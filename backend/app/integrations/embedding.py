"""Local embedding HTTP adapter."""
import httpx
from ..core.settings import settings


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
