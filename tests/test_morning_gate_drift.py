from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from pathlib import Path

sys.modules.setdefault("requests", types.SimpleNamespace())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from main import send_saved_candidate


def _candidate(delivery_date: str) -> dict:
    return {
        "delivery_date": delivery_date,
        "subject": f"[audited] 公考晨读 {delivery_date}",
        "plain_text": "stored reviewed plain text",
        "html_body": "<html><body>stored reviewed html</body></html>",
        "brief": {"featured_article": {"title": "stored reviewed brief"}},
        "quality_gate": {"overall": "ok", "p0_count": 0, "p0_issues": []},
        "quality": {"final": {"content_quality": {"status": "ok"}}},
    }


def _forbid(*args, **kwargs):
    raise AssertionError("morning_send must not re-render or re-run quality checks")


@contextmanager
def _settings_override(tmp_path, *, send_email: bool | None = None):
    original_output_dir = settings.output_dir
    original_send_email = settings.send_email
    object.__setattr__(settings, "output_dir", tmp_path)
    if send_email is not None:
        object.__setattr__(settings, "send_email", send_email)
    try:
        yield
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)
        object.__setattr__(settings, "send_email", original_send_email)


def _configure_send(monkeypatch, candidate: dict) -> tuple[list[dict], list[tuple]]:
    import candidate_store
    import email_renderer
    import email_sender
    import harness_metrics
    import pre_send_cleanliness

    metrics_calls: list[dict] = []
    send_calls: list[tuple] = []
    monkeypatch.setattr(candidate_store, "load_candidate", lambda delivery_date: (candidate, {"candidate_storage": "oss"}))
    monkeypatch.setattr(email_renderer, "render_plain_text", _forbid)
    monkeypatch.setattr(email_renderer, "render_email_html", _forbid)
    monkeypatch.setattr(pre_send_cleanliness, "pre_send_cleanliness_guard", _forbid)
    monkeypatch.setattr("main.evaluate_selection_quality", _forbid)
    monkeypatch.setattr("main.evaluate_all_quality", _forbid)
    monkeypatch.setattr("main.shared_evaluate_weekly_pdf_quality", _forbid)
    monkeypatch.setattr(
        email_sender,
        "load_subscriber_table_for_segmentation",
        lambda test_mode=False: ({"records": []}, "local"),
    )
    monkeypatch.setattr(
        email_sender,
        "split_recipient_records",
        lambda records, today=None: {"full": [], "lite": [], "skipped": [], "variant_counts": {}},
    )
    monkeypatch.setattr(
        email_sender,
        "save_send_audit",
        lambda delivery_date, segments, recipient_source: {
            "full_count": 0,
            "lite_count": 0,
            "skipped_count": 0,
        },
    )
    monkeypatch.setattr(
        email_sender,
        "send_segmented_email",
        lambda *args, **kwargs: send_calls.append(args)
        or {"success_count": 0, "fail_count": 0, "full_count": 0, "lite_count": 0, "skipped_count": 0},
    )
    monkeypatch.setattr("main.render_lite_email", lambda value: {"plain_text": "lite", "html_body": "<p>lite</p>"})
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: metrics_calls.append(kwargs) or {"ok": True})
    return metrics_calls, send_calls


def test_send_saved_candidate_uses_stored_audited_artifacts_without_recheck(monkeypatch, tmp_path) -> None:
    candidate = _candidate("2026-06-23")
    expected_subject = candidate["subject"]
    expected_plain = candidate["plain_text"]
    expected_html = candidate["html_body"]
    metrics_calls, send_calls = _configure_send(monkeypatch, candidate)

    with _settings_override(tmp_path, send_email=True):
        result = send_saved_candidate({"delivery_date": "2026-06-23"})

    assert result["status"] == "ok"
    assert result["mode"] == "morning_send"
    assert candidate["subject"] == expected_subject
    assert candidate["plain_text"] == expected_plain
    assert candidate["html_body"] == expected_html
    assert "stored_quality_gate" not in candidate
    assert "morning_gate_drift" not in candidate
    assert "send_time_cleanliness" not in candidate
    assert send_calls == [(expected_subject, expected_plain, expected_html, "lite", "<p>lite</p>")]
    assert metrics_calls[-1]["status"] == "ok"


def test_send_saved_candidate_still_blocks_a_stored_failed_gate(monkeypatch, tmp_path) -> None:
    import candidate_store
    import harness_metrics

    candidate = _candidate("2026-06-23")
    candidate["quality_gate"] = {
        "overall": "fail",
        "p0_count": 1,
        "p0_issues": [{"code": "stored_failure"}],
    }
    metrics_calls: list[dict] = []
    monkeypatch.setattr(candidate_store, "load_candidate", lambda delivery_date: (candidate, {"candidate_storage": "oss"}))
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: metrics_calls.append(kwargs) or {"ok": True})
    with _settings_override(tmp_path):
        result = send_saved_candidate({"delivery_date": "2026-06-23"})

    assert result["status"] == "blocked"
    assert result["reason"] == "quality_gate_fail"
    assert result["quality_gate"] == candidate["quality_gate"]
    assert metrics_calls[-1]["reason"] == "quality_gate_fail"


def test_send_saved_candidate_blocks_when_stored_artifact_is_missing(monkeypatch, tmp_path) -> None:
    import candidate_store
    import harness_metrics

    candidate = _candidate("2026-06-23")
    candidate["html_body"] = ""
    metrics_calls: list[dict] = []
    monkeypatch.setattr(candidate_store, "load_candidate", lambda delivery_date: (candidate, {"candidate_storage": "oss"}))
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: metrics_calls.append(kwargs) or {"ok": True})
    with _settings_override(tmp_path):
        result = send_saved_candidate({"delivery_date": "2026-06-23"})

    assert result["status"] == "blocked"
    assert result["reason"] == "candidate_artifact_missing"
    assert result["missing_artifacts"] == ["html_body"]
    assert metrics_calls[-1]["reason"] == "candidate_artifact_missing"


def test_weekly_candidate_uses_stored_gate_without_quality_recheck(monkeypatch, tmp_path) -> None:
    import candidate_store

    candidate = _candidate("2026-06-29")
    candidate["candidate_type"] = "weekly_pdf"
    candidate["weekly_pdf"] = {"oss_pdf_path": "oss://bucket/review.pdf"}
    monkeypatch.setattr(candidate_store, "load_candidate", lambda delivery_date: (candidate, {"candidate_storage": "oss"}))
    monkeypatch.setattr("main.shared_evaluate_weekly_pdf_quality", _forbid)
    monkeypatch.setattr(
        "main.send_weekly_pdf_candidate",
        lambda **kwargs: {
            "status": "ok",
            "mode": "weekly_pdf",
            "candidate": kwargs["candidate"],
        },
    )
    with _settings_override(tmp_path):
        result = send_saved_candidate({"delivery_date": "2026-06-29"})

    assert result["status"] == "ok"
    assert result["mode"] == "weekly_pdf"
    assert result["candidate"] is candidate
