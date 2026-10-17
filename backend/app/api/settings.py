"""Settings API routes."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from .. import ai
from ..repositories import sqlite as s
from ..core.settings import settings
from ..integrations.credentials import gigachat_key, save_gigachat_key, embedding_key, save_embedding_key
from .dependencies import admin

router = APIRouter()


class GigaChatKeyInput(BaseModel):
    auth_key: str = Field(min_length=16)


class EmbeddingKeyInput(BaseModel):
    api_key: str = Field(min_length=16)



@router.get("/api/settings/gigachat", dependencies=[Depends(admin)])
def gigachat_settings():
    return {"configured": bool(gigachat_key()), "model": settings.gigachat_model}



@router.put("/api/settings/gigachat", dependencies=[Depends(admin)])
async def put_gigachat_settings(body: GigaChatKeyInput):
    save_gigachat_key(body.auth_key)
    async with ai.gigachat.lock:
        ai.gigachat.token = None
        ai.gigachat.expires_at = 0
    s.audit(None, "gigachat_key_updated", details={"source": "web_settings"})
    return {"configured": True, "model": settings.gigachat_model}


@router.get("/api/settings/embedding", dependencies=[Depends(admin)])
def embedding_settings():
    return {"configured": bool(embedding_key()), "model": settings.embedding_model}


@router.put("/api/settings/embedding", dependencies=[Depends(admin)])
def put_embedding_settings(body: EmbeddingKeyInput):
    save_embedding_key(body.api_key)
    s.audit(None, "embedding_key_updated", details={"source": "web_settings"})
    return {"configured": True, "model": settings.embedding_model}
