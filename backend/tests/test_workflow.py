"""End-to-end workflow with local AI adapters replaced by deterministic fakes."""
import unittest
import json
import ssl
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import httpx
from docx import Document

from fastapi.testclient import TestClient
from app import ai
from app.main import app
from app.core.settings import settings
from app.integrations.credentials import gigachat_key
from app.repositories import sqlite as s


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        Path("backend/data").mkdir(parents=True, exist_ok=True)
        self.db_path = Path("backend/data/test_workflow.sqlite3").resolve()
        self.db_path.unlink(missing_ok=True)
        object.__setattr__(settings, "database_path", str(self.db_path))
        self.key_path = Path("backend/data/test_gigachat_auth_key").resolve()
        self.key_path.unlink(missing_ok=True)
        self.original_key_path = settings.gigachat_key_path
        object.__setattr__(settings, "gigachat_key_path", str(self.key_path))
        self.keys = (settings.api_key, settings.admin_api_key, settings.lawyer_api_key,
                     settings.operator_api_key)
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for name, value in zip(("api_key", "admin_api_key", "lawyer_api_key", "operator_api_key"), self.keys):
            object.__setattr__(settings, name, value)
        object.__setattr__(settings, "gigachat_key_path", self.original_key_path)
        self.key_path.unlink(missing_ok=True)
        self.db_path.unlink(missing_ok=True)

    def test_gigachat_tls_and_analysis_error(self):
        self.assertIsInstance(ai.gigachat_tls_verify(), ssl.SSLContext)
        self.client.post("/api/import/appeals", json=[{"external_id": "SSL-1", "text": "Протечка трубы"}])
        appeal_id = self.client.get("/api/appeals").json()[0]["id"]

        async def fail_search(_appeal_id):
            raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

        with patch("app.services.processing.search", fail_search):
            response = self.client.post(f"/api/appeals/{appeal_id}/process")
        self.assertEqual(response.status_code, 502)
        self.assertIn("сертификат", response.json()["detail"])
        self.assertEqual(self.client.get(f"/api/appeals/{appeal_id}").json()["status"], "ERROR")

    def test_legal_demo_fills_template(self):
        example = json.loads(Path("examples/legal-claim-demo.json").read_text(encoding="utf-8"))
        self.assertEqual(self.client.post("/api/templates", json=example["template"]).status_code, 200)
        self.assertEqual(self.client.post("/api/import/appeals", json=[example["appeal"]]).json()["created"], 1)
        appeal_id = self.client.get("/api/appeals").json()[0]["id"]

        async def fake_embed(text, query=False):
            return [0.1, 0.2]

        async def fake_retrieve(vector):
            return []

        async def fake_structured(schema, system, payload):
            if schema is ai.Classification:
                return ai.Classification(legal_required=True, case_type="disputed",
                    category=ai.Category(code="PROPERTY_DAMAGE_CLAIM", name="Возмещение ущерба"),
                    confidence=0.9, reasoning_summary="Требование о возмещении ущерба",
                    recommended_template_code="DEMO_DAMAGE_CLAIM_V1",
                    required_context=[ai.RequiredContext(key="work_history")]), {}
            return ai.Draft(subject="Ответ", full_text="Текст модели", confidence=0.8), {}

        with patch("app.ai.embed", fake_embed), patch("app.ai.retrieve", fake_retrieve), \
             patch.object(ai.gigachat, "structured", fake_structured):
            response = self.client.post(f"/api/appeals/{appeal_id}/process")
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()["draft"]["ai_payload"]
        self.assertEqual(draft["template_code"], "DEMO_DAMAGE_CLAIM_V1")
        self.assertIn("Тестовый заявитель", draft["full_text"])
        self.assertIn("Заявка DEMO-74", draft["full_text"])
        self.assertNotIn("{{", draft["full_text"])
        self.assertEqual(response.json()["draft"]["edited_text"], draft["full_text"])

    def test_import_process_review_and_versions(self):
        rows = [
            {"external_id": "A-1", "text": "Протекает труба", "applicant": {"name": "Иванов"},
             "context": {"building_info": {"address": "Дом 1"}}},
            {"external_id": "BAD", "text": ""},
        ]
        report = self.client.post("/api/import/appeals", json=rows).json()
        self.assertEqual((report["created"], len(report["errors"])), (1, 1))
        self.assertEqual(self.client.post("/api/import/appeals", json=[rows[0]]).json()["skipped"], 1)
        appeal_id = self.client.get("/api/appeals").json()[0]["id"]

        async def fake_embed(text, query=False):
            return [0.1, 0.2]

        async def fake_retrieve(vector):
            return []

        async def fake_complete(schema, system, payload):
            if schema is ai.Classification:
                return ai.Classification(legal_required=True, case_type="typical",
                    category=ai.Category(code="LEAK", name="Протечка"), confidence=0.8,
                    reasoning_summary="Требуется проверка", required_context=[
                        ai.RequiredContext(key="building_info")]), {"total_tokens": 10}
            return ai.Draft(subject="Ответ", full_text="Проект ответа",
                            confidence=0.7, used_context_keys=["building_info"]), {"total_tokens": 20}

        with patch("app.ai.embed", fake_embed), patch("app.ai.retrieve", fake_retrieve), \
             patch.object(ai.gigachat, "structured", fake_complete):
            self.assertEqual(self.client.post(f"/api/appeals/{appeal_id}/retrieve").status_code, 200)
            self.assertEqual(self.client.get(f"/api/appeals/{appeal_id}").json()["status"], "NEW")
            response = self.client.post(f"/api/appeals/{appeal_id}/process")
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["status"], "READY_FOR_REVIEW")
            self.assertEqual(data["context"][0]["data"]["address"], "Дом 1")
            draft_id = data["draft"]["id"]
            self.assertEqual(self.client.put(f"/api/drafts/{draft_id}", json={
                "actor": "Юрист", "text": "Проверенный ответ"}).status_code, 200)
            self.assertEqual(self.client.post(f"/api/drafts/{draft_id}/approve", json={
                "actor": "Юрист"}).json()["status"], "APPROVED")
            self.assertEqual(self.client.get(f"/api/appeals/{appeal_id}").json()["draft"]["edited_text"],
                             "Проверенный ответ")
            self.assertEqual(self.client.post(f"/api/drafts/{draft_id}/approve", json={
                "actor": "Юрист"}).status_code, 409)
            word = self.client.get(f"/api/drafts/{draft_id}/export-docx")
            self.assertEqual(word.status_code, 200)
            self.assertTrue(word.content.startswith(b"PK"))
            resolved = self.client.post(f"/api/appeals/{appeal_id}/mark-resolved", json={
                "actor": "Юрист", "index_now": False}).json()
            self.assertFalse(resolved["indexed"])
            self.assertEqual(self.client.get("/api/index/status").json()["total"], 1)

    def test_resolved_import_and_template_version(self):
        result = self.client.post("/api/import/resolved-cases", json=[
            {"external_id": "R-1", "appeal_text": "Протечка", "decision_text": "Провели осмотр"},
            {"external_id": "R-2"},
        ]).json()
        self.assertEqual(result["created"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(self.client.get("/api/index/status").json()["total"], 1)
        document = Document()
        document.add_paragraph("Уважаемый заявитель! Ваше обращение рассмотрено.")
        buffer = BytesIO()
        document.save(buffer)
        attached = self.client.post("/api/cases/decision-file?external_id=R-1",
            files={"file": ("answer.docx", buffer.getvalue(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        self.assertEqual(attached.status_code, 200, attached.text)
        case = s.one("SELECT * FROM cases WHERE external_id=?", ("R-1",))
        self.assertIn("Уважаемый заявитель", case["decision_text"])
        downloaded = self.client.get(f"/api/cases/{case['id']}/decision-file")
        self.assertEqual(downloaded.status_code, 200)
        self.assertTrue(downloaded.content.startswith(b"PK"))
        self.client.post("/api/import/resolved-cases", json=[
            {"external_id": "R-1", "appeal_text": "Протечка", "decision_text": "Устаревший JSON"}])
        self.assertIn("Уважаемый заявитель", s.one(
            "SELECT decision_text FROM cases WHERE external_id=?", ("R-1",))["decision_text"])
        Path(case["decision_file_uri"]).unlink()
        body = {"code": "LEAK_V1", "name": "Протечка", "body": "Уважаемый заявитель"}
        self.assertEqual(self.client.post("/api/templates", json=body).json()["version"], 1)
        self.assertEqual(self.client.post("/api/templates", json=body).json()["version"], 2)

    def test_roles_restrict_mutations(self):
        object.__setattr__(settings, "admin_api_key", "admin-test")
        object.__setattr__(settings, "lawyer_api_key", "lawyer-test")
        object.__setattr__(settings, "operator_api_key", "operator-test")
        operator = {"X-API-Key": "operator-test"}
        lawyer = {"X-API-Key": "lawyer-test"}
        admin = {"X-API-Key": "admin-test"}
        self.assertEqual(self.client.get("/api/appeals", headers=operator).status_code, 200)
        self.assertEqual(self.client.post("/api/templates", headers=operator,
            json={"code": "A", "name": "A", "body": "A"}).status_code, 403)
        self.assertEqual(self.client.post("/api/templates", headers=lawyer,
            json={"code": "A", "name": "A", "body": "A"}).status_code, 403)
        self.assertEqual(self.client.post("/api/templates", headers=admin,
            json={"code": "A", "name": "A", "body": "A"}).status_code, 200)
        self.assertEqual(self.client.get("/api/audit", headers=operator).status_code, 403)
        self.assertEqual(self.client.get("/api/me", headers=lawyer).json()["role"], "LAWYER")
        self.assertEqual(self.client.put("/api/settings/gigachat", headers=operator,
            json={"auth_key": "test-authorization-key"}).status_code, 403)
        response = self.client.put("/api/settings/gigachat", headers=admin,
            json={"auth_key": "test-authorization-key"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(gigachat_key(), "test-authorization-key")
        self.assertNotIn("test-authorization-key", self.client.get(
            "/api/settings/gigachat", headers=admin).text)

    def test_example_new_appeals_is_importable(self):
        examples = json.loads(Path("examples/new-appeals.json").read_text(encoding="utf-8"))
        self.assertEqual(len(examples), 2)
        self.assertEqual(self.client.post("/api/import/appeals", json=examples).json()["created"], 2)
        self.assertIn("AI-юрист по вопросам ЖКХ", Path("frontend/index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
