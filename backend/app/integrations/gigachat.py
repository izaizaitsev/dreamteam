"""GigaChat OAuth, TLS and chat adapter."""
import asyncio
import json
import logging
import ssl
import time
import uuid
from pathlib import Path
import certifi
import httpx
from pydantic import BaseModel
from ..core.settings import settings
from .credentials import gigachat_key

logger = logging.getLogger("uvicorn.error")


def gigachat_tls_verify() -> ssl.SSLContext | bool:
    if not settings.verify_ssl:
        return False
    context = ssl.create_default_context(cafile=certifi.where())
    root = Path(__file__).resolve().parents[1] / "certs" / "russian_trusted_root_ca_pem.crt"
    context.load_verify_locations(cafile=str(root))
    if settings.gigachat_ca_bundle_file:
        context.load_verify_locations(cafile=settings.gigachat_ca_bundle_file)
    return context



class GigaChatClient:
    def __init__(self):
        self.token: str | None = None
        self.expires_at = 0.0
        self.lock = asyncio.Lock()

    async def access_token(self, force=False):
        key = gigachat_key()
        if not key:
            raise ValueError("Добавьте ключ GigaChat в разделе «Настройки»")
        async with self.lock:
            if self.token and not force and time.time() < self.expires_at - 120:
                return self.token
            async with httpx.AsyncClient(timeout=30, verify=gigachat_tls_verify()) as client:
                response = await client.post(settings.gigachat_oauth_url,
                    headers={"Authorization": "Basic " + key,
                             "RqUID": str(uuid.uuid4()), "Accept": "application/json"},
                    data={"scope": settings.gigachat_scope})
                response.raise_for_status()
                data = response.json()
            self.token = data["access_token"]
            self.expires_at = int(data["expires_at"]) / 1000 if data.get("expires_at") else time.time() + 1800
            return self.token

    async def complete(self, messages: list[dict]) -> dict:
        async with httpx.AsyncClient(timeout=90, verify=gigachat_tls_verify()) as client:
            for attempt in range(4):
                started = time.perf_counter()
                logger.info("GigaChat request: model=%s attempt=%d", settings.gigachat_model, attempt + 1)
                try:
                    token = await self.access_token(force=attempt > 0 and previous_status == 401)
                    response = await client.post(settings.gigachat_url.rstrip("/") + "/chat/completions",
                        headers={"Authorization": "Bearer " + token},
                        json={"model": settings.gigachat_model, "messages": messages, "temperature": 0.1})
                except Exception as exc:
                    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                    logger.error("GigaChat failed: model=%s attempt=%d status=%s error=%s elapsed_ms=%.0f",
                                 settings.gigachat_model, attempt + 1, status, type(exc).__name__,
                                 (time.perf_counter() - started) * 1000)
                    raise
                previous_status = response.status_code
                if response.status_code == 401 and attempt == 0:
                    logger.warning("GigaChat retry: model=%s attempt=%d status=%d",
                                   settings.gigachat_model, attempt + 1, response.status_code)
                    continue
                if response.status_code in (408, 429, 500, 502, 503, 504) and attempt < 3:
                    logger.warning("GigaChat retry: model=%s attempt=%d status=%d",
                                   settings.gigachat_model, attempt + 1, response.status_code)
                    await asyncio.sleep(2 ** attempt)
                    continue
                try:
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("GigaChat response must be a JSON object")
                except Exception as exc:
                    logger.error("GigaChat failed: model=%s attempt=%d status=%d error=%s elapsed_ms=%.0f",
                                 settings.gigachat_model, attempt + 1, response.status_code,
                                 type(exc).__name__, (time.perf_counter() - started) * 1000)
                    raise
                usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
                logger.info("GigaChat response: model=%s attempt=%d status=%d total_tokens=%s elapsed_ms=%.0f",
                            settings.gigachat_model, attempt + 1, response.status_code,
                            usage.get("total_tokens"), (time.perf_counter() - started) * 1000)
                return data
        raise RuntimeError("GigaChat не ответил после повторов")

    async def structured(self, schema: type[BaseModel], system: str, payload: dict) -> tuple[BaseModel, dict]:
        messages = [{"role": "system", "content": system + "\nВерни только валидный JSON без Markdown."},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        for attempt in range(2):
            raw = await self.complete(messages)
            content = raw["choices"][0]["message"]["content"]
            try:
                parsed = schema.model_validate(json.loads(content))
                if schema.__name__ == "Draft" and not payload.get("template") and not parsed.full_text.strip():
                    sections = [parsed.issue_summary, parsed.factual_section, parsed.work_section,
                                parsed.legal_section, parsed.closing_section]
                    if not any(section.strip() for section in sections):
                        raise ValueError("Пустой full_text и секции черновика при отсутствии шаблона")
                    full_text = "\n\n".join(part.strip() for part in [parsed.subject, *sections] if part.strip())
                    parsed = parsed.model_copy(update={"full_text": full_text})
                return parsed, raw.get("usage", {})
            except (ValueError, KeyError) as exc:
                logger.warning("GigaChat invalid structured response: model=%s schema=%s attempt=%d error=%s",
                               settings.gigachat_model, schema.__name__, attempt + 1, type(exc).__name__)
                if attempt:
                    raise ValueError("GigaChat вернул невалидный JSON: " + str(exc)) from exc
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content":
                                 "Исправь ответ: верни JSON нужной структуры. "
                                 "Если шаблона нет, заполни full_text связным текстом черновика."})
        raise RuntimeError("Недоступный ответ модели")



gigachat = GigaChatClient()
