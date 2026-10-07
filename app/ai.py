"""Adapters for the three services already declared in compose.yaml."""
from __future__ import annotations
import asyncio
import json
import re
import time
import uuid
import httpx
from pydantic import BaseModel, Field
from .settings import settings

COLLECTION = "resolved_appeals"


class RequiredContext(BaseModel):
    key: str
    reason: str = ""
    required: bool = True


class Category(BaseModel):
    code: str = "OTHER"
    name: str = "Другое"


class Classification(BaseModel):
    legal_required: bool
    case_type: str
    category: Category
    confidence: float = Field(ge=0, le=1)
    reasoning_summary: str
    recommended_template_code: str | None = None
    required_context: list[RequiredContext] = []
    warnings: list[str] = []


class Draft(BaseModel):
    subject: str
    issue_summary: str = ""
    factual_section: str = ""
    work_section: str = ""
    legal_section: str = ""
    closing_section: str = ""
    full_text: str = Field(min_length=1)
    used_case_ids: list[str] = []
    used_context_keys: list[str] = []
    missing_information: list[str] = []
    warnings: list[str] = []
    confidence: float = Field(ge=0, le=1)


async def embed(text: str, query: bool = False) -> list[float]:
    if query:
        text = "Instruct: Given a Russian resident appeal, retrieve similar resolved appeals\nQuery: " + text
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(settings.embedding_url.rstrip("/") + "/embed", json={"inputs": [text]})
        response.raise_for_status()
        data = response.json()
    vector = data[0] if isinstance(data, list) else data["embeddings"][0]
    if not isinstance(vector, list) or not vector:
        raise ValueError("Embedding service returned no vector")
    return vector


def qheaders() -> dict:
    return {"api-key": settings.qdrant_key} if settings.qdrant_key else {}


async def ensure_collection(size: int):
    async with httpx.AsyncClient(timeout=30, headers=qheaders()) as client:
        url = f"{settings.qdrant_url.rstrip('/')}/collections/{COLLECTION}"
        response = await client.get(url)
        if response.status_code == 404:
            response = await client.put(url, json={"vectors": {"size": size, "distance": "Cosine"}})
            response.raise_for_status()
        else:
            response.raise_for_status()
            actual = response.json()["result"]["config"]["params"]["vectors"]["size"]
            if actual != size:
                raise ValueError(f"Размерность индекса {actual}, embedding {size}; нужен rebuild")


async def delete_collection():
    async with httpx.AsyncClient(timeout=30, headers=qheaders()) as client:
        response = await client.delete(f"{settings.qdrant_url.rstrip('/')}/collections/{COLLECTION}")
        if response.status_code != 404:
            response.raise_for_status()


async def upsert_case(case: dict):
    vector = await embed(case["appeal_text"])
    await ensure_collection(len(vector))
    async with httpx.AsyncClient(timeout=60, headers=qheaders()) as client:
        response = await client.put(
            f"{settings.qdrant_url.rstrip('/')}/collections/{COLLECTION}/points?wait=true",
            json={"points": [{"id": case["id"], "vector": vector,
                              "payload": {"external_id": case["external_id"]}}]})
        response.raise_for_status()


async def retrieve(vector: list[float]) -> list[dict]:
    async with httpx.AsyncClient(timeout=30, headers=qheaders()) as client:
        response = await client.post(
            f"{settings.qdrant_url.rstrip('/')}/collections/{COLLECTION}/points/search",
            json={"vector": vector, "limit": settings.retrieval_top_k})
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return [{"id": point["id"], "retrieval_score": point["score"]}
                for point in response.json()["result"]]


async def rerank(query: str, cases: list[dict]) -> list[dict]:
    if not cases:
        return []
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(settings.reranker_url.rstrip("/") + "/rerank",
                                     json={"model": settings.reranker_model, "query": query,
                                           "documents": [case["appeal_text"] for case in cases]})
        response.raise_for_status()
        data = response.json()
    ranking = data.get("results", data) if isinstance(data, dict) else data
    output = []
    for item in ranking[:settings.rerank_top_k]:
        index = item.get("index")
        if isinstance(index, int) and 0 <= index < len(cases):
            output.append({**cases[index], "rerank_score": item.get("relevance_score", item.get("score"))})
    return output


class GigaChatClient:
    def __init__(self):
        self.token: str | None = None
        self.expires_at = 0.0
        self.lock = asyncio.Lock()

    async def access_token(self, force=False):
        if not settings.gigachat_key:
            raise ValueError("Задайте GIGACHAT_AUTH_KEY в .env")
        async with self.lock:
            if self.token and not force and time.time() < self.expires_at - 120:
                return self.token
            async with httpx.AsyncClient(timeout=30, verify=settings.verify_ssl) as client:
                response = await client.post(settings.gigachat_oauth_url,
                    headers={"Authorization": "Basic " + settings.gigachat_key,
                             "RqUID": str(uuid.uuid4()), "Accept": "application/json"},
                    data={"scope": settings.gigachat_scope})
                response.raise_for_status()
                data = response.json()
            self.token = data["access_token"]
            self.expires_at = int(data["expires_at"]) / 1000 if data.get("expires_at") else time.time() + 1800
            return self.token

    async def complete(self, messages: list[dict]) -> dict:
        async with httpx.AsyncClient(timeout=90, verify=settings.verify_ssl) as client:
            for attempt in range(4):
                token = await self.access_token(force=attempt > 0 and previous_status == 401)
                response = await client.post(settings.gigachat_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + token},
                    json={"model": settings.gigachat_model, "messages": messages, "temperature": 0.1})
                previous_status = response.status_code
                if response.status_code == 401 and attempt == 0:
                    continue
                if response.status_code in (408, 429, 500, 502, 503, 504) and attempt < 3:
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                return response.json()
        raise RuntimeError("GigaChat не ответил после повторов")

    async def structured(self, schema: type[BaseModel], system: str, payload: dict) -> tuple[BaseModel, dict]:
        messages = [{"role": "system", "content": system + "\nВерни только валидный JSON без Markdown."},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        for attempt in range(2):
            raw = await self.complete(messages)
            content = raw["choices"][0]["message"]["content"]
            try:
                return schema.model_validate(json.loads(content)), raw.get("usage", {})
            except (ValueError, KeyError) as exc:
                if attempt:
                    raise ValueError("GigaChat вернул невалидный JSON: " + str(exc)) from exc
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "Исправь ответ: верни только JSON нужной структуры."})
        raise RuntimeError("Недоступный ответ модели")


gigachat = GigaChatClient()


def llm_text(text: str) -> str:
    if not settings.mask_pii:
        return text
    text = re.sub(r"\b[\w.-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    text = re.sub(r"(?:\+7|8)[\s()-]*\d{3}[\s()-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}", "[ТЕЛЕФОН]", text)
    return text
