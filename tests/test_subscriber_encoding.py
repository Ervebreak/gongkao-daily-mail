import pytest
from dataclasses import replace

import email_sender as sender


CSV = "uid,email,status,nickname,source\nu001,user@example.com,active,中文昵称,内测\n"


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gb18030", "utf-16"])
def test_decode_preserves_chinese(encoding):
    assert sender.decode_subscribers_csv_bytes(CSV.encode(encoding)) == CSV


def test_repeated_round_trips_preserve_uid_and_single_bom():
    table = sender.parse_subscribers_csv_table("\ufeff" * 7 + CSV)
    for _ in range(10):
        _, data = sender.serialize_subscribers_csv_bytes(table["records"], table["fieldnames"])
        assert data.startswith(b"\xef\xbb\xbfuid,")
        assert not data.startswith(b"\xef\xbb\xbf" * 2)
        table = sender.parse_subscribers_csv_table(sender.decode_subscribers_csv_bytes(data))
        assert table["fieldnames"].count("uid") == 1
        assert table["records"][0]["uid"] == "u001"
        assert table["records"][0]["nickname"] == "中文昵称"


@pytest.mark.parametrize("text", [CSV.replace("中文昵称", "???"), CSV.replace("中文昵称", "\ufffd")])
def test_damaged_description_is_readable_and_warned(text):
    decoded = sender.decode_subscribers_csv_bytes(text.encode("utf-8"))
    assert decoded == text
    assert sender._validate_subscribers_text(decoded) == [
        {"code": "damaged_descriptive_field", "row": 2, "field": "nickname"}
    ]


def setup_oss(monkeypatch):
    monkeypatch.setattr(sender, "settings", replace(sender.settings, subscribers_storage="oss"))
    monkeypatch.setattr(sender, "oss_ready", lambda: True)
    monkeypatch.setattr(sender, "oss_config", lambda: {})
    monkeypatch.setattr(sender, "oss_url", lambda cfg: cfg["object_key"])
    monkeypatch.setattr(sender, "oss_headers", lambda *args: {})


class Response:
    status_code = 200
    encoding = "ISO-8859-1"

    def __init__(self, data=b""):
        self.content = data

    @property
    def text(self):
        raise AssertionError("HTTP charset decoding must not be used")

    def raise_for_status(self):
        pass


def test_oss_read_ignores_wrong_charset_and_backup_is_exact(monkeypatch):
    setup_oss(monkeypatch)
    raw = CSV.encode("gb18030")
    monkeypatch.setattr(sender.requests, "get", lambda *args, **kwargs: Response(raw))
    calls = []

    def put(url, **kwargs):
        calls.append((url, kwargs["data"]))
        return Response()

    monkeypatch.setattr(sender.requests, "put", put)
    table = sender.load_subscribers_csv_oss_table()
    assert table["records"][0]["nickname"] == "中文昵称"
    result = sender.backup_and_save_subscribers_table_to_oss(table)
    assert result["subscribers_write_ok"]
    assert calls[0][1] == raw
    assert calls[1][1].startswith(b"\xef\xbb\xbfuid,")
    result = sender.backup_and_save_subscribers_table_to_oss(table)
    assert result["subscribers_write_skip_reason"] == "no_subscriber_changes"
    assert len(calls) == 2


def test_damaged_oss_read_stops_instead_of_fallback(monkeypatch):
    setup_oss(monkeypatch)
    monkeypatch.setattr(sender.requests, "get", lambda *args, **kwargs: Response(b"???uid,email\n"))
    with pytest.raises(ValueError, match="sending stopped"):
        sender.load_subscriber_table_for_segmentation()


def test_damaged_table_cannot_be_written(monkeypatch):
    setup_oss(monkeypatch)
    monkeypatch.setattr(sender.requests, "put", lambda *args, **kwargs: pytest.fail("must not write"))
    table = sender.parse_subscribers_csv_table(CSV.replace("中文昵称", "???"))
    result = sender.backup_and_save_subscribers_table_to_oss(table)
    assert not result["subscribers_write_ok"]
    assert result["subscribers_write_skip_reason"] == "damaged_descriptive_fields"


@pytest.mark.parametrize("text", [
    CSV.replace("user@example.com", "bad-email"),
    CSV.replace("active", "???"),
    CSV.replace("active", "actve"),
    CSV.replace("uid,email", "???uid,email"),
    CSV.replace("uid,email", "email,email"),
    CSV.replace(",source", ""),
    'email,status\n"unterminated,active\n',
    "email,status,plan\nuser@example.com,active,paidd\n",
    "email,status,send_mode\nuser@example.com,active,all\n",
    "email,status,paid_until\nuser@example.com,active,2026-02-30\n",
    "email,status,paid_until\nuser@example.com,active,2026-10-12junk\n",
])
def test_invalid_critical_data_stops_oss_read(monkeypatch, text):
    setup_oss(monkeypatch)
    monkeypatch.setattr(sender.requests, "get", lambda *args, **kwargs: Response(text.encode("utf-8")))
    with pytest.raises(ValueError, match="sending stopped"):
        sender.load_subscriber_table_for_segmentation()


def test_descriptive_damage_sends_but_no_backup_or_overwrite(monkeypatch, caplog):
    setup_oss(monkeypatch)
    text = CSV.replace("中文昵称", "???")
    monkeypatch.setattr(sender.requests, "get", lambda *args, **kwargs: Response(text.encode("gb18030")))
    monkeypatch.setattr(sender.requests, "put", lambda *args, **kwargs: pytest.fail("must not write"))
    table = sender.load_subscribers_csv_oss_table()
    assert table["subscribers_read_only"] is True
    assert "automatic backup and overwrite are disabled" in caplog.text
    assert "user@example.com" not in caplog.text
    sent = []

    def fake_send(subject, plain, html, recipients, **kwargs):
        sent.extend(item["email"] for item in recipients)
        return {"success_count": len(recipients), "fail_count": 0, "recipient_status": [], "failures": []}

    monkeypatch.setattr(sender, "_send_email_to_records", fake_send)
    monkeypatch.setattr(sender, "save_send_audit", lambda *args: {"full_count": 0, "lite_count": 1, "skipped_count": 0})
    monkeypatch.setattr(sender, "update_send_audit_results", lambda date, audit, *args, **kwargs: audit)
    result = sender.send_segmented_email(
        "subject", "full", "<p>full</p>", "lite", "<p>lite</p>",
        delivery_date="2026-10-12", test_mode=False,
        segments=sender.split_recipient_records(table["records"], today="2026-10-12"),
        recipient_source="OSS:test", subscribers_table=table,
    )
    assert sent == ["user@example.com"]
    assert result["success_count"] == 1
    assert result["subscribers_warnings"]
    assert result["subscribers_read_only"] is True
    assert result["subscribers_write_skipped"] is True
    assert not result["subscribers_backup_ok"]
    assert result["subscribers_write_skip_reason"] == "damaged_descriptive_fields"


def test_clearing_warning_does_not_allow_overwriting_damaged_source(monkeypatch):
    setup_oss(monkeypatch)
    monkeypatch.setattr(sender.requests, "put", lambda *args, **kwargs: pytest.fail("must not write"))
    table = sender.parse_subscribers_csv_table(CSV)
    table["raw_text"] = CSV.replace("中文昵称", "???")
    result = sender.backup_and_save_subscribers_table_to_oss(table)
    assert result["subscribers_write_skip_reason"] == "damaged_descriptive_fields"
