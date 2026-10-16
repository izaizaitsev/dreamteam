"""GigaChat OAuth, TLS and chat adapter."""
import asyncio
import json
import ssl
import time
import uuid
from pathlib import Path
import certifi
import httpx
from pydantic import BaseModel
from ..core.settings import settings
from .credentials import gigachat_key


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
