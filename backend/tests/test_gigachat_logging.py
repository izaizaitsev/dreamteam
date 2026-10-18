"""Model request logs record outcomes without credentials or prompt content."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.integrations.gigachat import GigaChatClient


class GigaChatLoggingTest(unittest.TestCase):
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
