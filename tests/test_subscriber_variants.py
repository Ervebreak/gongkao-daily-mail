from __future__ import annotations

from email_sender import (
    apply_successful_reminder_updates,
    recipient_variant,
    render_variant_email_payloads,
    serialize_subscribers_csv,
    split_recipient_records,
)


def test_recipient_variants_cover_trial_warning_and_lite_fallbacks() -> None:
    records = [
        {"email": " d3@example.com ", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-10", "send_mode": "full"},
        {"email": "d1@example.com", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-08", "send_mode": "full"},
        {"email": "d0@example.com", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-07", "send_mode": "full"},
        {"email": "normal@example.com", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-12", "send_mode": "full"},
        {"email": "no-date@example.com", "status": "active", "plan": "paid_trial", "paid_until": "", "send_mode": "full"},
        {"email": "free@example.com", "status": "active", "plan": "free", "paid_until": "", "send_mode": "lite"},
        {"email": "expired@example.com", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-06", "send_mode": "full"},
        {"email": "skip@example.com", "status": "paused", "plan": "free", "paid_until": "", "send_mode": "lite"},
    ]

    segments = split_recipient_records(records, today="2026-06-07")

    assert recipient_variant(records[0], today="2026-06-07") == "full_trial_d3"
    assert recipient_variant(records[1], today="2026-06-07") == "full_trial_d1"
    assert recipient_variant(records[2], today="2026-06-07") == "full_trial_d0"
    assert recipient_variant(records[3], today="2026-06-07") == "full_normal"
    assert recipient_variant(records[4], today="2026-06-07") == "full_normal"
    assert recipient_variant(records[5], today="2026-06-07") == "free_lite"
    assert recipient_variant(records[6], today="2026-06-07") == "expired_lite"
    assert recipient_variant(records[7], today="2026-06-07") == "skip"

    assert [item["email"] for item in segments["variants"]["full_trial_d3"]] == ["d3@example.com"]
    assert [item["email"] for item in segments["variants"]["full_trial_d1"]] == ["d1@example.com"]
    assert [item["email"] for item in segments["variants"]["full_trial_d0"]] == ["d0@example.com"]
    assert [item["email"] for item in segments["variants"]["full_normal"]] == ["normal@example.com", "no-date@example.com"]
    assert [item["email"] for item in segments["variants"]["free_lite"]] == ["free@example.com"]
    assert [item["email"] for item in segments["variants"]["expired_lite"]] == ["expired@example.com"]
    assert [item["email"] for item in segments["variants"]["skip"]] == ["skip@example.com"]
    assert segments["variant_counts"]["full_trial_d3"] == 1
    assert segments["variant_counts"]["full_normal"] == 2


def test_render_variant_email_payloads_inserts_trial_banner_once_per_variant() -> None:
    payloads = render_variant_email_payloads(
        subject="测试主题",
        full_plain_text="FULL BODY",
        full_html_body="<html><body><div>FULL BODY</div></body></html>",
        lite_plain_text="LITE BODY",
        lite_html_body="<html><body><div>LITE BODY</div></body></html>",
        variants=["full_normal", "full_trial_d3", "free_lite"],
        enable_trial_reminders=True,
    )

    assert payloads["full_normal"]["plain_text"] == "FULL BODY"
    assert "FULL BODY" in payloads["full_trial_d3"]["plain_text"]
    assert "还有 3 天到期" in payloads["full_trial_d3"]["plain_text"]
    assert "还有 3 天到期" in payloads["full_trial_d3"]["html_body"]
    assert payloads["free_lite"]["plain_text"] == "LITE BODY"
    assert "还有 3 天到期" not in payloads["free_lite"]["html_body"]


def test_apply_successful_reminder_updates_and_csv_compat() -> None:
    table = {
        "fieldnames": ["uid", "email", "status", "plan", "paid_until", "send_mode", "note"],
        "records": [
            {
                "uid": "u1",
                "email": "d3@example.com",
                "status": "active",
                "plan": "paid_trial",
                "paid_until": "2026-06-10",
                "send_mode": "full",
                "note": "trial",
            },
            {
                "uid": "u2",
                "email": "d1@example.com",
                "status": "active",
                "plan": "paid_trial",
                "paid_until": "2026-06-08",
                "send_mode": "full",
                "note": "trial",
                "reminder_sent": "d3",
            },
        ],
    }
    variant_results = {
        "full_trial_d3": {
            "recipient_status": [
                {"email": "d3@example.com", "status": "sent"},
                {"email": "d1@example.com", "status": "failed", "error": "smtp"},
            ]
        },
        "full_trial_d1": {
            "recipient_status": [
                {"email": "d1@example.com", "status": "sent"},
            ]
        },
    }

    meta = apply_successful_reminder_updates(table, variant_results)
    csv_text = serialize_subscribers_csv(table["records"], table["fieldnames"])

    assert meta["subscribers_reminder_updates"] == 2
    assert table["records"][0]["reminder_sent"] == "d3"
    assert table["records"][1]["reminder_sent"] == "d3|d1"
    assert csv_text.splitlines()[0].endswith(",reminder_sent")
    assert "d3@example.com" in csv_text
    assert "d3|d1" in csv_text
