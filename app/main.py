"""Local AI appeal copilot API and review UI."""
from __future__ import annotations
import json
import httpx
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import ai, pipeline as p, storage as s
from .importers import BitrixJsonAdapter, records, normalize_text
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    s.init_db()
    yield


app = FastAPI(title="AI Legal Copilot — входящие обращения", lifespan=lifespan)


def auth(x_api_key: str | None = Header(default=None)):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(401, "Неверный X-API-Key")


def fail(exc: Exception):
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    raise exc


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    return {"status": "ok", "appeals": s.one("SELECT COUNT(*) AS n FROM appeals")["n"]}


@app.get("/health/gigachat")
def health_gigachat():
    return {"configured": bool(settings.gigachat_key), "model": settings.gigachat_model}


@app.get("/health/embedding")
async def health_embedding():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(settings.embedding_url.rstrip("/") + "/health")
            return {"status": "ok" if response.is_success else "unavailable", "http_status": response.status_code}
    except httpx.HTTPError:
        return {"status": "unavailable"}


@app.get("/health/reranker")
async def health_reranker():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(settings.reranker_url.rstrip("/") + "/health")
            return {"status": "ok" if response.is_success else "unavailable", "http_status": response.status_code}
    except httpx.HTTPError:
        return {"status": "unavailable"}


@app.get("/api/config", dependencies=[Depends(auth)])
def config():
    return {"embedding_model": settings.embedding_model, "reranker_model": settings.reranker_model,
            "gigachat_model": settings.gigachat_model, "gigachat_configured": bool(settings.gigachat_key)}


@app.post("/api/import/appeals", dependencies=[Depends(auth)])
async def import_appeals(request: Request):
    try:
        items = records(await request.json())
    except (ValueError, json.JSONDecodeError) as exc:
        fail(exc)
    report = {"total": len(items), "created": 0, "updated": 0, "skipped": 0, "errors": []}
    adapter = BitrixJsonAdapter()
    for index, item in enumerate(items):
        try:
            dto = adapter.convert(item)
            existing = s.one("SELECT id,text,bitrix_status FROM appeals WHERE external_id=?", (dto.external_id,))
            if existing and existing["text"] == dto.text and existing["bitrix_status"] == dto.status:
                report["skipped"] += 1
                continue
            if existing:
                s.execute("UPDATE appeals SET source=?,title=?,text=?,applicant_name=?,applicant_type=?,building_id=?,apartment_id=?,received_at=?,due_at=?,bitrix_status=?,raw_payload=?,updated_at=? WHERE id=?",
                    (dto.source, dto.title, dto.text, dto.applicant_name, dto.applicant_type,
                     dto.building_id, dto.apartment_id, str(dto.received_at) if dto.received_at else None,
                     str(dto.due_at) if dto.due_at else None, dto.status,
                     json.dumps(dto.raw_payload, ensure_ascii=False), s.now(), existing["id"]))
                report["updated"] += 1
                s.audit(existing["id"], "appeal_updated")
            else:
                new_id = s.uid()
                s.execute("INSERT INTO appeals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_id, dto.external_id, dto.source, dto.title, dto.text, dto.applicant_name,
                     dto.applicant_type, dto.building_id, dto.apartment_id,
                     str(dto.received_at) if dto.received_at else None,
                     str(dto.due_at) if dto.due_at else None, dto.status,
                     json.dumps(dto.raw_payload, ensure_ascii=False), "NEW", None, s.now(), s.now()))
                report["created"] += 1
                s.audit(new_id, "appeal_imported")
        except Exception as exc:
            report["errors"].append({"row": index + 1, "message": str(exc)})
    return report


@app.post("/api/import/resolved-cases", dependencies=[Depends(auth)])
async def import_cases(request: Request, index_now: bool = False):
    try:
        items = records(await request.json())
    except (ValueError, json.JSONDecodeError) as exc:
        fail(exc)
    report = {"total": len(items), "created": 0, "updated": 0, "errors": [], "indexed": 0}
    for index, item in enumerate(items):
        try:
            external = str(item.get("external_id") or item.get("ID") or "").strip()
            text = normalize_text(item.get("appeal_text") or item.get("text") or "")
            if not external or not text:
                raise ValueError("Нужны external_id и appeal_text")
            existing = s.one("SELECT id FROM cases WHERE external_id=?", (external,))
            case_id = existing["id"] if existing else s.uid()
            values = (text, item.get("decision_text"), item.get("decision_file_uri"),
                      item.get("category_code"), item.get("source"), item.get("building_id"),
                      json.dumps(item, ensure_ascii=False), s.now())
            if existing:
                s.execute("UPDATE cases SET appeal_text=?,decision_text=?,decision_file_uri=?,category_code=?,source=?,building_id=?,metadata=?,updated_at=?,indexed_at=NULL WHERE id=?",
                          (*values, case_id))
                report["updated"] += 1
            else:
                s.execute("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (case_id, external, text, item.get("decision_text"), item.get("decision_file_uri"),
                     item.get("category_code"), item.get("source"), item.get("building_id"),
                     json.dumps(item, ensure_ascii=False), None, None, s.now(), s.now()))
                report["created"] += 1
            if index_now:
                try:
                    await index_case(case_id)
                    report["indexed"] += 1
                except Exception as exc:
                    report["errors"].append({"row": index + 1, "message": "Индексация: " + str(exc)})
        except Exception as exc:
            report["errors"].append({"row": index + 1, "message": str(exc)})
    return report


async def index_case(case_id: str):
    case = s.one("SELECT * FROM cases WHERE id=?", (case_id,))
    if not case:
        raise ValueError("Кейс не найден")
    await ai.upsert_case(case)
    s.execute("UPDATE cases SET indexed_at=?,embedding_model=? WHERE id=?",
              (s.now(), settings.embedding_model, case_id))


@app.get("/api/appeals", dependencies=[Depends(auth)])
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


@app.get("/api/appeals/{appeal_id}", dependencies=[Depends(auth)])
def detail(appeal_id: str):
    try:
        return p.detail(appeal_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/process", dependencies=[Depends(auth)])
async def process(appeal_id: str):
    try:
        return await p.process(appeal_id)
    except ValueError as exc:
        fail(exc)


@app.post("/api/appeals/{appeal_id}/retrieve", dependencies=[Depends(auth)])
async def retrieve(appeal_id: str):
    try:
        return await p.search(appeal_id)
    except ValueError as exc:
        fail(exc)


@app.post("/api/appeals/{appeal_id}/classify", dependencies=[Depends(auth)])
async def classify(appeal_id: str):
    try:
        return await p.classify(appeal_id)
    except ValueError as exc:
        fail(exc)


@app.post("/api/appeals/{appeal_id}/load-context", dependencies=[Depends(auth)])
def context(appeal_id: str):
    try:
        return p.load_context(appeal_id)
    except ValueError as exc:
        fail(exc)


@app.post("/api/appeals/{appeal_id}/generate-draft", dependencies=[Depends(auth)])
async def generate(appeal_id: str):
    try:
        return await p.generate_draft(appeal_id)
    except ValueError as exc:
        fail(exc)


@app.get("/api/appeals/{appeal_id}/similar-cases", dependencies=[Depends(auth)])
def similar(appeal_id: str):
    return s.latest(appeal_id, "similar_cases") or []


@app.get("/api/appeals/{appeal_id}/context", dependencies=[Depends(auth)])
def context_get(appeal_id: str):
    return s.latest(appeal_id, "context") or []


@app.get("/api/appeals/{appeal_id}/draft", dependencies=[Depends(auth)])
def draft_get(appeal_id: str):
    return p.detail(appeal_id)["draft"]


class DraftEdit(BaseModel):
    text: str = Field(min_length=1)
    actor: str = Field(min_length=1)


@app.put("/api/drafts/{draft_id}", dependencies=[Depends(auth)])
def edit_draft(draft_id: str, body: DraftEdit):
    draft = s.one("SELECT * FROM drafts WHERE id=?", (draft_id,))
    if not draft:
        raise HTTPException(404, "Черновик не найден")
    if draft["status"] != "PENDING":
        raise HTTPException(409, "Черновик уже рассмотрен")
    s.execute("UPDATE drafts SET edited_text=? WHERE id=?", (body.text, draft_id))
    s.audit(draft["appeal_id"], "draft_edited", body.actor, {"draft_id": draft_id})
    return {"status": "saved"}


class Review(BaseModel):
    actor: str = Field(min_length=1)
    text: str | None = None


def review_draft(draft_id: str, body: Review, state: str):
    draft = s.one("SELECT * FROM drafts WHERE id=?", (draft_id,))
    if not draft:
        raise HTTPException(404, "Черновик не найден")
    if draft["status"] != "PENDING":
        raise HTTPException(409, "Черновик уже рассмотрен")
    final = body.text or draft["edited_text"]
    s.execute("UPDATE drafts SET edited_text=?,status=?,reviewer=?,reviewed_at=? WHERE id=?",
              (final, state, body.actor, s.now(), draft_id))
    p.set_status(draft["appeal_id"], "APPROVED" if state == "APPROVED" else "REJECTED")
    s.audit(draft["appeal_id"], "draft_" + state.lower(), body.actor,
            {"draft_id": draft_id, "changed": final != json.loads(draft["ai_payload"])["full_text"]})
    return {"status": state, "draft_id": draft_id}


@app.post("/api/drafts/{draft_id}/approve", dependencies=[Depends(auth)])
def approve(draft_id: str, body: Review):
    return review_draft(draft_id, body, "APPROVED")


@app.post("/api/drafts/{draft_id}/reject", dependencies=[Depends(auth)])
def reject(draft_id: str, body: Review):
    return review_draft(draft_id, body, "REJECTED")


class ResolveInput(BaseModel):
    actor: str = Field(min_length=1)
    decision_file_uri: str | None = None
    index_now: bool = False


@app.post("/api/appeals/{appeal_id}/mark-resolved", dependencies=[Depends(auth)])
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
    if existing:
        s.execute("UPDATE cases SET appeal_text=?,decision_text=?,decision_file_uri=?,category_code=?,indexed_at=NULL,updated_at=? WHERE id=?",
            (row["text"], draft["edited_text"], body.decision_file_uri, category, s.now(), case_id))
    else:
        s.execute("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (case_id, row["external_id"], row["text"], draft["edited_text"],
             body.decision_file_uri, category, row["source"], row["building_id"],
             json.dumps({"origin_appeal_id": appeal_id}, ensure_ascii=False), None, None, s.now(), s.now()))
    s.audit(appeal_id, "resolved", body.actor, {"case_id": case_id, "decision_file_uri": body.decision_file_uri})
    indexed = False
    if body.index_now:
        try:
            await index_case(case_id)
            indexed = True
        except Exception as exc:
            return {"case_id": case_id, "indexed": False, "index_error": str(exc)}
    return {"case_id": case_id, "indexed": indexed}


@app.get("/api/templates", dependencies=[Depends(auth)])
def templates():
    return s.all_rows("SELECT * FROM templates ORDER BY code,version DESC")


class TemplateInput(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category_code: str | None = None
    body: str = Field(min_length=1)
    required_context: list[dict] = []
    active: bool = True


@app.post("/api/templates", dependencies=[Depends(auth)])
def create_template(body: TemplateInput):
    version = s.one("SELECT MAX(version) AS n FROM templates WHERE code=?", (body.code,))["n"] or 0
    template_id = s.uid()
    s.execute("INSERT INTO templates VALUES (?,?,?,?,?,?,?,?,?)",
        (template_id, body.code, body.name, body.category_code, body.body,
         json.dumps(body.required_context, ensure_ascii=False), int(body.active), version + 1, s.now()))
    s.audit(None, "template_created", details={"template_id": template_id, "code": body.code})
    return {"id": template_id, "version": version + 1}


@app.put("/api/templates/{template_id}", dependencies=[Depends(auth)])
def update_template(template_id: str, body: TemplateInput):
    if not s.one("SELECT id FROM templates WHERE id=?", (template_id,)):
        raise HTTPException(404, "Шаблон не найден")
    return create_template(body)


@app.get("/api/index/status", dependencies=[Depends(auth)])
def index_status():
    return s.one("SELECT COUNT(*) AS total, SUM(CASE WHEN indexed_at IS NOT NULL THEN 1 ELSE 0 END) AS indexed FROM cases")


@app.post("/api/index/upsert", dependencies=[Depends(auth)])
async def index_upsert():
    cases = s.all_rows("SELECT id FROM cases WHERE indexed_at IS NULL")
    report = {"total": len(cases), "indexed": 0, "errors": []}
    for case in cases:
        try:
            await index_case(case["id"])
            report["indexed"] += 1
        except Exception as exc:
            report["errors"].append({"id": case["id"], "message": str(exc)})
    return report


@app.post("/api/index/rebuild", dependencies=[Depends(auth)])
async def index_rebuild():
    s.execute("UPDATE cases SET indexed_at=NULL")
    return await index_upsert()


@app.get("/api/audit", dependencies=[Depends(auth)])
def audit(appeal_id: str | None = None):
    if appeal_id:
        return s.all_rows("SELECT * FROM audit WHERE appeal_id=? ORDER BY created_at DESC LIMIT 200", (appeal_id,))
    return s.all_rows("SELECT * FROM audit ORDER BY created_at DESC LIMIT 200")
