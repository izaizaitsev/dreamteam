from .. import ai
from ..repositories import sqlite as s
from ..core.settings import settings


async def index_case(case_id: str):
    case = s.one("SELECT * FROM cases WHERE id=?", (case_id,))
    if not case:
        raise ValueError("Кейс не найден")
    await ai.upsert_case(case)
    s.execute("UPDATE cases SET indexed_at=?,embedding_model=? WHERE id=?",
              (s.now(), settings.embedding_model, case_id))
