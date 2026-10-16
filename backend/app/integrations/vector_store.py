"""Qdrant vector index adapter."""
import httpx
from ..core.settings import settings
from .embedding import embed

COLLECTION = "resolved_appeals"


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
