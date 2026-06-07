from __future__ import annotations

import sys
import types
import json

sys.modules.setdefault("requests", types.SimpleNamespace())

from email_sender import parse_subscribers_csv_all_records, split_recipient_records, update_send_audit_results, save_send_audit
from config import settings
from lite_email_renderer import render_lite_email


def test_paid_lite_recipient_segmentation() -> None:
    csv_text = """email,status,plan,paid_until,send_mode,note
paid@example.com,active,paid_trial,2026-06-30,,
expired@example.com,active,paid_monthly,2026-06-01,,
free@example.com,active,free,,,
gone@example.com,unsubscribed,paid_monthly,2026-06-30,,
"""
    records = parse_subscribers_csv_all_records(csv_text)

    segments = split_recipient_records(records, today="2026-06-07")

    assert [item["email"] for item in segments["full"]] == ["paid@example.com"]
    assert [item["email"] for item in segments["lite"]] == ["expired@example.com", "free@example.com"]
    assert [item["email"] for item in segments["skipped"]] == ["gone@example.com"]


def test_missing_paid_fields_default_to_active_free_lite() -> None:
    records = parse_subscribers_csv_all_records("email\nlegacy@example.com\n")

    segments = split_recipient_records(records, today="2026-06-07")

    assert segments["full"] == []
    assert [item["email"] for item in segments["lite"]] == ["legacy@example.com"]
    assert segments["skipped"] == []


def test_send_mode_overrides_plan_and_paid_until() -> None:
    csv_text = """email,status,plan,paid_until,send_mode,note
force_full@example.com,active,free,,full,
force_lite@example.com,active,paid_monthly,2026-06-30,lite,
force_none@example.com,active,paid_monthly,2026-06-30,none,
"""
    records = parse_subscribers_csv_all_records(csv_text)

    segments = split_recipient_records(records, today="2026-06-07")

    assert [item["email"] for item in segments["full"]] == ["force_full@example.com"]
    assert [item["email"] for item in segments["lite"]] == ["force_lite@example.com"]
    assert [item["email"] for item in segments["skipped"]] == ["force_none@example.com"]


def test_send_audit_records_send_results(tmp_path) -> None:
    original_output_dir = settings.output_dir
    object.__setattr__(settings, "output_dir", tmp_path)
    try:
        segments = split_recipient_records(
            parse_subscribers_csv_all_records(
                """email,status,plan,paid_until
full@example.com,active,paid_trial,2026-06-30
lite@example.com,active,free,
"""
            ),
            today="2026-06-07",
        )
        audit = save_send_audit("2026-06-07", segments, "test")
        update_send_audit_results(
            "2026-06-07",
            audit,
            {
                "success_count": 1,
                "fail_count": 0,
                "recipient_status": [{"email": "full@example.com", "status": "sent"}],
                "failures": [],
            },
            {
                "success_count": 0,
                "fail_count": 1,
                "recipient_status": [{"email": "lite@example.com", "status": "failed", "error": "smtp"}],
                "failures": [{"email": "lite@example.com", "error": "smtp"}],
            },
        )
        stored = json.loads((tmp_path / "send_audit_2026-06-07.json").read_text(encoding="utf-8"))

        assert stored["full_emails"] == ["full@example.com"]
        assert stored["lite_emails"] == ["lite@example.com"]
        assert stored["full_result"]["success_count"] == 1
        assert stored["lite_result"]["failures"] == [{"email": "lite@example.com", "error": "smtp"}]
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)


def test_render_lite_email_keeps_only_simple_preview_fields() -> None:
    lite = render_lite_email(
        {
            "brief": {
                "today_theme": "基层治理中的协同处置",
                "today_takeaway": {
                    "golden_sentences": [{"sentence": "把问题解决在基层一线。"}],
                },
                "daily_question": {
                    "question": "请谈谈如何做好跨部门协同。",
                    "candidate_answer": "这是完整版答案，不应进入简版。",
                },
            },
            "weekly_pdf": {"oss_pdf_path": "oss://bucket/weekly.pdf"},
        }
    )

    body = lite["plain_text"] + lite["html_body"]
    assert "基层治理中的协同处置" in body
    assert "把问题解决在基层一线。" in body
    assert "请谈谈如何做好跨部门协同。" in body
    assert "这是完整版答案" not in body
    assert "oss://bucket/weekly.pdf" not in body
    assert "周末 PDF 下载" not in body
