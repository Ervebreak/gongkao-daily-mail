from __future__ import annotations

import sys
import types

sys.modules.setdefault("requests", types.SimpleNamespace())

from config import settings


def _candidate_with_reflections() -> dict:
    return {
        "delivery_date": "2026-06-23",
        "subject": "公考晨读",
        "html_body": "<html><body>完整版</body></html>",
        "plain_text": "完整版",
        "brief": {
            "today_theme": "基层治理",
            "today_takeaway": {"golden_sentences": [{"sentence": "把问题解决在基层一线。"}]},
            "daily_question": {
                "question": "请谈谈如何做好基层治理。",
                "candidate_answer": "完整版答案不应进入简版。",
            },
        },
        "final_selection": {
            "featured": {"title": "精读文章"},
            "quick_reads": [{"title": "速读一"}],
        },
        "quality": {"final": {}},
        "quality_gate": {"overall": "ok", "p0_count": 0, "p0_issues": []},
        "quality_reflections": {
            "reflection_count": 1,
            "reflections": [
                {
                    "issue_type": "half_sentence",
                    "module": "content_quality",
                    "root_cause": "render",
                    "detector": "text_truncation",
                    "auto_fix": "minor_auto_fix_or_rewrite",
                }
            ],
            "summary": {
                "repeated_issue_types": {"half_sentence": 2},
                "promoted_counts": {"rule": 1},
            },
        },
    }


def test_build_admin_quality_report_includes_reflections() -> None:
    import admin_report

    subject, plain_text, html_body = admin_report.build_admin_quality_report(_candidate_with_reflections())

    assert "质检报告" in subject
    assert "本次质量反思" in plain_text
    assert "half_sentence / content_quality / render" in plain_text
    assert "本次质量反思" in html_body
    assert "流转状态" in html_body


def test_send_admin_quality_report_attaches_reflections(monkeypatch) -> None:
    import admin_report

    original_enabled = settings.admin_report_enabled
    original_send_email = settings.admin_report_send_email
    original_emails = settings.admin_report_emails_raw
    object.__setattr__(settings, "admin_report_enabled", True)
    object.__setattr__(settings, "admin_report_send_email", True)
    object.__setattr__(settings, "admin_report_emails_raw", "admin@example.com")

    captured: dict[str, object] = {}

    def fake_send_email_to_recipients(*args, **kwargs):
        captured["attachments"] = kwargs.get("attachments") or []
        return {"success_count": 1, "fail_count": 0, "recipient_status": [], "failures": []}

    monkeypatch.setattr(admin_report, "send_email_to_recipients", fake_send_email_to_recipients)
    try:
        result = admin_report.send_admin_quality_report(_candidate_with_reflections())
    finally:
        object.__setattr__(settings, "admin_report_enabled", original_enabled)
        object.__setattr__(settings, "admin_report_send_email", original_send_email)
        object.__setattr__(settings, "admin_report_emails_raw", original_emails)

    filenames = [item["filename"] for item in captured["attachments"]]
    assert result["admin_report_sent"] is True
    assert "latest_quality_reflections.json" in filenames
