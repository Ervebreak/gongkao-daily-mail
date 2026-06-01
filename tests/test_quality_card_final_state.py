from __future__ import annotations

from admin_report import build_quality_card_markdown


def test_quality_card_uses_final_remaining_issues_only() -> None:
    candidate = {
        "delivery_date": "2026-06-01",
        "subject": "【公考晨读】测试",
        "quality_gate": {"overall": "ok", "p0_count": 0, "p0_issues": []},
        "quality": {
            "initial": {
                "daily_question": {
                    "issues": [
                        {"severity": "high", "code": "old_initial_issue", "message": "这是初始旧问题"}
                    ]
                }
            },
            "final": {
                "daily_question": {"ok": True, "status": "ok", "score": 95, "issues": []},
                "content_quality": {"ok": True, "status": "ok", "score": 92, "issues": []},
                "content_risk": {"ok": True, "status": "ok", "score": 100, "issues": []},
            },
            "rewrite": {
                "rewritten_modules": ["daily_question"],
                "details": {
                    "daily_question": {
                        "issues_before": [
                            {"severity": "high", "code": "old_rewrite_issue", "message": "这是重写前旧问题"}
                        ]
                    }
                },
            },
        },
        "rewrite_comparison": [
            {
                "module": "daily_question",
                "changed": True,
                "issues_before": [
                    {"severity": "high", "code": "old_comparison_issue", "message": "这是对比旧问题"}
                ],
                "quality_after": {"status": "ok", "score": 95, "issues": []},
                "before": {"candidate_answer": "旧答案"},
                "after": {"candidate_answer": "新答案"},
            }
        ],
    }

    card = build_quality_card_markdown(candidate)

    assert "暂无剩余结构化风险" in card
    assert "old_initial_issue" not in card
    assert "old_rewrite_issue" not in card
    assert "old_comparison_issue" not in card


def test_quality_card_reports_final_issues() -> None:
    candidate = {
        "delivery_date": "2026-06-01",
        "subject": "【公考晨读】测试",
        "quality_gate": {
            "overall": "fail",
            "p0_count": 1,
            "p0_issues": [{"module": "daily_question", "code": "truncated_answer", "message": "答案疑似截断"}],
        },
        "quality": {
            "final": {
                "daily_question": {
                    "ok": False,
                    "status": "fail",
                    "score": 40,
                    "issues": [{"severity": "high", "code": "truncated_answer", "message": "答案疑似截断"}],
                },
                "content_quality": {"ok": True, "status": "ok", "score": 90, "issues": []},
                "content_risk": {"ok": True, "status": "ok", "score": 100, "issues": []},
            }
        },
    }

    card = build_quality_card_markdown(candidate)

    assert "truncated_answer" in card
    assert "答案疑似截断" in card
    assert "阻断发送" in card
