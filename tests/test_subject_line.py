from __future__ import annotations

import unittest

from subject_line import normalize_email_subject


def _brief_with_subject(subject: str) -> dict:
    return {
        "email_subject": subject,
        "today_theme": "基层治理",
        "featured_article": {
            "title": "群众诉求办理中的闭环治理",
            "theme": "群众诉求",
            "article_framework_map": {
                "exam_tags": ["群众诉求"],
            },
        },
        "daily_question": {
            "question_type": "申论综合分析题",
            "upper_exam_points": ["群众诉求"],
        },
    }


class SubjectLineNormalizationTests(unittest.TestCase):
    def test_generic_subject_falls_back(self) -> None:
        brief, _ = normalize_email_subject(_brief_with_subject("基层治理"))
        self.assertEqual(brief["email_subject"], "申论素材：群众诉求怎么用")

    def test_prefixed_generic_subject_strips_and_falls_back(self) -> None:
        brief, _ = normalize_email_subject(_brief_with_subject("【公考晨读】公共服务"))
        self.assertEqual(brief["email_subject"], "申论素材：群众诉求怎么用")

    def test_hype_subject_is_replaced(self) -> None:
        brief, _ = normalize_email_subject(_brief_with_subject("必考押题：基层治理"))
        self.assertEqual(brief["email_subject"], "申论素材：群众诉求怎么用")

    def test_good_exam_benefit_subject_is_preserved(self) -> None:
        brief, _ = normalize_email_subject(_brief_with_subject("高频考点：群众诉求怎么闭环"))
        self.assertEqual(brief["email_subject"], "高频考点：群众诉求怎么闭环")


if __name__ == "__main__":
    unittest.main()
