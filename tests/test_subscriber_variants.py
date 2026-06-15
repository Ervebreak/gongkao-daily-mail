from __future__ import annotations

import email_sender

from email_sender import (
    apply_try_expiration_updates,
    apply_successful_reminder_updates,
    recipient_variant,
    render_variant_email_payloads,
    serialize_subscribers_csv,
    send_segmented_email,
    subscribers_table_needs_reminder_field_backfill,
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
        {"email": "try-full@example.com", "status": "active", "plan": "try", "paid_until": "2026-06-09", "send_mode": "full"},
        {"email": "try-expired@example.com", "status": "active", "plan": "try", "paid_until": "2026-06-06", "send_mode": "full"},
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
    assert recipient_variant(records[8], today="2026-06-07") == "full_normal"
    assert recipient_variant(records[9], today="2026-06-07") == "expired_lite"

    assert [item["email"] for item in segments["variants"]["full_trial_d3"]] == ["d3@example.com"]
    assert [item["email"] for item in segments["variants"]["full_trial_d1"]] == ["d1@example.com"]
    assert [item["email"] for item in segments["variants"]["full_trial_d0"]] == ["d0@example.com"]
    assert [item["email"] for item in segments["variants"]["full_normal"]] == ["normal@example.com", "no-date@example.com", "try-full@example.com"]
    assert [item["email"] for item in segments["variants"]["free_lite"]] == ["free@example.com"]
    assert [item["email"] for item in segments["variants"]["expired_lite"]] == ["expired@example.com", "try-expired@example.com"]
    assert [item["email"] for item in segments["variants"]["skip"]] == ["skip@example.com"]
    assert segments["variant_counts"]["full_trial_d3"] == 1
    assert segments["variant_counts"]["full_normal"] == 3


def test_try_plan_never_triggers_trial_reminder_variants() -> None:
    record = {
        "email": "try-reminder@example.com",
        "status": "active",
        "plan": "try",
        "paid_until": "2026-06-10",
        "send_mode": "full",
    }

    segments = split_recipient_records([record], today="2026-06-07")

    assert recipient_variant(record, today="2026-06-07") == "full_normal"
    assert "full_trial_d3" not in segments["variants"]
    assert [item["email"] for item in segments["variants"]["full_normal"]] == ["try-reminder@example.com"]


def test_recipient_variant_skips_repeat_trial_reminder_when_already_sent() -> None:
    record = {
        "email": "repeat@example.com",
        "status": "active",
        "plan": "paid_trial",
        "paid_until": "2026-06-10",
        "send_mode": "full",
        "reminder_sent": "d3",
    }

    segments = split_recipient_records([record], today="2026-06-07")

    assert recipient_variant(record, today="2026-06-07") == "full_normal"
    assert "full_trial_d3" not in segments["variants"]
    assert [item["email"] for item in segments["variants"]["full_normal"]] == ["repeat@example.com"]


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


def test_apply_try_expiration_updates_downgrades_to_free_lite() -> None:
    table = {
        "fieldnames": ["uid", "email", "status", "plan", "paid_until", "send_mode", "note"],
        "records": [
            {
                "uid": "u1",
                "email": "try-expired@example.com",
                "status": "active",
                "plan": "try",
                "paid_until": "2026-06-06",
                "send_mode": "full",
                "note": "friend test",
            },
            {
                "uid": "u2",
                "email": "try-active@example.com",
                "status": "active",
                "plan": "try",
                "paid_until": "2026-06-08",
                "send_mode": "full",
                "note": "",
            },
        ],
    }

    meta = apply_try_expiration_updates(table, today="2026-06-07")

    assert meta["subscribers_try_expiration_updates"] == 1
    assert meta["subscribers_try_expiration_update_emails"] == ["try-expired@example.com"]
    assert table["records"][0]["plan"] == "free"
    assert table["records"][0]["send_mode"] == "lite"
    assert table["records"][0]["paid_until"] == ""
    assert "auto_downgraded_from_try_2026-06-07" in table["records"][0]["note"]
    assert table["records"][1]["plan"] == "try"


def test_subscribers_table_backfill_detection() -> None:
    assert subscribers_table_needs_reminder_field_backfill({"source_fieldnames": ["uid", "email", "status"]}) is True
    assert subscribers_table_needs_reminder_field_backfill({"source_fieldnames": ["uid", "email", "reminder_sent"]}) is False


def test_send_segmented_email_skips_oss_write_when_no_subscriber_changes(monkeypatch) -> None:
    def fake_send(*args, **kwargs):
        recipients = kwargs.get("recipients") if "recipients" in kwargs else args[3]
        return {
            "send_mode": "individual",
            "recipient_source": kwargs.get("recipient_source", "test"),
            "valid_recipient_count": len(recipients),
            "success_count": len(recipients),
            "fail_count": 0,
            "recipient_status": [{"email": item["email"], "status": "sent"} for item in recipients],
            "failures": [],
        }

    def fail_backup(*args, **kwargs):
        raise AssertionError("backup_and_save_subscribers_table_to_oss should not be called")

    monkeypatch.setattr(email_sender, "_send_email_to_records", fake_send)
    monkeypatch.setattr(email_sender, "backup_and_save_subscribers_table_to_oss", fail_backup)

    segments = split_recipient_records(
        [{"email": "normal@example.com", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-12", "send_mode": "full"}],
        today="2026-06-07",
    )
    subscribers_table = {
        "records": [{"email": "normal@example.com", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-12", "send_mode": "full", "reminder_sent": ""}],
        "fieldnames": ["email", "status", "plan", "paid_until", "send_mode", "reminder_sent"],
        "source_fieldnames": ["email", "status", "plan", "paid_until", "send_mode", "reminder_sent"],
        "storage": "oss",
    }

    result = send_segmented_email(
        "测试主题",
        "FULL",
        "<html><body>FULL</body></html>",
        "LITE",
        "<html><body>LITE</body></html>",
        delivery_date="2026-06-07",
        test_mode=False,
        segments=segments,
        recipient_source="test",
        enable_trial_reminders=True,
        subscribers_table=subscribers_table,
    )

    assert result["subscribers_write_skipped"] is True
    assert result["subscribers_write_skip_reason"] == "no_subscriber_changes"


def test_send_segmented_email_writes_when_reminder_field_missing(monkeypatch) -> None:
    def fake_send(*args, **kwargs):
        recipients = kwargs.get("recipients") if "recipients" in kwargs else args[3]
        return {
            "send_mode": "individual",
            "recipient_source": kwargs.get("recipient_source", "test"),
            "valid_recipient_count": len(recipients),
            "success_count": len(recipients),
            "fail_count": 0,
            "recipient_status": [{"email": item["email"], "status": "sent"} for item in recipients],
            "failures": [],
        }

    def fake_backup(table):
        return {"subscribers_write_ok": True, "subscribers_backup_ok": True}

    monkeypatch.setattr(email_sender, "_send_email_to_records", fake_send)
    monkeypatch.setattr(email_sender, "backup_and_save_subscribers_table_to_oss", fake_backup)

    segments = split_recipient_records(
        [{"email": "normal@example.com", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-12", "send_mode": "full"}],
        today="2026-06-07",
    )
    subscribers_table = {
        "records": [{"email": "normal@example.com", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-12", "send_mode": "full"}],
        "fieldnames": ["email", "status", "plan", "paid_until", "send_mode"],
        "source_fieldnames": ["email", "status", "plan", "paid_until", "send_mode"],
        "storage": "oss",
    }

    result = send_segmented_email(
        "测试主题",
        "FULL",
        "<html><body>FULL</body></html>",
        "LITE",
        "<html><body>LITE</body></html>",
        delivery_date="2026-06-07",
        test_mode=False,
        segments=segments,
        recipient_source="test",
        enable_trial_reminders=True,
        subscribers_table=subscribers_table,
    )

    assert result["subscribers_write_skipped"] is False
    assert result["subscribers_write_ok"] is True


def test_send_segmented_email_writes_when_try_plan_expires(monkeypatch) -> None:
    def fake_send(*args, **kwargs):
        recipients = kwargs.get("recipients") if "recipients" in kwargs else args[3]
        return {
            "send_mode": "individual",
            "recipient_source": kwargs.get("recipient_source", "test"),
            "valid_recipient_count": len(recipients),
            "success_count": len(recipients),
            "fail_count": 0,
            "recipient_status": [{"email": item["email"], "status": "sent"} for item in recipients],
            "failures": [],
        }

    def fake_backup(table):
        return {"subscribers_write_ok": True, "subscribers_backup_ok": True}

    monkeypatch.setattr(email_sender, "_send_email_to_records", fake_send)
    monkeypatch.setattr(email_sender, "backup_and_save_subscribers_table_to_oss", fake_backup)

    segments = split_recipient_records(
        [{"email": "try-expired@example.com", "status": "active", "plan": "try", "paid_until": "2026-06-06", "send_mode": "full"}],
        today="2026-06-07",
    )
    subscribers_table = {
        "records": [{"email": "try-expired@example.com", "status": "active", "plan": "try", "paid_until": "2026-06-06", "send_mode": "full", "note": ""}],
        "fieldnames": ["email", "status", "plan", "paid_until", "send_mode", "note"],
        "source_fieldnames": ["email", "status", "plan", "paid_until", "send_mode", "note"],
        "storage": "oss",
    }

    result = send_segmented_email(
        "娴嬭瘯涓婚",
        "FULL",
        "<html><body>FULL</body></html>",
        "LITE",
        "<html><body>LITE</body></html>",
        delivery_date="2026-06-07",
        test_mode=False,
        segments=segments,
        recipient_source="test",
        enable_trial_reminders=True,
        subscribers_table=subscribers_table,
    )

    assert result["subscribers_write_skipped"] is False
    assert result["subscribers_write_ok"] is True
    assert result["subscribers_try_expiration_updates"] == 1
    assert subscribers_table["records"][0]["plan"] == "free"
    assert subscribers_table["records"][0]["send_mode"] == "lite"
