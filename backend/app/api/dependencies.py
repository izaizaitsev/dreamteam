"""Role checks and external service error mapping."""
import hmac
import httpx
from fastapi import Depends, Header, HTTPException, Request
from ..core.settings import settings
from ..core.sessions import COOKIE_NAME, valid_session


def auth(request: Request, x_api_key: str | None = Header(default=None)):
    keys = {"ADMIN": [settings.admin_api_key, settings.api_key],
            "LAWYER": [settings.lawyer_api_key], "OPERATOR": [settings.operator_api_key]}
    for role, values in keys.items():
        if x_api_key and any(key and hmac.compare_digest(x_api_key, key) for key in values):
            return role
    if valid_session(request.cookies.get(COOKIE_NAME)):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("X-Requested-With") != "DreamTeam":
            raise HTTPException(403, "Недопустимый источник запроса")
        return "ADMIN"
    raise HTTPException(401, "Требуется вход в систему")



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
