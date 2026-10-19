"""Model request logs record outcomes without credentials or prompt content."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.integrations.gigachat import GigaChatClient
from app.schemas.ai import Draft


class GigaChatLoggingTest(unittest.TestCase):
    def test_empty_full_text_is_valid_when_template_renders_it(self):
        draft = {"subject": "Претензия", "full_text": "", "confidence": 0.8}
        reply = {"choices": [{"message": {"content": json.dumps(draft)}}]}
        with patch.object(GigaChatClient, "complete", new=AsyncMock(return_value=reply)) as complete:
            parsed, _ = asyncio.run(GigaChatClient().structured(
                Draft, "system", {"template": "Тема: {{subject}}"}))
        self.assertEqual(parsed.full_text, "")
        self.assertEqual(complete.await_count, 1)

    def test_empty_full_text_without_template_is_retried(self):
        empty = {"choices": [{"message": {"content": json.dumps(
            {"subject": "Ответ", "full_text": "", "confidence": 0.8})}}]}
        filled = {"choices": [{"message": {"content": json.dumps(
            {"subject": "Ответ", "full_text": "Текст ответа", "confidence": 0.8})}}]}
        with patch.object(GigaChatClient, "complete", new=AsyncMock(side_effect=[empty, filled])) as complete:
            with self.assertLogs("uvicorn.error", level="WARNING"):
                parsed, _ = asyncio.run(GigaChatClient().structured(Draft, "system", {"template": None}))
        self.assertEqual(parsed.full_text, "Текст ответа")
        self.assertEqual(complete.await_count, 2)

    def test_draft_text_is_assembled_from_sections_without_template(self):
        reply = {"choices": [{"message": {"content": json.dumps({
            "subject": "Ответ", "factual_section": "Установленные обстоятельства.",
            "closing_section": "Просим предоставить документы.",
            "full_text": "", "confidence": 0.8,
        })}}]}
        with patch.object(GigaChatClient, "complete", new=AsyncMock(return_value=reply)) as complete:
            parsed, _ = asyncio.run(GigaChatClient().structured(Draft, "system", {"template": None}))
        self.assertIn("Установленные обстоятельства.", parsed.full_text)
        self.assertIn("Просим предоставить документы.", parsed.full_text)
        self.assertEqual(complete.await_count, 1)

    def test_chat_response_is_logged_without_payload(self):
        def respond(request: httpx.Request):
            self.assertEqual(request.headers["Authorization"], "Bearer test-token")
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 17},
            })

        real_client = httpx.AsyncClient

        def mock_client(**kwargs):
            return real_client(transport=httpx.MockTransport(respond), **kwargs)

        with patch.object(GigaChatClient, "access_token", new=AsyncMock(return_value="test-token")), \
             patch("app.integrations.gigachat.gigachat_tls_verify", return_value=True), \
             patch("app.integrations.gigachat.httpx.AsyncClient", side_effect=mock_client):
            with self.assertLogs("uvicorn.error", level="INFO") as logs:
                result = asyncio.run(GigaChatClient().complete([
                    {"role": "user", "content": "Секретное обращение"},
                ]))

        self.assertEqual(result["usage"]["total_tokens"], 17)
        self.assertIn("GigaChat request", logs.output[0])
        self.assertIn("GigaChat response", logs.output[1])
        self.assertIn("total_tokens=17", logs.output[1])
        self.assertNotIn("test-token", " ".join(logs.output))
        self.assertNotIn("Секретное обращение", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
