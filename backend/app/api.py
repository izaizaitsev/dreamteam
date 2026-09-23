import hashlib
import hmac
import os
from datetime import date
from uuid import uuid4
import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from .ai import AIRequest, get_provider
from .auth import Actor, get_actor, password_hash, require_role, token_for
from .db import get_db
from .deadlines import deadline_state, local_today
from .documents import DocumentError, MAX_FILE_BYTES, extract_text
from .models import (AIGeneration, AuditEvent, BackgroundJob, Consultation, Draft, Obligation,
                     Prescription, RegulatoryDocument, RegulatoryRevision, User, UserDocument)
from .worker import evaluate_deadlines

app = FastAPI(title="ЖКХ: юридический помощник", version="0.1.0")
PREFIX = "/api/v1"

@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={**detail, "details": {}, "request_id": request.headers.get("x-request-id", str(uuid4()))})

@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    import logging
    request_id = request.headers.get("x-request-id", str(uuid4()))
    logging.exception("Request %s failed", request_id)
    return JSONResponse(status_code=500, content={"code": "internal_error", "message": "Внутренняя ошибка", "details": {}, "request_id": request_id})

class LoginIn(BaseModel):
    username: str
    password: str

class ConsultationIn(BaseModel):
    question: str = Field(min_length=5, max_length=5000)
    target_date: date = Field(default_factory=local_today)

class PrescriptionIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    content: str = Field(min_length=10, max_length=50000)

class ObligationIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str = ""
    due_date: date
    priority: str = "normal"

class RevisionIn(BaseModel):
    document_id: str | None = None
    title: str = Field(min_length=3, max_length=300)
    section: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl | None = None
    effective_from: date
    effective_to: date | None = None
    content: str = Field(min_length=10, max_length=100000)

    @field_validator("source_url")
    @classmethod
    def https_only(cls, value: HttpUrl | None):
        if value is not None and value.scheme != "https":
            raise ValueError("Используйте HTTPS для ссылки на источник")
        return value

def fail(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})

def audit(db: Session, actor: Actor, resource: str, resource_id: str, action: str):
    db.add(AuditEvent(organization_id=actor.organization_id, actor_id=actor.id,
                      resource=resource, resource_id=resource_id, action=action))

def consultation_out(item: Consultation) -> dict:
    return {"id": item.id, "question": item.question, "target_date": item.target_date,
            "status": item.status, "answer": item.answer, "citations": item.citations, "created_at": item.created_at}

def draft_out(item: Draft) -> dict:
    return {"id": item.id, "prescription_id": item.prescription_id, "content": item.content,
            "status": item.status, "citations": item.citations, "created_at": item.created_at}

def obligation_out(item: Obligation) -> dict:
    today = local_today()
    remaining = (item.due_date - today).days
    state = deadline_state(item.due_date, item.status, today)
    return {"id": item.id, "title": item.title, "description": item.description, "due_date": item.due_date,
            "status": item.status, "priority": item.priority, "deadline_state": state, "days_remaining": remaining}

def verified_citations(db: Session, hits: list[dict], target_date: date) -> list[dict]:
    result = []
    for hit in hits:
        revision = db.scalar(select(RegulatoryRevision).where(RegulatoryRevision.id == hit.get("revision_id")))
        if revision is None or revision.document_id != hit.get("document_id") or revision.effective_from > target_date or (revision.effective_to and target_date >= revision.effective_to):
            continue
        if hit.get("fragment", "") not in revision.content:
            continue
        document = db.scalar(select(RegulatoryDocument).where(RegulatoryDocument.id == revision.document_id))
        if document is None:
            continue
        result.append({"citation_id": f"S{len(result) + 1}", "document_id": document.id,
                       "revision_id": revision.id, "chunk_id": hit.get("chunk_id"), "title": document.title,
                       "section": revision.section, "effective_from": revision.effective_from.isoformat(),
                       "effective_to": revision.effective_to.isoformat() if revision.effective_to else None,
                       "source_url": document.source_url, "fragment": hit["fragment"], "score": hit.get("score")})
    return result

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post(PREFIX + "/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username))
    if user is None or not hmac.compare_digest(user.password_hash, password_hash(data.password)):
        fail(401, "invalid_credentials", "Неверное имя или пароль")
    return {"token": token_for(user), "user": {"username": user.username, "role": user.role, "organization_id": user.organization_id}}

@app.get(PREFIX + "/me")
def me(actor: Actor = Depends(get_actor)):
    return {"username": actor.username, "role": actor.role, "organization_id": actor.organization_id}

@app.get(PREFIX + "/consultations")
def list_consultations(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return [consultation_out(item) for item in db.scalars(select(Consultation).where(Consultation.organization_id == actor.organization_id).order_by(Consultation.created_at.desc())).all()]

@app.post(PREFIX + "/consultations", status_code=201)
async def create_consultation(data: ConsultationIn, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(os.environ.get("RAG_URL", "http://localhost:8001") + "/internal/search", json=data.model_dump(mode="json"))
            response.raise_for_status()
            evidence = verified_citations(db, response.json()["evidence"], data.target_date)
    except (httpx.HTTPError, KeyError, ValueError):
        fail(503, "retrieval_unavailable", "Поиск источников временно недоступен")
    status = "insufficient_evidence"
    answer = None
    if evidence:
        try:
            answer = await get_provider().generate(AIRequest("consultation", data.question, evidence))
            status = "ai_draft"
        except (httpx.HTTPError, KeyError, ValueError, RuntimeError):
            fail(503, "generation_unavailable", "Генерация временно недоступна")
    item = Consultation(organization_id=actor.organization_id, actor_id=actor.id, question=data.question,
                        target_date=data.target_date, status=status, answer=answer, citations=evidence)
    db.add(item)
    db.flush()
    if status == "ai_draft":
        db.add(AIGeneration(organization_id=actor.organization_id, resource="consultation", resource_id=item.id,
                            provider=get_provider().name, model=os.environ.get("AI_MODEL", "mock-v1"), prompt_version="v1",
                            target_date=data.target_date, source_ids=[entry["chunk_id"] for entry in evidence],
                            user_document_ids=[], status="succeeded"))
    audit(db, actor, "consultation", item.id, "created")
    db.commit()
    return consultation_out(item)

@app.get(PREFIX + "/consultations/{item_id}")
def get_consultation(item_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    item = db.scalar(select(Consultation).where(Consultation.id == item_id, Consultation.organization_id == actor.organization_id))
    if item is None:
        fail(404, "not_found", "Консультация не найдена")
    return consultation_out(item)

@app.get(PREFIX + "/obligations")
def list_obligations(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return [obligation_out(item) for item in db.scalars(select(Obligation).where(Obligation.organization_id == actor.organization_id).order_by(Obligation.due_date)).all()]

@app.post(PREFIX + "/obligations", status_code=201)
def create_obligation(data: ObligationIn, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    if data.priority not in {"low", "normal", "high"}:
        fail(422, "invalid_priority", "Недопустимый приоритет")
    item = Obligation(organization_id=actor.organization_id, **data.model_dump())
    db.add(item)
    db.flush()
    audit(db, actor, "obligation", item.id, "created")
    db.commit()
    return obligation_out(item)

@app.post(PREFIX + "/obligations/{item_id}/complete")
def complete_obligation(item_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    item = db.scalar(select(Obligation).where(Obligation.id == item_id, Obligation.organization_id == actor.organization_id))
    if item is None:
        fail(404, "not_found", "Обязательство не найдено")
    item.status = "done"
    audit(db, actor, "obligation", item.id, "completed")
    db.commit()
    return obligation_out(item)

@app.get(PREFIX + "/prescriptions")
def list_prescriptions(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return [{"id": item.id, "title": item.title, "content": item.content} for item in db.scalars(select(Prescription).where(Prescription.organization_id == actor.organization_id)).all()]

@app.post(PREFIX + "/prescriptions", status_code=201)
def create_prescription(data: PrescriptionIn, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    item = Prescription(organization_id=actor.organization_id, **data.model_dump())
    db.add(item)
    db.flush()
    audit(db, actor, "prescription", item.id, "created")
    db.commit()
    return {"id": item.id, "title": item.title, "content": item.content}

@app.get(PREFIX + "/prescriptions/{item_id}/drafts")
def list_drafts(item_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return [draft_out(item) for item in db.scalars(select(Draft).where(Draft.organization_id == actor.organization_id, Draft.prescription_id == item_id).order_by(Draft.created_at.desc())).all()]

@app.get(PREFIX + "/prescriptions/{item_id}/attachments")
def list_attachments(item_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    source = db.scalar(select(Prescription.id).where(Prescription.id == item_id, Prescription.organization_id == actor.organization_id))
    if source is None:
        fail(404, "not_found", "Предписание не найдено")
    items = db.scalars(select(UserDocument).where(UserDocument.prescription_id == item_id,
                 UserDocument.organization_id == actor.organization_id).order_by(UserDocument.created_at)).all()
    return [{"id": item.id, "filename": item.filename, "mime_type": item.mime_type,
             "status": item.status, "created_at": item.created_at} for item in items]

@app.post(PREFIX + "/prescriptions/{item_id}/attachments", status_code=201)
async def upload_attachment(item_id: str, file: UploadFile = File(...), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    source = db.scalar(select(Prescription.id).where(Prescription.id == item_id, Prescription.organization_id == actor.organization_id))
    if source is None:
        fail(404, "not_found", "Предписание не найдено")
    name = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
    raw = await file.read(MAX_FILE_BYTES + 1)
    try:
        text, mime_type = await run_in_threadpool(extract_text, name, raw)
    except DocumentError as exc:
        fail(422, "invalid_document", str(exc))
    count = len(db.scalars(select(UserDocument.id).where(UserDocument.prescription_id == item_id,
                             UserDocument.organization_id == actor.organization_id)).all())
    if count >= 5:
        fail(409, "attachment_limit", "Для одного предписания допускается не более 5 файлов")
    item = UserDocument(organization_id=actor.organization_id, prescription_id=item_id, filename=name,
                        mime_type=mime_type, checksum=hashlib.sha256(raw).hexdigest(), extracted_text=text)
    db.add(item)
    db.flush()
    audit(db, actor, "user_document", item.id, "uploaded")
    db.commit()
    return {"id": item.id, "filename": item.filename, "mime_type": item.mime_type, "status": item.status}

@app.post(PREFIX + "/prescriptions/{item_id}/drafts", status_code=201)
async def create_draft(item_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    source = db.scalar(select(Prescription).where(Prescription.id == item_id, Prescription.organization_id == actor.organization_id))
    if source is None:
        fail(404, "not_found", "Предписание не найдено")
    require_role(actor, "admin", "director", "lawyer")
    attachments = db.scalars(select(UserDocument).where(UserDocument.prescription_id == item_id,
                        UserDocument.organization_id == actor.organization_id, UserDocument.status == "ready")).all()
    documents = [{"id": item.id, "filename": item.filename, "text": item.extracted_text} for item in attachments]
    try:
        content = await get_provider().generate(AIRequest("prescription_draft", source.content, [], documents))
    except (httpx.HTTPError, KeyError, ValueError, RuntimeError):
        fail(503, "generation_unavailable", "Генерация временно недоступна")
    item = Draft(organization_id=actor.organization_id, prescription_id=item_id, content=content, citations=[])
    db.add(item)
    db.flush()
    db.add(AIGeneration(organization_id=actor.organization_id, resource="draft", resource_id=item.id,
                        provider=get_provider().name, model=os.environ.get("AI_MODEL", "mock-v1"), prompt_version="v1",
                        target_date=None, source_ids=[], user_document_ids=[item.id for item in attachments], status="succeeded"))
    audit(db, actor, "draft", item.id, "created")
    db.commit()
    return draft_out(item)

@app.post(PREFIX + "/drafts/{item_id}/review")
def review_draft(item_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    require_role(actor, "admin", "lawyer")
    item = db.scalar(select(Draft).where(Draft.id == item_id, Draft.organization_id == actor.organization_id))
    if item is None:
        fail(404, "not_found", "Черновик не найден")
    if item.status != "draft":
        fail(409, "invalid_transition", "Черновик уже передан на проверку")
    item.status = "legal_review"
    audit(db, actor, "draft", item.id, "submitted_for_review")
    db.commit()
    return draft_out(item)

@app.post(PREFIX + "/drafts/{item_id}/{decision}")
def decide_draft(item_id: str, decision: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    require_role(actor, "admin", "lawyer")
    if decision not in {"approve", "reject"}:
        fail(404, "not_found", "Неизвестное действие")
    item = db.scalar(select(Draft).where(Draft.id == item_id, Draft.organization_id == actor.organization_id))
    if item is None:
        fail(404, "not_found", "Черновик не найден")
    if item.status != "legal_review":
        fail(409, "invalid_transition", "Сначала передайте черновик на проверку")
    item.status = "approved" if decision == "approve" else "rejected"
    audit(db, actor, "draft", item.id, item.status)
    db.commit()
    return draft_out(item)

@app.get(PREFIX + "/sources")
def list_sources(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    rows = db.execute(select(RegulatoryDocument, RegulatoryRevision).join(RegulatoryRevision, RegulatoryDocument.id == RegulatoryRevision.document_id)).all()
    return [{"id": revision.id, "title": document.title, "section": revision.section,
             "effective_from": revision.effective_from, "effective_to": revision.effective_to,
             "source_url": document.source_url, "checksum": revision.checksum} for document, revision in rows]

@app.post(PREFIX + "/sources", status_code=201)
async def create_source(data: RevisionIn, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    require_role(actor, "admin", "lawyer")
    if data.effective_to and data.effective_to <= data.effective_from:
        fail(422, "invalid_interval", "Конец действия должен быть позже начала")
    if data.document_id:
        document = db.scalar(select(RegulatoryDocument).where(RegulatoryDocument.id == data.document_id))
        if document is None:
            fail(404, "not_found", "Документ не найден")
        if document.title != data.title:
            fail(422, "title_mismatch", "Название редакции должно совпадать с документом")
        revisions = db.scalars(select(RegulatoryRevision).where(RegulatoryRevision.document_id == document.id)).all()
        for old in revisions:
            if (old.effective_to is None or data.effective_from < old.effective_to) and (data.effective_to is None or old.effective_from < data.effective_to):
                fail(409, "revision_overlap", "Периоды действия редакций пересекаются")
    else:
        document = RegulatoryDocument(title=data.title, source_url=str(data.source_url) if data.source_url else None)
        db.add(document)
        db.flush()
    revision = RegulatoryRevision(document_id=document.id, section=data.section, effective_from=data.effective_from,
                                  effective_to=data.effective_to, content=data.content,
                                  checksum=hashlib.sha256(data.content.encode()).hexdigest())
    db.add(revision)
    db.flush()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(os.environ.get("RAG_URL", "http://localhost:8001") + "/internal/revisions", json={
                **data.model_dump(mode="json"), "document_id": document.id, "revision_id": revision.id})
            response.raise_for_status()
    except httpx.HTTPError:
        db.rollback()
        fail(503, "index_unavailable", "Не удалось проиндексировать источник")
    audit(db, actor, "regulatory_revision", revision.id, "created")
    db.commit()
    return {"id": revision.id, "document_id": document.id, "indexed_chunks": response.json()["indexed_chunks"]}

@app.post(PREFIX + "/deadline-checks", status_code=202)
def start_deadline_check(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    job = BackgroundJob(organization_id=actor.organization_id, kind="deadline_check")
    db.add(job)
    db.commit()
    try:
        evaluate_deadlines.delay(job.id, actor.organization_id)
    except Exception:
        job.status = "failed"
        job.error = "Очередь задач недоступна"
        db.commit()
        fail(503, "queue_unavailable", "Очередь задач временно недоступна")
    return {"job_id": job.id}

@app.get(PREFIX + "/jobs/{job_id}")
def get_job(job_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id, BackgroundJob.organization_id == actor.organization_id))
    if job is None:
        fail(404, "not_found", "Задача не найдена")
    return {"id": job.id, "kind": job.kind, "status": job.status, "result": job.result, "error": job.error}
