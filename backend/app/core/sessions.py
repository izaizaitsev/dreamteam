"""Opaque, revocable administrator sessions; credentials are configured by the operator."""
import hashlib
import time
from .settings import settings
from ..repositories import sqlite as storage

COOKIE_NAME = "dreamteam_session"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def credential_version() -> str:
    return hashlib.sha256(f"{settings.admin_username}\0{settings.admin_password}".encode()).hexdigest()


def init_sessions():
    if not settings.admin_password or len(settings.admin_password) < 12:
        raise RuntimeError("Set ADMIN_PASSWORD to at least 12 characters before starting the application")
    if settings.session_ttl_seconds <= 0:
        raise RuntimeError("SESSION_TTL_SECONDS must be positive")
    storage.execute("""CREATE TABLE IF NOT EXISTS admin_sessions (
        token_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL, credential_version TEXT NOT NULL
    )""")


def valid_session(token: str | None) -> bool:
    if not token or not settings.admin_password:
        return False
    return bool(storage.one(
        "SELECT token_hash FROM admin_sessions WHERE token_hash=? AND expires_at>? AND credential_version=?",
        (token_hash(token), int(time.time()), credential_version()),
    ))
