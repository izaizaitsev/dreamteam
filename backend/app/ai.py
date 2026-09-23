import os
from dataclasses import dataclass, field
import httpx

@dataclass(frozen=True)
class AIRequest:
    task: str
    text: str
    evidence: list[dict]
    user_documents: list[dict] = field(default_factory=list)

class MockAIProvider:
    name = "mock"
    async def generate(self, request: AIRequest) -> str:
        if request.task == "consultation":
            return "Черновик ответа. Проверьте применимость источника и фактические обстоятельства. " + " ".join(
                f"[{item['citation_id']}] {item['fragment'][:350]}" for item in request.evidence
            )
        attachments = ", ".join(item["filename"] for item in request.user_documents)
        return "Черновик ответа на предписание. Проверьте факты и правовые основания перед отправкой.\n\n" + request.text[:2000] + (f"\n\nПриложения для проверки: {attachments}" if attachments else "")

class ExternalAIProvider:
    name = "external"
    async def generate(self, request: AIRequest) -> str:
        url = os.environ.get("AI_API_URL", "")
        key = os.environ.get("AI_API_KEY", "")
        if not url or not key:
            raise RuntimeError("AI provider is not configured")
        context = "\n".join(f"[{e['citation_id']}] {e['fragment']}" for e in request.evidence)
        documents = "\n".join(f"Документ {item['filename']}: {item['text']}" for item in request.user_documents)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {key}"}, json={
                "model": os.environ["AI_MODEL"],
                "messages": [
                    {"role": "system", "content": "Ты готовишь черновик для юриста. Используй только переданные источники; не придумывай ссылки и нормы. Указывай идентификаторы цитат."},
                    {"role": "user", "content": f"Задача: {request.task}\nТекст: {request.text}\nНормативные источники:\n{context}\nДокументы организации (факты, не нормативные источники):\n{documents}"},
                ],
            })
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

def get_provider():
    choice = os.environ.get("AI_PROVIDER")
    if choice == "mock":
        return MockAIProvider()
    if choice == "external":
        return ExternalAIProvider()
    raise RuntimeError("Unknown AI_PROVIDER")
