from __future__ import annotations

import unittest
from unittest import mock

from agent import tools


class TestAgentToolArgumentFiltering(unittest.TestCase):
    def test_execute_tool_ignores_model_explanation_fields(self) -> None:
        received: dict = {}

        def fake_tool(article_ids, delivery_date):
            received.update(article_ids=article_ids, delivery_date=delivery_date)
            return {"ok": True}

        registered = tools.Tool(
            name="select_articles_for_test",
            description="test",
            parameters={"article_ids": {"type": "array"}},
            fn=fake_tool,
        )
        with mock.patch.dict(
            tools.TOOL_REGISTRY,
            {"select_articles_for_test": registered},
            clear=False,
        ), mock.patch.object(tools, "load_run", return_value=None):
            result = tools.execute_tool(
                "select_articles_for_test",
                {
                    "article_ids": [1, 2, 3],
                    "reason": "模型误放在 arguments 里的选文理由",
                    "unexpected": "ignored",
                },
                delivery_date="2026-10-29",
                test_mode=False,
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            received,
            {"article_ids": [1, 2, 3], "delivery_date": "2026-10-29"},
        )


if __name__ == "__main__":
    unittest.main()
