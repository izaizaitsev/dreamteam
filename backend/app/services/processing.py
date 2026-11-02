"""Explicit, reviewable stages of appeal processing."""
from __future__ import annotations
import json
import logging
import re
from datetime import datetime
from .. import ai
from ..repositories import sqlite as s
from ..core.settings import settings
from .draft_prompt import DRAFT_PROMPT, PROMPT_VERSION

logger = logging.getLogger("uvicorn.error")

def similar_with_dates(cases: list[dict]) -> list[dict]:
    """Use the source appeal date, never the date the case was imported."""
    result = []
    for case in cases:
        stored = s.one("SELECT metadata FROM cases WHERE id=?", (case["id"],))
        metadata = json.loads((stored or case).get("metadata") or "{}")
        origin = s.one("SELECT received_at FROM appeals WHERE id=?",
                       (metadata.get("origin_appeal_id"),))
        value = (origin or {}).get("received_at") or metadata.get("received_at") or metadata.get("DATE_CREATE") or metadata.get("date")
        received_at = None
        if isinstance(value, str):
            try:
                received_at = datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
            except ValueError:
                for pattern in ("%d.%m.%Y", "%d.%m.%Y %H:%M:%S"):
                    try:
                        received_at = datetime.strptime(value, pattern).isoformat()
                        break
                    except ValueError:
                        continue
        result.append({**case, "received_at": received_at})
    return result

TOOL_KEYS = {"work_history", "dispatch_requests", "previous_appeals", "building_info"}
TEMPLATE_FIELD = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def render_template(body: str, row: dict, draft: dict) -> tuple[str, list[str], list[str]]:
    raw = json.loads(row["raw_payload"])
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    template_fields = raw.get("template_fields") if isinstance(raw.get("template_fields"), dict) else {}
    values = {
        "title": row["title"], "applicant_name": row["applicant_name"],
        "building_id": row["building_id"], "apartment_id": row["apartment_id"],
        "received_at": row["received_at"], "appeal_text": row["text"],
        "body": draft.get("body"), "closing": draft.get("closing"),
        **{key: context.get(key) for key in TOOL_KEYS},
        **{key: draft.get(key) for key in (
            "subject", "issue_summary", "factual_section", "work_section",
            "legal_section", "closing_section")},
    }
    values.update({key: value for key, value in template_fields.items()
                   if key not in values and isinstance(value, (str, int, float))})
    for key, value in draft.get("header", {}).items():
        if not values.get(key):
            values[key] = value
    missing = []
    used_context = []

    def replace(match: re.Match) -> str:
        key = match.group(1)
        value = values.get(key)
        if value is None or value == "":
            if key not in missing:
                missing.append(key)
            return "________"
        if key in TOOL_KEYS and key not in used_context:
            used_context.append(key)
        return str(value) if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    return TEMPLATE_FIELD.sub(replace, body), missing, used_context


def appeal(appeal_id: str) -> dict:
    row = s.one("SELECT * FROM appeals WHERE id=?", (appeal_id,))
    if not row:
        raise ValueError("Обращение не найдено")
    return row


def set_status(appeal_id: str, status: str, error: str | None = None):
    logger.info("Appeal processing: appeal_id=%s stage=%s failed=%s", appeal_id, status, bool(error))
    s.execute("UPDATE appeals SET status=?,error=?,updated_at=? WHERE id=?",
              (status, error, s.now(), appeal_id))
    s.audit(appeal_id, "stage", details={"stage": status, "error": error})


async def search(appeal_id: str) -> list[dict]:
    row = appeal(appeal_id)
    previous_status = row["status"] if row["status"] in {
        "NEW", "READY_FOR_REVIEW", "APPROVED", "REJECTED", "CONTEXT_REQUIRED"} else "NEW"
    set_status(appeal_id, "EMBEDDING")
    vector = await ai.embed(row["text"], query=True)
    set_status(appeal_id, "RETRIEVAL")
    hits = await ai.retrieve(vector)
    cases = []
    for hit in hits:
        case = s.one("SELECT * FROM cases WHERE id=?", (hit["id"],))
        if case:
            cases.append({**case, **hit})
    ranked = similar_with_dates(cases[:settings.retrieval_top_k])
    s.result(appeal_id, "similar_cases", ranked, settings.embedding_model)
    set_status(appeal_id, previous_status)
    return ranked


def template_for(row: dict) -> dict | None:
    # Template selection is explicit import metadata, never an AI classification.
    raw = json.loads(row["raw_payload"])
    code = raw.get("template_code")
    if not isinstance(code, str) or not code.strip():
        return None
    template = s.one("SELECT * FROM templates WHERE code=? AND active=1 ORDER BY version DESC LIMIT 1", (code,))
    if not template:
        raise ValueError("Указанный template_code не найден среди активных шаблонов")
    return template

def load_context(appeal_id: str) -> list[dict]:
    row = appeal(appeal_id)
    set_status(appeal_id, "CONTEXT_LOADING")
    raw = json.loads(row["raw_payload"])
    context = []
    for key in sorted(TOOL_KEYS):
        # Until real internal integrations are supplied, only imported facts are returned.
        value = raw.get("context", {}).get(key) if isinstance(raw.get("context"), dict) else None
        if key == "building_info" and not value and row["building_id"]:
            value = {"building_id": row["building_id"]}
        context.append({"key": key, "status": "available" if value else "missing",
                        "source": "Bitrix24 import" if value else "no connected source",
                        "data": value, "warning": None if value else "Данные отсутствуют; требуется ручная проверка"})
    s.result(appeal_id, "context", context)
    set_status(appeal_id, "CONTEXT_REQUIRED")
    return context


async def generate_draft(appeal_id: str) -> dict:
    row = appeal(appeal_id)
    context = load_context(appeal_id)
    template = template_for(row)
    similar = s.latest(appeal_id, "similar_cases") or []
    # Only completed responses are useful as examples; preserve retrieval order.
    examples = [case for case in similar if (case.get("decision_text") or "").strip()][:3]
    raw = json.loads(row["raw_payload"])
    source_fields = raw.get("template_fields") if isinstance(raw.get("template_fields"), dict) else {}
    section_keys = {"subject", "issue_summary", "factual_section", "work_section",
                    "legal_section", "closing_section", "body", "closing", "full_text"}
    header_keys = sorted(set(TEMPLATE_FIELD.findall(template["body"])) - section_keys - TOOL_KEYS - {"appeal_text"}) if template else [
        "recipient_name", "recipient_address", "outgoing_number", "outgoing_date", "sender_name", "signatory_name"]
    known_values = {**source_fields, **{key: row.get(key) for key in (
        "title", "applicant_name", "building_id", "apartment_id", "received_at") if row.get(key)}}
    header_values = {key: str(known_values[key]) for key in header_keys
                     if isinstance(known_values.get(key), (str, int, float)) and known_values[key] != ""}
    header_schema = {"type": "object", "properties": {
        key: {"type": ["string", "null"]} for key in header_keys},
        "required": header_keys, "additionalProperties": False}
    response_schema = ai.Draft.model_json_schema()
    response_schema["properties"]["header"] = header_schema
    set_status(appeal_id, "DRAFTING")
    payload = {"appeal": {"text": ai.llm_text(row["text"]), "title": row["title"],
                          "applicant_name": ai.llm_text(row["applicant_name"] or ""),
                          "received_at": row["received_at"]},
               "legal_required": True, "template": template["body"] if template else None,
               "template_id": template["code"] if template else None,
               "template_fields": sorted(set(TEMPLATE_FIELD.findall(template["body"]))) if template else [],
               "header_schema": header_schema, "header_values": header_values,
               "response_schema": response_schema,
               "drafting_task": raw.get("drafting_task") or "Подготовь ответ по существу обращения и уместное правовое обоснование.",
               "legal_sources": raw.get("legal_sources") or [],
               "context": context,
               "similar_cases": [{"id": c["id"], "appeal_text": ai.llm_text(c["appeal_text"]),
                                  "decision_text": ai.llm_text(c["decision_text"] or "")}
                                 for c in examples]}
    parsed, usage = await ai.gigachat.structured(ai.Draft, DRAFT_PROMPT, payload)
    data = parsed.model_dump()
    data["closing_section"] = data["closing_section"] or data["closing"] or ""
    # The model returns structure; the application controls document assembly.
    header_text = "\n".join(value for value in data["header"].values() if value)
    data["full_text"] = "\n\n".join(part.strip() for part in (
        header_text, data["subject"], data["body"], data["closing"] or "") if part.strip())
    allowed_cases = {c["id"] for c in examples}
    data["used_case_ids"] = [x for x in data["used_case_ids"] if x in allowed_cases]
    allowed_context = {c["key"] for c in context if c["status"] == "available"}
    data["used_context_keys"] = [x for x in data["used_context_keys"] if x in allowed_context]
    if template:
        data["full_text"], missing_fields, used_context = render_template(template["body"], row, data)
        data["template_code"] = template["code"]
        data["template_version"] = template["version"]
        for key in missing_fields:
            if key not in data["missing_information"]:
                data["missing_information"].append(key)
        for key in used_context:
            if key not in data["used_context_keys"]:
                data["used_context_keys"].append(key)
    else:
        if not data["full_text"].strip():
            raise ValueError("GigaChat не вернул текст черновика")
        data["warnings"].append("Шаблон не найден; проверьте оформление")
    for item in context:
        if item["status"] != "available" and item["key"] not in data["missing_information"]:
            data["missing_information"].append(item["key"])
    draft_id = s.uid()
    s.execute("INSERT INTO drafts (id,appeal_id,ai_payload,edited_text,status,reviewer,reviewed_at,created_at) VALUES (?,?,?,?,?,?,?,?)",
              (draft_id, appeal_id, json.dumps(data, ensure_ascii=False), data["full_text"],
               "PENDING", None, None, s.now()))
    s.result(appeal_id, "draft", {"draft_id": draft_id, **data}, settings.gigachat_model, PROMPT_VERSION)
    s.audit(appeal_id, "draft_generated", details={"draft_id": draft_id,
            "model": settings.gigachat_model, "usage": usage, "template_id": template["id"] if template else None})
    set_status(appeal_id, "READY_FOR_REVIEW")
    return {"draft_id": draft_id, **data}


async def process(appeal_id: str):
    try:
        await search(appeal_id)
        await generate_draft(appeal_id)
        return detail(appeal_id)
    except Exception as exc:
        row = s.one("SELECT status FROM appeals WHERE id=?", (appeal_id,))
        if row:
            set_status(appeal_id, "ERROR", f"{row['status']}: {exc}")
        raise


def detail(appeal_id: str) -> dict:
    row = appeal(appeal_id)
    row["raw_payload"] = json.loads(row["raw_payload"])
    row["legal_required"] = True
    row["similar_cases"] = similar_with_dates(s.latest(appeal_id, "similar_cases") or [])
    row["context"] = s.latest(appeal_id, "context") or []
    draft = s.one("SELECT * FROM drafts WHERE appeal_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (appeal_id,))
    if draft:
        draft["ai_payload"] = json.loads(draft["ai_payload"])
        draft["ai_payload"].pop("confidence", None)
    row["draft"] = draft
    row["audit"] = s.all_rows("SELECT * FROM audit WHERE appeal_id=? ORDER BY created_at DESC", (appeal_id,))
    return row
