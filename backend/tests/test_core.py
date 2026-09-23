from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.ai import AIRequest, MockAIProvider
from app.api import app, verified_citations
from app.auth import Actor, require_role
from app.db import Base, get_db
from app.deadlines import deadline_state, reminder_offset
from app.documents import DocumentError, extract_text
from app.models import Obligation, Organization, Prescription, RegulatoryDocument, RegulatoryRevision, User
from app.rag import EmbeddingProvider

def test_mock_ai_uses_supplied_citation_only():
    import asyncio
    result = asyncio.run(MockAIProvider().generate(AIRequest("consultation", "question", [
        {"citation_id": "S1", "fragment": "Проверенный фрагмент"}
    ])))
    assert "[S1]" in result
    assert "Проверенный фрагмент" in result

def test_embedding_is_deterministic():
    provider = EmbeddingProvider()
    assert provider.embed("лифт проверка") == provider.embed("лифт проверка")
    assert provider.embed("лифт проверка") != provider.embed("договор аренда")

def test_deadline_offsets_are_deterministic():
    today = date(2026, 9, 23)
    assert reminder_offset(date(2026, 9, 30), today) == "7_days"
    assert reminder_offset(date(2026, 9, 26), today) == "3_days"
    assert reminder_offset(date(2026, 9, 24), today) == "1_day"
    assert reminder_offset(date(2026, 9, 22), today) == "overdue"
    assert deadline_state(date(2026, 9, 22), "done", today) == "closed"

def test_document_extraction_rejects_scanned_or_unsupported_file():
    assert extract_text("evidence.txt", "Текст подтверждения".encode())[0] == "Текст подтверждения"
    for name, data in [("scan.pdf", b"not a pdf"), ("image.png", b"image")]:
        try:
            extract_text(name, data)
            assert False
        except DocumentError:
            pass

def test_role_check_rejects_specialist():
    from fastapi import HTTPException
    actor = Actor("u", "org", "specialist", "specialist")
    try:
        require_role(actor, "lawyer")
        assert False
    except HTTPException as exc:
        assert exc.status_code == 403

def test_tenant_scoped_obligations(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)  # Test database only.
    with Session(engine) as db:
        db.add_all([Organization(id="a", name="A"), Organization(id="b", name="B")])
        db.add_all([User(id="ua", organization_id="a", username="a", role="admin", password_hash="x"),
                    User(id="ub", organization_id="b", username="b", role="admin", password_hash="x")])
        db.add_all([Obligation(id="oa", organization_id="a", title="Only A", description="", due_date=date(2027, 1, 1)),
                    Obligation(id="ob", organization_id="b", title="Only B", description="", due_date=date(2027, 1, 1))])
        db.add(Prescription(id="pb", organization_id="b", title="Only B", content="Чужой документ организации"))
        db.add(Prescription(id="pa", organization_id="a", title="Only A", content="Собственный документ организации"))
        db.commit()

    def db_override():
        with Session(engine) as session:
            yield session

    from app.auth import get_actor
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_actor] = lambda: Actor("ua", "a", "a", "admin")
    try:
        with TestClient(app) as client:
            result = client.get("/api/v1/obligations")
            assert result.status_code == 200
            assert [item["title"] for item in result.json()] == ["Only A"]
            assert client.post("/api/v1/obligations/ob/complete").status_code == 404
            assert client.post("/api/v1/prescriptions/pb/attachments", files={"file": ("a.txt", b"secret")}).status_code == 404
            uploaded = client.post("/api/v1/prescriptions/pa/attachments", files={"file": ("evidence.txt", "Текст приложения".encode())})
            assert uploaded.status_code == 201
            assert uploaded.json()["status"] == "ready"
            assert len(client.get("/api/v1/prescriptions/pa/attachments").json()) == 1
            draft = client.post("/api/v1/prescriptions/pa/drafts")
            assert draft.status_code == 201
            assert "evidence.txt" in draft.json()["content"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

def test_citations_use_canonical_revision_and_legal_date():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(RegulatoryDocument(id="doc", title="Проверенный источник", source_url="https://example.org/source"))
        db.add(RegulatoryRevision(id="rev", document_id="doc", section="Статья 1", effective_from=date(2025, 1, 1),
                                  effective_to=date(2026, 1, 1), content="Подтверждённый текст источника", checksum="x"))
        db.commit()
        hit = {"document_id": "doc", "revision_id": "rev", "chunk_id": "c", "title": "Подменённое название",
               "fragment": "Подтверждённый текст", "score": 0.9}
        valid = verified_citations(db, [hit], date(2025, 6, 1))
        assert valid[0]["title"] == "Проверенный источник"
        assert verified_citations(db, [hit], date(2026, 1, 1)) == []
    engine.dispose()
