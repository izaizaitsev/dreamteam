"""Explicit, reviewable stages of appeal processing."""
from __future__ import annotations
import json
from . import ai, storage as s
from .settings import settings

CLASSIFIER_PROMPT = """Ты помощник юридического отдела управляющей компании. Классифицируй обращение.
Не принимай окончательное решение и не выдумывай факты. Похожие кейсы являются примерами практики,
не источником фактов о текущем обращении. Верни JSON с полями legal_required (bool),
case_type (typical|disputed|unknown), category ({code,name}), confidence (0..1),
reasoning_summary, recommended_template_code, required_context ([{key,reason,required}]), warnings.
Доступные ключи контекста: work_history, dispatch_requests, previous_appeals, building_info.
Запрашивай только нужные ключи."""
DRAFT_PROMPT = """Ты помощник юридического отдела управляющей компании. Создай только проект ответа.
Не выдумывай факты, работы, даты, документы, нормы или данные заявителя. Похожие обращения служат
примерами практики; запрещено переносить из них конкретные факты. Если данных нет, перечисли их
в missing_information; противоречия перечисли в warnings. Верни JSON с полями subject,
issue_summary, factual_section, work_section, legal_section, closing_section, full_text,
used_case_ids, used_context_keys, missing_information, warnings, confidence (0..1)."""

TOOL_KEYS = {"work_history", "dispatch_requests", "previous_appeals", "building_info"}


def appeal(appeal_id: str) -> dict:
    row = s.one("SELECT * FROM appeals WHERE id=?", (appeal_id,))
    if not row:
        raise ValueError("Обращение не найдено")
    return row


def set_status(appeal_id: str, status: str, error: str | None = None):
    s.execute("UPDATE appeals SET status=?,error=?,updated_at=? WHERE id=?",
              (status, error, s.now(), appeal_id))
    s.audit(appeal_id, "stage", details={"stage": status, "error": error})


async def search(appeal_id: str) -> list[dict]:
    row = appeal(appeal_id)
    set_status(appeal_id, "EMBEDDING")
    vector = await ai.embed(row["text"], query=True)
    set_status(appeal_id, "RETRIEVAL")
    hits = await ai.retrieve(vector)
    cases = []
    for hit in hits:
        case = s.one("SELECT * FROM cases WHERE id=?", (hit["id"],))
        if case:
            cases.append({**case, **hit})
    set_status(appeal_id, "RERANKING")
    ranked = await ai.rerank(row["text"], cases)
    s.result(appeal_id, "similar_cases", ranked, settings.reranker_model)
    return ranked


def template_for(classification: dict) -> dict | None:
    code = classification.get("recommended_template_code")
    if code:
        row = s.one("SELECT * FROM templates WHERE code=? AND active=1 ORDER BY version DESC LIMIT 1", (code,))
        if row:
            return row
    return s.one("SELECT * FROM templates WHERE category_code=? AND active=1 ORDER BY version DESC LIMIT 1",
                 (classification["category"]["code"],))


async def classify(appeal_id: str) -> dict:
    row = appeal(appeal_id)
    set_status(appeal_id, "CLASSIFYING")
    cases = s.latest(appeal_id, "similar_cases") or []
    templates = s.all_rows("SELECT code,name,category_code FROM templates WHERE active=1")
    payload = {"appeal": {"text": ai.llm_text(row["text"]), "source": row["source"],
                          "building_id": row["building_id"]},
               "similar_cases": [{"id": c["id"], "appeal_text": ai.llm_text(c["appeal_text"]),
                                  "decision_text": ai.llm_text(c["decision_text"] or "")}
                                 for c in cases], "templates": templates}
    parsed, usage = await ai.gigachat.structured(ai.Classification, CLASSIFIER_PROMPT, payload)
    if parsed.case_type not in {"typical", "disputed", "unknown"}:
        raise ValueError("Недопустимый case_type")
    data = parsed.model_dump()
    if data["recommended_template_code"] and not template_for(data):
        data["warnings"].append("Рекомендованный шаблон недоступен")
    s.result(appeal_id, "classification", data, settings.gigachat_model, "classifier-v1")
    s.audit(appeal_id, "classification", details={"model": settings.gigachat_model, "usage": usage})
    set_status(appeal_id, "CONTEXT_REQUIRED" if parsed.legal_required else "READY_FOR_REVIEW")
    return data


def load_context(appeal_id: str) -> list[dict]:
    row = appeal(appeal_id)
    classification = s.latest(appeal_id, "classification")
    if not classification:
        raise ValueError("Сначала выполните классификацию")
    set_status(appeal_id, "CONTEXT_LOADING")
    raw = json.loads(row["raw_payload"])
    context = []
    for request in classification["required_context"]:
        key = request["key"]
        if key not in TOOL_KEYS:
            context.append({"key": key, "status": "unavailable", "source": "tool registry",
                            "data": None, "warning": "Инструмент не разрешён"})
            continue
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
    classification = s.latest(appeal_id, "classification")
    if not classification or not classification["legal_required"]:
        raise ValueError("Для обращения не требуется юридический черновик")
    context = s.latest(appeal_id, "context") or load_context(appeal_id)
    template = template_for(classification)
    similar = s.latest(appeal_id, "similar_cases") or []
    set_status(appeal_id, "DRAFTING")
    payload = {"appeal": {"text": ai.llm_text(row["text"]), "title": row["title"],
                          "applicant_name": ai.llm_text(row["applicant_name"] or ""),
                          "received_at": row["received_at"]},
               "classification": classification, "template": template["body"] if template else None,
               "context": context,
               "similar_cases": [{"id": c["id"], "appeal_text": ai.llm_text(c["appeal_text"]),
                                  "decision_text": ai.llm_text(c["decision_text"] or "")}
                                 for c in similar]}
    parsed, usage = await ai.gigachat.structured(ai.Draft, DRAFT_PROMPT, payload)
    data = parsed.model_dump()
    allowed_cases = {c["id"] for c in similar}
    data["used_case_ids"] = [x for x in data["used_case_ids"] if x in allowed_cases]
    allowed_context = {c["key"] for c in context if c["status"] == "available"}
    data["used_context_keys"] = [x for x in data["used_context_keys"] if x in allowed_context]
    if not template:
        data["warnings"].append("Шаблон не найден; проверьте оформление")
    for item in context:
        if item["status"] != "available" and item["key"] not in data["missing_information"]:
            data["missing_information"].append(item["key"])
    draft_id = s.uid()
    s.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?)",
              (draft_id, appeal_id, json.dumps(data, ensure_ascii=False), data["full_text"],
               "PENDING", None, None, s.now()))
    s.result(appeal_id, "draft", {"draft_id": draft_id, **data}, settings.gigachat_model, "draft-v1")
    s.audit(appeal_id, "draft_generated", details={"draft_id": draft_id,
            "model": settings.gigachat_model, "usage": usage, "template_id": template["id"] if template else None})
    set_status(appeal_id, "READY_FOR_REVIEW")
    return {"draft_id": draft_id, **data}


async def process(appeal_id: str):
    try:
        await search(appeal_id)
        classification = await classify(appeal_id)
        if classification["legal_required"]:
            load_context(appeal_id)
            await generate_draft(appeal_id)
        return detail(appeal_id)
    except Exception as exc:
        current = appeal(appeal_id)["status"]
        set_status(appeal_id, "ERROR", f"{current}: {exc}")
        raise


def detail(appeal_id: str) -> dict:
    row = appeal(appeal_id)
    row["raw_payload"] = json.loads(row["raw_payload"])
    row["classification"] = s.latest(appeal_id, "classification")
    row["similar_cases"] = s.latest(appeal_id, "similar_cases") or []
    row["context"] = s.latest(appeal_id, "context") or []
    draft = s.one("SELECT * FROM drafts WHERE appeal_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (appeal_id,))
    if draft:
        draft["ai_payload"] = json.loads(draft["ai_payload"])
    row["draft"] = draft
    row["audit"] = s.all_rows("SELECT * FROM audit WHERE appeal_id=? ORDER BY created_at DESC", (appeal_id,))
    return row
