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
from pydantic import BaseModel, ValidationError
from ..core.settings import settings
from .credentials import gigachat_key

logger = logging.getLogger("uvicorn.error")

def parse_model_json(content: str) -> dict:
    """Accept a JSON object, optionally inside a single Markdown code block."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Модель вернула пустой текст ответа")
    text = content.strip().lstrip("\ufeff").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].strip().lower() in {"```", "```json"} and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        if not exc.msg.startswith("Invalid control character"):
            raise
        # Models sometimes emit literal line breaks inside body. Preserve them,
        # while still requiring valid quoting, structure and the response schema.
        value = json.loads(text, strict=False)
        logger.info("GigaChat JSON normalized: reason=unescaped_control_character")
    if not isinstance(value, dict):
        raise ValueError("Модель должна вернуть JSON-объект")
    return value


def response_error(exc: Exception) -> str:
    """Diagnostic details without input text, model output or Pydantic input values."""
    if isinstance(exc, json.JSONDecodeError):
        return f"JSON syntax: {exc.msg}; line={exc.lineno} column={exc.colno} position={exc.pos}"
    if isinstance(exc, ValidationError):
        return "Schema validation: " + "; ".join(
            f"{'.'.join(map(str, error['loc']))}: {error['type']}"
            for error in exc.errors(include_input=False, include_context=False)[:8])
    if isinstance(exc, (KeyError, IndexError, TypeError)):
        return "Неверная структура ответа или тип поля"
    return str(exc)


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
            logger.warning("GigaChat unavailable: model=%s reason=missing_credentials", settings.gigachat_model)
            raise ValueError("Добавьте ключ GigaChat в разделе «Настройки»")
        async with self.lock:
            if self.token and not force and time.time() < self.expires_at - 120:
                return self.token
            request_id = str(uuid.uuid4())
            started = time.perf_counter()
            logger.info("GigaChat OAuth request: request_id=%s", request_id)
            try:
                async with httpx.AsyncClient(timeout=30, verify=gigachat_tls_verify()) as client:
                    response = await client.post(settings.gigachat_oauth_url,
                        headers={"Authorization": "Basic " + key,
                                 "RqUID": request_id, "Accept": "application/json"},
                        data={"scope": settings.gigachat_scope})
                    response.raise_for_status()
                    data = response.json()
                token = data["access_token"]
                expires_at = int(data["expires_at"]) / 1000 if data.get("expires_at") else time.time() + 1800
            except Exception as exc:
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                logger.error("GigaChat OAuth failed: request_id=%s status=%s error=%s elapsed_ms=%.0f",
                             request_id, status, type(exc).__name__, (time.perf_counter() - started) * 1000)
                raise
            self.token = token
            self.expires_at = expires_at
            logger.info("GigaChat OAuth response: request_id=%s status=%d elapsed_ms=%.0f",
                        request_id, response.status_code, (time.perf_counter() - started) * 1000)
            return self.token

    async def complete(self, messages: list[dict]) -> dict:
        try:
            verify = gigachat_tls_verify()
        except Exception as exc:
            logger.error("GigaChat TLS configuration failed: error=%s", type(exc).__name__)
            raise
        async with httpx.AsyncClient(timeout=90, verify=verify) as client:
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
            content = None
            finish_reason = None
            try:
                choice = raw["choices"][0]
                finish_reason = choice.get("finish_reason")
                content = choice["message"]["content"]
                if finish_reason in {"length", "max_tokens"}:
                    raise ValueError("Ответ модели обрезан по лимиту токенов; сократи текст и верни завершённый JSON")
                parsed = schema.model_validate(parse_model_json(content))
                if schema.__name__ == "Draft":
                    if not parsed.body.strip():
                        raise ValueError("Пустой body черновика")
                    expected = set(payload["header_schema"]["properties"])
                    if set(parsed.header) != expected:
                        raise ValueError("Поля header не соответствуют header_schema")
                    for key, value in payload["header_values"].items():
                        if parsed.header[key] != value:
                            raise ValueError("Изменены известные реквизиты шапки")
                return parsed, raw.get("usage", {})
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                detail = response_error(exc)
                logger.warning("GigaChat invalid structured response: model=%s schema=%s attempt=%d error=%s detail=%s finish_reason=%s characters=%d",
                               settings.gigachat_model, schema.__name__, attempt + 1, type(exc).__name__,
                               detail, finish_reason, len(content) if isinstance(content, str) else 0)
                if attempt:
                    raise RuntimeError("GigaChat не вернул ответ нужной структуры: " + detail) from exc
                if isinstance(content, str) and content:
                    messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content":
                                 "Исправь ответ. Ошибка проверки: " + detail + ". "
                                 "Верни только один завершённый JSON-объект по response_schema, без Markdown. "
                                 "Экранируй двойные кавычки внутри строк как \\\" и переводы строк как \\n. "
                                 "Сохрани все обязательные поля и типы из response_schema. "
                                 "Если переданы header_schema и header_values, соблюдай их."})
        raise RuntimeError("Недоступный ответ модели")



gigachat = GigaChatClient()
