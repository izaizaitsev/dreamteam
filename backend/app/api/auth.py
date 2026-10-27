"""Administrator login/logout. There is deliberately no registration endpoint."""
import hashlib
import hmac
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from ..core.settings import settings
from ..core.sessions import COOKIE_NAME, credential_version, token_hash
from ..repositories import sqlite as storage
from .dependencies import auth

router = APIRouter(prefix="/api/auth")


def browser_write(request: Request):
    if request.headers.get("X-Requested-With") != "DreamTeam":
        raise HTTPException(403, "Недопустимый источник запроса")


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


@router.post("/login", dependencies=[Depends(browser_write)])
def login(body: LoginInput, request: Request, response: Response):
    # Hash both operands before comparing to support Unicode and equal-length comparison.
    username_ok = hmac.compare_digest(hashlib.sha256(body.username.encode()).digest(),
                                      hashlib.sha256(settings.admin_username.encode()).digest())
    password_ok = hmac.compare_digest(hashlib.sha256(body.password.encode()).digest(),
                                      hashlib.sha256(settings.admin_password.encode()).digest())
    if not settings.admin_password or not (username_ok and password_ok):
        raise HTTPException(401, "Неверный логин или пароль")
    old_token = request.cookies.get(COOKIE_NAME)
    if old_token:
        storage.execute("DELETE FROM admin_sessions WHERE token_hash=?", (token_hash(old_token),))
    storage.execute("DELETE FROM admin_sessions WHERE expires_at<=?", (int(time.time()),))
    token = secrets.token_urlsafe(32)
    storage.execute("INSERT INTO admin_sessions VALUES (?,?,?)",
                    (token_hash(token), int(time.time()) + settings.session_ttl_seconds, credential_version()))
    response.set_cookie(COOKIE_NAME, token, max_age=settings.session_ttl_seconds,
                        httponly=True, secure=settings.session_cookie_secure, samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"role": "ADMIN"}


@router.post("/logout", dependencies=[Depends(browser_write), Depends(auth)])
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        storage.execute("DELETE FROM admin_sessions WHERE token_hash=?", (token_hash(token),))
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.session_cookie_secure,
                           httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
