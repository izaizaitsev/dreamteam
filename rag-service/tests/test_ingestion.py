from datetime import date
from io import BytesIO
from zipfile import ZipFile
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from rag.api import app
from rag.db import Base, get_db
from rag.docx import InvalidDocx, extract
from rag.worker import demo_dates

def docx(text: str, extra: dict[str, bytes] | None = None) -> bytes:
    output = BytesIO()
    xml = (f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    with ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return output.getvalue()

def test_docx_extracts_text_and_rejects_external_relationships():
    assert extract(docx("Срок исполнения указан в документе"))[0][1] == "Срок исполнения указан в документе"
    dangerous = docx("Текст", {"word/_rels/document.xml.rels": b'<Relationship TargetMode="External" />'})
    try:
        extract(dangerous)
        assert False
    except InvalidDocx:
        pass

def test_demo_dates_are_repeatable_and_category_specific():
    checksum = "a" * 64
    normative = demo_dates(checksum, "normative", date(2026, 9, 23))
    assert normative == demo_dates(checksum, "normative", date(2026, 9, 23))
    assert normative[2] is None
    obligation = demo_dates(checksum, "obligation", date(2026, 9, 23))
    assert obligation[:2] == (None, None)
    assert obligation[2] is not None

def test_upload_requires_category_and_is_idempotent(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    def db_override():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db_override
    monkeypatch.setenv("RAG_INTERNAL_TOKEN", "test-internal")
    monkeypatch.setattr("rag.api.store_original", lambda category, key, raw: None)
    monkeypatch.setattr("rag.api.process_ingestion_task.delay", lambda envelope: None)
    payload = docx("Тестовое условие документа")
    try:
        with TestClient(app) as client:
            headers = {"X-Internal-Token": "test-internal"}
            missing = client.post("/internal/documents", headers=headers,
                data={"organization_id": "org", "title": "Тест"}, files={"file": ("test.docx", payload)})
            assert missing.status_code == 422
            created = client.post("/internal/documents", headers=headers,
                data={"organization_id": "org", "document_category": "obligation", "title": "Тест"},
                files={"file": ("test.docx", payload)})
            assert created.status_code == 202
            repeated = client.post("/internal/documents", headers=headers,
                data={"organization_id": "org", "document_category": "obligation", "title": "Тест"},
                files={"file": ("test.docx", payload)})
            assert repeated.status_code == 202
            assert repeated.json()["revision_id"] == created.json()["revision_id"]
            assert client.get("/internal/documents", params={"organization_id": "org"}).status_code == 401
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
