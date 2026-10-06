"""End-to-end workflow with local AI adapters replaced by deterministic fakes."""
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import ai
from app.main import app
from app.settings import settings


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        Path("app/data").mkdir(parents=True, exist_ok=True)
        self.db_path = Path("app/data/test_workflow.sqlite3").resolve()
        self.db_path.unlink(missing_ok=True)
        object.__setattr__(settings, "database_path", str(self.db_path))
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.db_path.unlink(missing_ok=True)

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
        body = {"code": "LEAK_V1", "name": "Протечка", "body": "Уважаемый заявитель"}
        self.assertEqual(self.client.post("/api/templates", json=body).json()["version"], 1)
        self.assertEqual(self.client.post("/api/templates", json=body).json()["version"], 2)


if __name__ == "__main__":
    unittest.main()
