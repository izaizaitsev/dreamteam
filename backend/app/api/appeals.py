"""Appeals API routes."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..services import processing as p
from ..repositories import sqlite as s
from ..services.indexing import index_case
from .dependencies import auth, lawyer, fail, ai_failure

router = APIRouter()


@router.get("/api/appeals", dependencies=[Depends(auth)])
def appeals(status: str | None = None, q: str | None = None):
    query = "SELECT id,external_id,source,title,text,applicant_name,building_id,received_at,due_at,status,error FROM appeals WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"; params.append(status)
    if q:
        query += " AND (text LIKE ? OR external_id LIKE ? OR title LIKE ?)"
        params.extend(["%" + q + "%"] * 3)
    query += " ORDER BY created_at DESC LIMIT 500"
    return s.all_rows(query, tuple(params))



@router.get("/api/appeals/{appeal_id}", dependencies=[Depends(auth)])
def detail(appeal_id: str):
    try:
        return p.detail(appeal_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc



@router.post("/api/appeals/{appeal_id}/process", dependencies=[Depends(lawyer)])
async def process(appeal_id: str):
    try:
        return await p.process(appeal_id)
    except Exception as exc:
        ai_failure(exc)



@router.post("/api/appeals/{appeal_id}/retrieve", dependencies=[Depends(lawyer)])
async def retrieve(appeal_id: str):
    try:
        return await p.search(appeal_id)
    except ValueError as exc:
        fail(exc)



@router.post("/api/appeals/{appeal_id}/classify", dependencies=[Depends(lawyer)])
async def classify(appeal_id: str):
    try:
        return await p.classify(appeal_id)
    except Exception as exc:
        if s.one("SELECT id FROM appeals WHERE id=?", (appeal_id,)):
            p.set_status(appeal_id, "ERROR", f"CLASSIFYING: {exc}")
        ai_failure(exc)



@router.post("/api/appeals/{appeal_id}/load-context", dependencies=[Depends(lawyer)])
def context(appeal_id: str):
    try:
        return p.load_context(appeal_id)
    except ValueError as exc:
        fail(exc)



@router.post("/api/appeals/{appeal_id}/generate-draft", dependencies=[Depends(lawyer)])
async def generate(appeal_id: str):
    try:
        return await p.generate_draft(appeal_id)
    except Exception as exc:
        if s.one("SELECT id FROM appeals WHERE id=?", (appeal_id,)):
            p.set_status(appeal_id, "ERROR", f"DRAFTING: {exc}")
        ai_failure(exc)



@router.get("/api/appeals/{appeal_id}/similar-cases", dependencies=[Depends(auth)])
def similar(appeal_id: str):
    return s.latest(appeal_id, "similar_cases") or []



@router.get("/api/appeals/{appeal_id}/context", dependencies=[Depends(auth)])
def context_get(appeal_id: str):
    return s.latest(appeal_id, "context") or []



@router.get("/api/appeals/{appeal_id}/draft", dependencies=[Depends(auth)])
def draft_get(appeal_id: str):
    return p.detail(appeal_id)["draft"]



class ResolveInput(BaseModel):
    actor: str = Field(min_length=1)
    decision_file_uri: str | None = None
    index_now: bool = False



@router.post("/api/appeals/{appeal_id}/mark-resolved", dependencies=[Depends(lawyer)])
async def mark_resolved(appeal_id: str, body: ResolveInput):
    row = s.one("SELECT * FROM appeals WHERE id=?", (appeal_id,))
    if not row:
        raise HTTPException(404, "Обращение не найдено")
    draft = s.one("SELECT * FROM drafts WHERE appeal_id=? AND status='APPROVED' ORDER BY reviewed_at DESC LIMIT 1", (appeal_id,))
    if not draft:
        raise HTTPException(409, "Сначала одобрите ответ")
    existing = s.one("SELECT id FROM cases WHERE external_id=?", (row["external_id"],))
    case_id = existing["id"] if existing else s.uid()
    classification = s.latest(appeal_id, "classification") or {}
    category = classification.get("category", {}).get("code")
    decision_file_uri = body.decision_file_uri or draft["document_uri"]
    if existing:
        s.execute("UPDATE cases SET appeal_text=?,decision_text=?,decision_file_uri=?,category_code=?,indexed_at=NULL,updated_at=? WHERE id=?",
            (row["text"], draft["edited_text"], decision_file_uri, category, s.now(), case_id))
    else:
        s.execute("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (case_id, row["external_id"], row["text"], draft["edited_text"],
             decision_file_uri, category, row["source"], row["building_id"],
             json.dumps({"origin_appeal_id": appeal_id}, ensure_ascii=False), None, None, s.now(), s.now()))
    s.audit(appeal_id, "resolved", body.actor, {"case_id": case_id, "decision_file_uri": decision_file_uri})
    indexed = False
    if body.index_now:
        try:
            await index_case(case_id)
            indexed = True
        except Exception as exc:
            return {"case_id": case_id, "indexed": False, "index_error": str(exc)}
    return {"case_id": case_id, "indexed": indexed}
