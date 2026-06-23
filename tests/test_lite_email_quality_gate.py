from __future__ import annotations

from lite_email_quality import evaluate_lite_email_quality


def _payload(hook: str) -> dict:
    return {
        "brief": {
            "featured_article": {
                "title": "把群众工作做成闭环",
                "one_sentence": "先接住诉求，再形成闭环。",
            },
            "daily_question": {
                "question": "请谈谈基层治理如何形成闭环办理机制。",
                "candidate_answer": "完整版答案不应出现在简版里。",
            },
            "lite_paid_cta": {
                "hook_type": "daily_question",
                "hook": hook,
                "source_module": "daily_question",
                "fallback_used": False,
            },
        }
    }


def test_lite_email_quality_flags_truncated_hook() -> None:
    result = evaluate_lite_email_quality(
        _payload("今天这道题适合练先摸清诉求、再公开协商，适合迁移到基层治理题"),
        plain_text="今天完整版多讲了什么\n今日完整版亮点：今天这道题适合练先摸清诉求、再公开协商，适合迁移到基层治理题",
        html_body="<p>今天完整版多讲了什么</p>",
    )

    assert result["status"] == "fail"
    assert any(item["code"] == "lite_cta_truncated" for item in result["issues"])


def test_lite_email_quality_flags_internal_marker_leak() -> None:
    result = evaluate_lite_email_quality(
        _payload("今天这道题会继续拆到基层协商和闭环反馈场景。"),
        plain_text="lite_paid_cta hook_type source_module fallback_used",
        html_body="<p>这是 debug candidate quality gate 字段</p>",
    )

    assert result["status"] == "fail"
    assert any(item["code"] == "lite_internal_marker_leaked" for item in result["issues"])
