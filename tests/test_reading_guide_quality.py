from __future__ import annotations

import unittest

from reading_guide_quality import evaluate_reading_guide_quality


def _brief_with_guide(**guide_overrides):
    guide = {
        "core_value": "基层治理题要把群众诉求写到办理反馈闭环。",
        "focus_path": "先看今日一题的场景设置，再看今日精读里的办理链条。",
        "learning_outcome": "带走一套接诉、分办、反馈、复盘的作答思路。",
        "anchor_module": "今日一题",
    }
    guide.update(guide_overrides)
    return {
        "email_subject": "高频考点：群众诉求怎么闭环",
        "reading_guide": guide,
    }


def _codes(result):
    return {issue["code"] for issue in result["issues"]}


class ReadingGuideQualityTests(unittest.TestCase):
    def test_reading_guide_quality_ok(self) -> None:
        result = evaluate_reading_guide_quality(_brief_with_guide())
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["issues"], [])

    def test_missing_reading_guide(self) -> None:
        result = evaluate_reading_guide_quality({"email_subject": "今日带走：群众诉求的答题角度"})
        self.assertFalse(result["ok"])
        self.assertIn("missing_reading_guide", _codes(result))

    def test_generic_reading_guide(self) -> None:
        result = evaluate_reading_guide_quality(
            _brief_with_guide(
                core_value="今天可以提升你的申论能力。",
                focus_path="认真阅读后可以帮助学习。",
                learning_outcome="帮助你积累热点素材并增强理解。",
            )
        )
        self.assertIn("generic_reading_guide", _codes(result))

    def test_module_catalog_intro(self) -> None:
        result = evaluate_reading_guide_quality(
            _brief_with_guide(
                focus_path="建议依次阅读今日精读、今日一题和今日可带走。",
            )
        )
        self.assertIn("module_catalog_intro", _codes(result))

    def test_hype_reading_guide(self) -> None:
        result = evaluate_reading_guide_quality(
            _brief_with_guide(
                core_value="这是基层治理里的必考押题重点。",
            )
        )
        self.assertIn("hype_reading_guide", _codes(result))

    def test_reading_guide_too_long(self) -> None:
        result = evaluate_reading_guide_quality(
            _brief_with_guide(
                core_value="这句话故意写得很长很长很长很长很长很长很长很长，用来触发超长检测并观察质检是否正常工作。",
                focus_path="这一句也故意拉长到超过五十五个字，用来确认重点路径字段过长时能够稳定打出 review 信号，而不是静默通过并漏掉问题。",
                learning_outcome="最后这一句同样写得很长很长很长，确保看完带走字段长度超限时也会被记录下来，方便后续人工复盘和规则调优。",
            )
        )
        self.assertIn("reading_guide_too_long", _codes(result))


if __name__ == "__main__":
    unittest.main()
