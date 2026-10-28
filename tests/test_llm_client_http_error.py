from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import requests

import llm_client


class _FakeResponse:
    status_code = 400
    text = '{"code":"InvalidParameter","message":"bad model sk-secret12345678","request_id":"req-1"}'

    def json(self):
        return {
            "code": "InvalidParameter",
            "message": "bad model sk-secret12345678",
            "request_id": "req-1",
            "ignored": "do not expose arbitrary provider fields",
        }

    def raise_for_status(self):
        raise requests.HTTPError("400 Client Error")


class TestDashScopeHttpError(unittest.TestCase):
    def test_chat_completion_exposes_safe_dashscope_error_body(self):
        test_settings = SimpleNamespace(
            dashscope_api_key="sk-local-test-key",
            dashscope_base_url="https://dashscope.example.test/compatible-mode/v1",
            llm_timeout=30,
            llm_temperature=0.3,
        )
        with mock.patch.object(llm_client, "settings", test_settings), mock.patch(
            "llm_client.requests.post", return_value=_FakeResponse()
        ):
            with self.assertRaises(RuntimeError) as raised:
                llm_client.chat_completion("qwen-plus", "return json")

        message = str(raised.exception)
        self.assertIn("DashScope HTTP 400", message)
        self.assertIn("InvalidParameter", message)
        self.assertIn("bad model", message)
        self.assertIn("req-1", message)
        self.assertNotIn("sk-secret12345678", message)
        self.assertNotIn("ignored", message)


if __name__ == "__main__":
    unittest.main()
