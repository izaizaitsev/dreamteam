"""Role checks and external service error mapping."""
import hmac
import httpx
from fastapi import Depends, Header, HTTPException
from ..core.settings import settings


def auth(x_api_key: str | None = Header(default=None)):
    keys = {"ADMIN": [settings.admin_api_key, settings.api_key],
            "LAWYER": [settings.lawyer_api_key], "OPERATOR": [settings.operator_api_key]}
    if not any(key for values in keys.values() for key in values):
        return "ADMIN"  # Localhost pilot only; set keys before exposing the service.
    for role, values in keys.items():
        if x_api_key and any(key and hmac.compare_digest(x_api_key, key) for key in values):
            return role
    raise HTTPException(401, "Неверный X-API-Key")



def admin(role: str = Depends(auth)):
    if role != "ADMIN":
        raise HTTPException(403, "Требуется роль ADMIN")



def lawyer(role: str = Depends(auth)):
    if role not in {"ADMIN", "LAWYER"}:
        raise HTTPException(403, "Требуется роль LAWYER")



def fail(exc: Exception):
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    raise exc



def ai_failure(exc: Exception):
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    if "CERTIFICATE_VERIFY_FAILED" in str(exc):
        raise HTTPException(502, "Не удалось проверить сертификат GigaChat. Проверьте доступ к сервису и доверенный CA-сертификат.") from exc
    if isinstance(exc, httpx.HTTPStatusError):
        raise HTTPException(502, f"AI-сервис вернул HTTP {exc.response.status_code}") from exc
    if isinstance(exc, (httpx.HTTPError, OSError)):
        raise HTTPException(502, f"Ошибка соединения с AI-сервисом: {exc}") from exc
    raise HTTPException(502, f"AI-анализ не выполнен: {exc}") from exc
