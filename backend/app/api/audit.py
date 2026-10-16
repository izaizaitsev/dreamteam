"""Audit API routes."""
from fastapi import APIRouter, Depends
from ..repositories import sqlite as s
from .dependencies import admin

router = APIRouter()


@router.get("/api/audit", dependencies=[Depends(admin)])
def audit(appeal_id: str | None = None):
    if appeal_id:
        return s.all_rows("SELECT * FROM audit WHERE appeal_id=? ORDER BY created_at DESC LIMIT 200", (appeal_id,))
    return s.all_rows("SELECT * FROM audit ORDER BY created_at DESC LIMIT 200")
