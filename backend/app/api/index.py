"""Index API routes."""
from fastapi import APIRouter, Depends
from .. import ai
from ..repositories import sqlite as s
from ..services.indexing import index_case
from ..core.settings import settings
from .dependencies import auth, admin

router = APIRouter()


@router.get("/api/index/status", dependencies=[Depends(auth)])
def index_status():
    result = s.one("SELECT COUNT(*) AS total, SUM(CASE WHEN indexed_at IS NOT NULL AND embedding_model=? THEN 1 ELSE 0 END) AS indexed FROM cases", (settings.embedding_model,))
    result["pending"] = result["total"] - (result["indexed"] or 0)
    return result



@router.post("/api/index/upsert", dependencies=[Depends(admin)])
async def index_upsert():
    cases = s.all_rows("SELECT id FROM cases WHERE indexed_at IS NULL OR embedding_model IS NULL OR embedding_model!=?", (settings.embedding_model,))
    report = {"total": len(cases), "indexed": 0, "errors": []}
    for case in cases:
        try:
            await index_case(case["id"])
            report["indexed"] += 1
        except Exception as exc:
            report["errors"].append({"id": case["id"], "message": str(exc)})
    return report



@router.post("/api/index/rebuild", dependencies=[Depends(admin)])
async def index_rebuild():
    await ai.delete_collection()
    s.execute("UPDATE cases SET indexed_at=NULL")
    return await index_upsert()
