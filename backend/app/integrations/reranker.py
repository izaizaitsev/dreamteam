"""Local reranker HTTP adapter."""
import httpx
from ..core.settings import settings


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
