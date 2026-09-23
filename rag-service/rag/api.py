import hashlib
import os
import re
from datetime import date
from uuid import uuid4
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from .db import get_db
from .docx import MAX_BYTES
from .models import Document, IngestionJob, Passage, Revision
from .storage import read_original, store_original
from .worker import process_ingestion_task

app = FastAPI(title="RAG document service", version="0.1.0")

def internal_auth(x_internal_token: str = Header(default="")):
    if not x_internal_token or x_internal_token != os.environ.get("RAG_INTERNAL_TOKEN"):
        raise HTTPException(status_code=401, detail="Internal authentication required")

class SearchIn(BaseModel):
    question: str = Field(min_length=3, max_length=5000)
    organization_id: str
    document_categories: list[str] = Field(default_factory=lambda: ["normative"])
    as_of_date: date | None = None

def document_out(db: Session, document: Document, revision: Revision) -> dict:
    passages = db.scalars(select(Passage).where(Passage.revision_id == revision.id).order_by(Passage.ordinal)).all()
    relevant = next((p for p in passages if any(word in p.fragment.lower() for word in ("срок", "исполн", "до "))), passages[0] if passages else None)
    return {"document_id": document.id, "revision_id": revision.id, "document_category": document.category,
            "title": document.title, "filename": revision.filename, "status": revision.status,
            "date_provenance": revision.date_provenance, "valid_from": revision.valid_from,
            "valid_to": revision.valid_to, "due_date": revision.due_date,
            "source_fragment": relevant.fragment if relevant else None,
            "source_passage_id": relevant.id if relevant else None,
            "original_url": f"/api/v1/documents/{revision.id}/original", "source_url": document.source_url}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/internal/documents", dependencies=[Depends(internal_auth)], status_code=202)
async def submit_document(organization_id: str = Form(...), document_category: str = Form(...),
                          title: str = Form(...), file: UploadFile = File(...),
                          document_id: str | None = Form(default=None),
                          db: Session = Depends(get_db)):
    if document_category not in {"normative", "obligation"}:
        raise HTTPException(status_code=422, detail="Invalid document_category")
    if not title.strip() or len(title) > 300:
        raise HTTPException(status_code=422, detail="Invalid title")
    filename = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
    raw = await file.read(MAX_BYTES + 1)
    if not filename.lower().endswith(".docx") or not raw.startswith(b"PK") or len(raw) > MAX_BYTES:
        raise HTTPException(status_code=422, detail="Expected DOCX up to 10 MB")
    checksum = hashlib.sha256(raw).hexdigest()
    existing = db.scalar(select(Revision).where(Revision.organization_id == organization_id,
        Revision.category == document_category, Revision.checksum == checksum))
    if existing:
        document = db.scalar(select(Document).where(Document.id == existing.document_id))
        if document is None or document.title != title or (document_id and document_id != document.id):
            raise HTTPException(status_code=409, detail="Duplicate content with conflicting metadata")
        job = db.scalar(select(IngestionJob).where(IngestionJob.revision_id == existing.id).order_by(desc(IngestionJob.created_at)))
        return {"job_id": job.id, "document_id": document.id, "revision_id": existing.id, "status": job.status}
    if document_id:
        document = db.scalar(select(Document).where(Document.id == document_id,
            Document.organization_id == organization_id))
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if document.category != document_category or document.title != title:
            raise HTTPException(status_code=409, detail="Category or title mismatch")
    else:
        document = Document(organization_id=organization_id, category=document_category, title=title.strip())
        db.add(document)
        db.flush()
    revision_id = str(uuid4())
    object_key = f"{organization_id}/{revision_id}/{checksum}.docx"
    try:
        await run_in_threadpool(store_original, document_category, object_key, raw)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Original storage unavailable") from exc
    revision = Revision(id=revision_id, document_id=document.id, organization_id=organization_id,
        category=document_category, filename=filename, checksum=checksum, object_key=object_key,
        extracted_text="", date_provenance="demo_random_unverified", status="received")
    db.add(revision)
    db.flush()
    job = IngestionJob(organization_id=organization_id, revision_id=revision_id, stage="received", status="queued")
    db.add(job)
    db.commit()
    try:
        process_ingestion_task.delay({"schema_version": 1, "kind": "rag_ingestion", "job_id": job.id,
            "revision_id": revision_id, "organization_id": organization_id})
    except Exception:
        job.status = "failed"
        job.error_code = "queue_unavailable"
        job.error_message = "Очередь обработки недоступна"
        db.commit()
        raise HTTPException(status_code=503, detail="Ingestion queue unavailable") from None
    return {"job_id": job.id, "document_id": document.id, "revision_id": revision_id, "status": "queued"}

@app.get("/internal/jobs/{job_id}", dependencies=[Depends(internal_auth)])
def get_job(job_id: str, organization_id: str, db: Session = Depends(get_db)):
    job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id,
        IngestionJob.organization_id == organization_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"id": job.id, "revision_id": job.revision_id, "status": job.status, "stage": job.stage,
            "error_code": job.error_code, "error_message": job.error_message}

@app.get("/internal/documents", dependencies=[Depends(internal_auth)])
def list_documents(organization_id: str, document_category: str | None = None, db: Session = Depends(get_db)):
    if document_category and document_category not in {"normative", "obligation"}:
        raise HTTPException(status_code=422, detail="Invalid document_category")
    statement = select(Document, Revision).join(Revision, Revision.document_id == Document.id).where(
        Document.organization_id == organization_id, Revision.organization_id == organization_id)
    if document_category:
        statement = statement.where(Document.category == document_category)
    return [document_out(db, document, revision) for document, revision in db.execute(statement.order_by(Revision.created_at.desc())).all()]

@app.get("/internal/documents/{revision_id}", dependencies=[Depends(internal_auth)])
def get_document(revision_id: str, organization_id: str, db: Session = Depends(get_db)):
    row = db.execute(select(Document, Revision).join(Revision, Revision.document_id == Document.id).where(
        Revision.id == revision_id, Revision.organization_id == organization_id,
        Document.organization_id == organization_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document, revision = row
    return {**document_out(db, document, revision), "extracted_text": revision.extracted_text}

@app.get("/internal/documents/{revision_id}/original", dependencies=[Depends(internal_auth)])
def get_original(revision_id: str, organization_id: str, db: Session = Depends(get_db)):
    revision = db.scalar(select(Revision).where(Revision.id == revision_id,
        Revision.organization_id == organization_id))
    if revision is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        raw = read_original(revision.category, revision.object_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Original unavailable") from exc
    return Response(content=raw, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{revision.id}.docx"'})

@app.post("/internal/search", dependencies=[Depends(internal_auth)])
def search(data: SearchIn, db: Session = Depends(get_db)):
    if not data.document_categories or any(category not in {"normative", "obligation"} for category in data.document_categories):
        raise HTTPException(status_code=422, detail="Invalid document_categories")
    terms = list(dict.fromkeys(re.findall(r"[\w]{3,}", data.question.lower())))[:16]
    if not terms:
        return {"evidence": [], "scope": {"document_categories": data.document_categories}, "limitations": ["Нет значимых слов для поиска"]}
    query = func.to_tsquery("russian", " | ".join(terms))
    vector = func.to_tsvector("russian", Passage.fragment)
    rows = db.execute(select(Document, Revision, Passage,
        func.ts_rank_cd(vector, query).label("score")).join(Revision, Revision.document_id == Document.id)
        .join(Passage, Passage.revision_id == Revision.id)
        .where(Document.organization_id == data.organization_id,
               Revision.organization_id == data.organization_id,
               Passage.organization_id == data.organization_id,
               Revision.status == "published_demo", Passage.category.in_(data.document_categories),
               Document.category.in_(data.document_categories), vector.op("@@")(query))
        .order_by(desc("score")).limit(20)).all()
    evidence = []
    for document, revision, passage, score in rows:
        if revision.date_provenance == "confirmed" and data.as_of_date:
            if revision.category == "normative" and (revision.valid_from is None or revision.valid_from > data.as_of_date or (revision.valid_to and revision.valid_to <= data.as_of_date)):
                continue
            if revision.category == "obligation" and revision.due_date is None:
                continue
        evidence.append({"citation_id": f"S{len(evidence) + 1}", "document_category": document.category,
            "document_id": document.id, "revision_id": revision.id, "passage_id": passage.id,
            "title": document.title, "section": passage.section, "fragment": passage.fragment,
            "effective_from": revision.valid_from.isoformat() if revision.valid_from else None,
            "effective_to": revision.valid_to.isoformat() if revision.valid_to else None,
            "due_date": revision.due_date.isoformat() if revision.due_date else None,
            "date_provenance": revision.date_provenance,
            "source_url": document.source_url,
            "original_url": f"/api/v1/documents/{revision.id}/original", "score": float(score)})
        if len(evidence) == 5:
            break
    limitations = ["Даты загруженных документов созданы демозаглушкой и не подтверждены"] if any(
        item["date_provenance"] != "confirmed" for item in evidence) else []
    return {"evidence": evidence, "scope": {"document_categories": data.document_categories,
        "as_of_date": data.as_of_date}, "limitations": limitations}
