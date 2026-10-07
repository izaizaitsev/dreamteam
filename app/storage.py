"""Small transactional store for the local MVP."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .settings import settings


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return str(uuid.uuid4())


SCHEMA = """
CREATE TABLE IF NOT EXISTS appeals (
 id TEXT PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, source TEXT NOT NULL,
 title TEXT, text TEXT NOT NULL, applicant_name TEXT, applicant_type TEXT,
 building_id TEXT, apartment_id TEXT, received_at TEXT, due_at TEXT,
 bitrix_status TEXT, raw_payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'NEW',
 error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
 id TEXT PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, appeal_text TEXT NOT NULL,
 decision_text TEXT, decision_file_uri TEXT, category_code TEXT, source TEXT,
 building_id TEXT, metadata TEXT NOT NULL, indexed_at TEXT, embedding_model TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS templates (
 id TEXT PRIMARY KEY, code TEXT NOT NULL, name TEXT NOT NULL, category_code TEXT,
 body TEXT NOT NULL, required_context TEXT NOT NULL DEFAULT '[]',
 active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, UNIQUE(code,version)
);
CREATE TABLE IF NOT EXISTS results (
 id TEXT PRIMARY KEY, appeal_id TEXT NOT NULL, kind TEXT NOT NULL,
 payload TEXT NOT NULL, model TEXT, prompt_version TEXT,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS results_appeal_kind ON results(appeal_id,kind,created_at);
CREATE TABLE IF NOT EXISTS drafts (
 id TEXT PRIMARY KEY, appeal_id TEXT NOT NULL, ai_payload TEXT NOT NULL,
 edited_text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
 reviewer TEXT, reviewed_at TEXT, created_at TEXT NOT NULL,
 document_uri TEXT
);
CREATE INDEX IF NOT EXISTS drafts_appeal ON drafts(appeal_id,created_at);
CREATE TABLE IF NOT EXISTS audit (
 id TEXT PRIMARY KEY, appeal_id TEXT, action TEXT NOT NULL,
 actor TEXT, details TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_appeal ON audit(appeal_id,created_at);
"""


@contextmanager
def db():
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(drafts)")}
        if "document_uri" not in columns:
            conn.execute("ALTER TABLE drafts ADD COLUMN document_uri TEXT")


def one(query: str, params: tuple = ()) -> dict | None:
    with db() as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def all_rows(query: str, params: tuple = ()) -> list[dict]:
    with db() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def execute(query: str, params: tuple = ()):
    with db() as conn:
        conn.execute(query, params)


def result(appeal_id: str, kind: str, payload: object, model: str | None = None,
           prompt_version: str | None = None):
    with db() as conn:
        conn.execute("INSERT INTO results VALUES (?,?,?,?,?,?,?)",
                     (uid(), appeal_id, kind, json.dumps(payload, ensure_ascii=False),
                      model, prompt_version, now()))


def latest(appeal_id: str, kind: str) -> dict | None:
    row = one("SELECT * FROM results WHERE appeal_id=? AND kind=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
              (appeal_id, kind))
    return json.loads(row["payload"]) if row else None


def audit(appeal_id: str | None, action: str, actor: str | None = None, details: object = None):
    execute("INSERT INTO audit VALUES (?,?,?,?,?,?)",
            (uid(), appeal_id, action, actor, json.dumps(details or {}, ensure_ascii=False), now()))
