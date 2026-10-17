"""Health and public configuration routes."""
from fastapi import APIRouter, Depends
from ..repositories import sqlite as repository
from ..core.settings import settings
from ..integrations.credentials import gigachat_key, embedding_key
from .dependencies import auth

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/db")
def health_db():
    return {"status": "ok", "appeals": repository.one("SELECT COUNT(*) AS n FROM appeals")["n"]}


@router.get("/health/gigachat")
def health_gigachat():
    return {"configured": bool(gigachat_key()), "model": settings.gigachat_model}


@router.get("/health/embedding")
def health_embedding():
    return {"status": "configured" if embedding_key() else "unavailable",
            "model": settings.embedding_model}


@router.get("/api/config", dependencies=[Depends(auth)])
def config():
    return {"embedding_model": settings.embedding_model,
            "embedding_configured": bool(embedding_key()),
            "gigachat_model": settings.gigachat_model,
            "gigachat_configured": bool(gigachat_key())}


@router.get("/api/me")
def me(role: str = Depends(auth)):
    return {"role": role}
