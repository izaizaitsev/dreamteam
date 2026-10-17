"""Embedding API contract and credential endpoint."""
import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.core.settings import settings
from app.integrations import embedding
from app.main import app


class EmbeddingTest(unittest.TestCase):
    def test_cloud_api_request(self):
        captured = {}

        def respond(request: httpx.Request):
            captured["url"] = str(request.url)
            captured["authorization"] = request.headers.get("Authorization")
            captured["body"] = request.content.decode()
            return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})

        real_client = httpx.AsyncClient

        def mock_client(**kwargs):
            return real_client(transport=httpx.MockTransport(respond), **kwargs)

        with patch("app.integrations.embedding.embedding_key", return_value="test-secret"), \
             patch("app.integrations.embedding.httpx.AsyncClient", side_effect=mock_client):
            vector = asyncio.run(embedding.embed("Проверка", query=True))

        self.assertEqual(vector, [0.1, 0.2])
        self.assertEqual(captured["url"], settings.embedding_url.rstrip("/") + "/embeddings")
        self.assertEqual(captured["authorization"], "Bearer test-secret")
        body = json.loads(captured["body"])
        self.assertEqual(body["model"], settings.embedding_model)
        self.assertIn("Query: Проверка", body["input"][0])

    def test_admin_can_save_key_without_echoing_it(self):
        Path("backend/data").mkdir(parents=True, exist_ok=True)
        key_path = Path("backend/data/test_embedding_api_key").resolve()
        key_path.unlink(missing_ok=True)
        previous = settings.embedding_key_path
        object.__setattr__(settings, "embedding_key_path", str(key_path))
        try:
            with TestClient(app) as client:
                response = client.put("/api/settings/embedding", json={"api_key": "test-embedding-secret"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn("test-embedding-secret", response.text)
                self.assertTrue(client.get("/api/settings/embedding").json()["configured"])
                self.assertEqual(key_path.read_text(), "test-embedding-secret")
        finally:
            object.__setattr__(settings, "embedding_key_path", previous)
            key_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
