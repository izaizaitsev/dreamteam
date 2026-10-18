"""Cloud.ru OpenAI-compatible embedding adapter."""
import logging
import time
import httpx
from ..core.settings import settings
from .credentials import embedding_key

logger = logging.getLogger("uvicorn.error")


async def embed(text: str, query: bool = False) -> list[float]:
    key = embedding_key()
    if not key:
        raise ValueError("Добавьте API-ключ embedding в разделе «Настройки»")
    if query:
        text = "Instruct: Given a Russian resident appeal, retrieve similar resolved appeals\nQuery: " + text
    started = time.perf_counter()
    purpose = "query" if query else "case"
    logger.info("Embedding request: model=%s purpose=%s", settings.embedding_model, purpose)
    try:
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
    except Exception as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.error("Embedding failed: model=%s purpose=%s status=%s error=%s elapsed_ms=%.0f",
                     settings.embedding_model, purpose, status, type(exc).__name__,
                     (time.perf_counter() - started) * 1000)
        raise
    logger.info("Embedding response: model=%s purpose=%s dimensions=%d elapsed_ms=%.0f",
                settings.embedding_model, purpose, len(vector), (time.perf_counter() - started) * 1000)
    return vector
