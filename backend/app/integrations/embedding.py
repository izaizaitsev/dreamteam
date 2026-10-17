"""Cloud.ru OpenAI-compatible embedding adapter."""
import httpx
from ..core.settings import settings
from .credentials import embedding_key


async def embed(text: str, query: bool = False) -> list[float]:
    key = embedding_key()
    if not key:
        raise ValueError("Добавьте API-ключ embedding в разделе «Настройки»")
    if query:
        text = "Instruct: Given a Russian resident appeal, retrieve similar resolved appeals\nQuery: " + text
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            settings.embedding_url.rstrip("/") + "/embeddings",
            headers={"Authorization": "Bearer " + key},
            json={"model": settings.embedding_model, "input": [text]},
        )
        response.raise_for_status()
        data = response.json()
    vector = data["data"][0]["embedding"]
    if not isinstance(vector, list) or not vector:
        raise ValueError("Embedding service returned no vector")
    return vector
