"""System API routes."""
import httpx
from fastapi import APIRouter, Depends
from ..repositories import sqlite as s
from ..core.settings import settings
from ..integrations.credentials import gigachat_key
from .dependencies import auth

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}



@router.get("/health/db")
def health_db():
    return {"status": "ok", "appeals": s.one("SELECT COUNT(*) AS n FROM appeals")["n"]}



@router.get("/health/gigachat")
def health_gigachat():
    return {"configured": bool(gigachat_key()), "model": settings.gigachat_model}



@router.get("/health/embedding")
async def health_embedding():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(settings.embedding_url.rstrip("/") + "/health")
            return {"status": "ok" if response.is_success else "unavailable", "http_status": response.status_code}
    except httpx.HTTPError:
        return {"status": "unavailable"}



@router.get("/health/reranker")
async def health_reranker():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(settings.reranker_url.rstrip("/") + "/health")
            return {"status": "ok" if response.is_success else "unavailable", "http_status": response.status_code}
    except httpx.HTTPError:
        return {"status": "unavailable"}



@router.get("/api/config", dependencies=[Depends(auth)])
def config():
    return {"embedding_model": settings.embedding_model, "reranker_model": settings.reranker_model,
            "gigachat_model": settings.gigachat_model, "gigachat_configured": bool(gigachat_key())}



@router.get("/api/me")
def me(role: str = Depends(auth)):
    return {"role": role}
