from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import Actor, get_actor, require_role
from .db import get_db
from .deadlines import deadline_state, local_today, reminder_offset
from .models import AuditEvent, Draft, Escalation, User
from .rag_client import RAGError, get_document, get_job, get_original, list_documents, upload_document
from .templates import render_obligation_draft

router = APIRouter(prefix="/api/v1")

class DocumentUploadResponse(BaseModel):
    job_id: str
    document_id: str
    revision_id: str
    status: str

class ObligationDraftIn(BaseModel):
    question: str = Field(min_length=5, max_length=3000)
    completion_date: date
    completed: bool

class DraftEditIn(BaseModel):
    content: str = Field(min_length=10, max_length=50000)

def fail(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})

def rag_failure(exc: RAGError):
    if exc.status_code == 404:
        fail(404, "not_found", "Документ не найден")
    if exc.status_code == 409:
        fail(409, "document_conflict", "Документ с такими данными уже существует")
    if exc.status_code == 422:
        fail(422, "invalid_document", "Некорректный документ или категория")
    fail(503, "rag_unavailable", "Сервис документов временно недоступен")

def draft_out(item: Draft) -> dict:
    return {"id": item.id, "prescription_id": item.prescription_id,
        "obligation_revision_id": item.obligation_revision_id, "template_id": item.template_id,
        "content": item.content, "status": item.status, "citations": item.citations,
        "created_at": item.created_at}

@router.post("/documents", status_code=202, response_model=DocumentUploadResponse)
async def submit_document(document_category: Literal["normative", "obligation"] = Form(...),
                          title: str = Form(...), file: UploadFile = File(...),
                          document_id: str | None = Form(default=None), actor: Actor = Depends(get_actor)):
    if document_category == "normative":
        require_role(actor, "admin", "lawyer")
    name = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
    raw = await file.read(10 * 1024 * 1024 + 1)
    if not name.lower().endswith(".docx") or len(raw) > 10 * 1024 * 1024:
        fail(422, "invalid_document", "Загрузите DOCX не больше 10 МБ")
    try:
        return await upload_document(actor.organization_id, document_category, title, name, raw, document_id)
    except RAGError as exc:
        rag_failure(exc)

@router.get("/documents")
async def documents(document_category: Literal["normative", "obligation"] | None = None,
                    actor: Actor = Depends(get_actor)):
    try:
        return await list_documents(actor.organization_id, document_category)
    except RAGError as exc:
        rag_failure(exc)

@router.get("/documents/jobs/{job_id}")
async def document_job(job_id: str, actor: Actor = Depends(get_actor)):
    try:
        return await get_job(actor.organization_id, job_id)
    except RAGError as exc:
        rag_failure(exc)

@router.get("/documents/{revision_id}/original")
async def original(revision_id: str, actor: Actor = Depends(get_actor)):
    try:
        raw = await get_original(actor.organization_id, revision_id)
    except RAGError as exc:
        rag_failure(exc)
    return Response(content=raw, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{revision_id}.docx"'})

@router.get("/deadline-dashboard")
async def deadline_dashboard(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    try:
        documents = await list_documents(actor.organization_id, "obligation")
    except RAGError as exc:
        rag_failure(exc)
    escalations = {item.revision_id: item for item in db.scalars(select(Escalation).where(
        Escalation.organization_id == actor.organization_id)).all()}
    today = local_today()
    result = []
    for document in documents:
        if document["status"] != "published_demo" or not document["due_date"]:
            continue
        due = date.fromisoformat(document["due_date"])
        escalation = escalations.get(document["revision_id"])
        result.append({**document, "days_remaining": (due - today).days,
            "sla_state": deadline_state(due, "open", today), "reminder": reminder_offset(due, today),
            "escalated_at": escalation.created_at if escalation else None,
            "escalated_to": "director" if escalation else None})
    return sorted(result, key=lambda item: item["due_date"])

@router.post("/deadline-dashboard/{revision_id}/escalate")
async def escalate(revision_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    require_role(actor, "admin", "lawyer", "specialist")
    try:
        document = await get_document(actor.organization_id, revision_id)
    except RAGError as exc:
        rag_failure(exc)
    if document["document_category"] != "obligation" or document["status"] != "published_demo":
        fail(409, "invalid_document", "Эскалация доступна только для опубликованного документа обязательств")
    existing = db.scalar(select(Escalation).where(Escalation.organization_id == actor.organization_id,
        Escalation.revision_id == revision_id))
    if existing:
        return {"id": existing.id, "revision_id": revision_id, "escalated_at": existing.created_at}
    director = db.scalar(select(User).where(User.organization_id == actor.organization_id, User.role == "director"))
    if director is None:
        fail(409, "director_missing", "В организации не назначен директор")
    escalation = Escalation(organization_id=actor.organization_id, revision_id=revision_id,
        director_id=director.id, actor_id=actor.id)
    db.add(escalation)
    db.flush()
    db.add(AuditEvent(organization_id=actor.organization_id, actor_id=actor.id,
        resource="escalation", resource_id=escalation.id, action="created"))
    db.commit()
    return {"id": escalation.id, "revision_id": revision_id, "escalated_at": escalation.created_at}

@router.get("/director-escalations")
async def director_escalations(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    require_role(actor, "admin", "director")
    try:
        documents = await list_documents(actor.organization_id, "obligation")
    except RAGError as exc:
        rag_failure(exc)
    titles = {document["revision_id"]: document["title"] for document in documents}
    return [{"id": item.id, "revision_id": item.revision_id, "title": titles.get(item.revision_id, "Документ"),
        "created_at": item.created_at} for item in db.scalars(select(Escalation).where(
        Escalation.organization_id == actor.organization_id,
        *([] if actor.role == "admin" else [Escalation.director_id == actor.id]))).all()]

@router.post("/obligation-documents/{revision_id}/drafts", status_code=201)
async def generate_obligation_draft(revision_id: str, data: ObligationDraftIn,
                                    actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    try:
        document = await get_document(actor.organization_id, revision_id)
    except RAGError as exc:
        rag_failure(exc)
    if document["document_category"] != "obligation" or document["status"] != "published_demo":
        fail(409, "invalid_document", "Нужен опубликованный документ обязательств")
    content, template_id = render_obligation_draft(document, data.question, data.completed, data.completion_date)
    draft = Draft(organization_id=actor.organization_id, obligation_revision_id=revision_id,
        template_id=template_id, content=content, citations=[{
            "document_category": "obligation", "revision_id": revision_id,
            "title": document["title"], "fragment": document["source_fragment"],
            "original_url": document["original_url"]}])
    db.add(draft)
    db.flush()
    db.add(AuditEvent(organization_id=actor.organization_id, actor_id=actor.id,
        resource="draft", resource_id=draft.id, action="created_from_template"))
    db.commit()
    return draft_out(draft)

@router.get("/obligation-documents/{revision_id}/drafts")
async def obligation_drafts(revision_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    try:
        document = await get_document(actor.organization_id, revision_id)
    except RAGError as exc:
        rag_failure(exc)
    if document["document_category"] != "obligation":
        fail(404, "not_found", "Документ не найден")
    return [draft_out(item) for item in db.scalars(select(Draft).where(Draft.organization_id == actor.organization_id,
        Draft.obligation_revision_id == revision_id).order_by(Draft.created_at.desc())).all()]

@router.patch("/drafts/{draft_id}")
def edit_draft(draft_id: str, data: DraftEditIn, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    draft = db.scalar(select(Draft).where(Draft.id == draft_id, Draft.organization_id == actor.organization_id))
    if draft is None:
        fail(404, "not_found", "Черновик не найден")
    if draft.status != "draft":
        fail(409, "invalid_transition", "Редактировать можно только черновик")
    draft.content = data.content
    db.add(AuditEvent(organization_id=actor.organization_id, actor_id=actor.id,
        resource="draft", resource_id=draft.id, action="edited"))
    db.commit()
    return draft_out(draft)
