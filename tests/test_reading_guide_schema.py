from __future__ import annotations

import unittest

from brief_schema import ensure_brief_schema


class ReadingGuideSchemaTests(unittest.TestCase):
    def test_missing_reading_guide_gets_filled(self) -> None:
        brief, warnings = ensure_brief_schema(
            {
                "date": "2026-06-02",
                "email_subject": "申论素材：群众诉求怎么用",
                "today_theme": "基层治理",
                "today_focus": "抓住群众诉求办理中的闭环问题和答题角度。",
                "featured_article": {
                    "title": "群众诉求办理中的闭环治理",
                    "source": "人民日报",
                    "theme": "群众诉求",
                    "article_framework_map": {
                        "exam_tags": ["群众诉求", "基层治理"],
                        "steps": [],
                    },
                },
                "daily_question": {
                    "question_type": "申论综合分析题",
                    "question": "请结合基层治理实际，谈谈如何提升群众诉求办理质效。",
                },
                "today_takeaway": {},
            },
            "2026-06-02",
        )
        guide = brief.get("reading_guide") or {}
        self.assertTrue(guide.get("core_value"))
        self.assertTrue(guide.get("focus_path"))
        self.assertTrue(guide.get("learning_outcome"))
        self.assertEqual(guide.get("anchor_module"), "今日一题")
        self.assertLessEqual(len(guide.get("core_value", "")), 45)
        self.assertLessEqual(len(guide.get("focus_path", "")), 55)
        self.assertLessEqual(len(guide.get("learning_outcome", "")), 55)
        self.assertIsInstance(warnings, list)
