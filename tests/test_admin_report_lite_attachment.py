from __future__ import annotations

import sys
import types

sys.modules.setdefault("requests", types.SimpleNamespace())

from config import settings


def test_admin_report_attaches_full_and_lite_email(monkeypatch) -> None:
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
        result = admin_report.send_admin_quality_report(
            {
                "delivery_date": "2026-06-07",
                "subject": "公考晨读",
                "html_body": "<html><body>完整邮件</body></html>",
                "plain_text": "完整邮件",
                "brief": {
                    "today_theme": "基层治理",
                    "today_takeaway": {"golden_sentences": [{"sentence": "把问题解决在基层一线。"}]},
                    "daily_question": {
                        "question": "请谈谈如何做好基层治理。",
                        "candidate_answer": "完整答案不应进入简版。",
                    },
                },
                "quality": {"final": {}},
                "quality_gate": {"overall": "ok", "p0_count": 0, "p0_issues": []},
            }
        )
    finally:
        object.__setattr__(settings, "admin_report_enabled", original_enabled)
        object.__setattr__(settings, "admin_report_send_email", original_send_email)
        object.__setattr__(settings, "admin_report_emails_raw", original_emails)

    attachments = captured["attachments"]
    filenames = [item["filename"] for item in attachments]
    lite_html = next(item["content"] for item in attachments if item["filename"] == "candidate_lite_email_2026-06-07.html")

    assert result["admin_report_sent"] is True
    assert "candidate_email_2026-06-07.html" in filenames
    assert "candidate_lite_email_2026-06-07.html" in filenames
    assert "完整答案" not in lite_html
    assert "oss://" not in lite_html
