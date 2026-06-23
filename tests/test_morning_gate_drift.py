from __future__ import annotations

import sys
import types

sys.modules.setdefault("requests", types.SimpleNamespace())

from config import settings
from main import send_saved_candidate


def _candidate(delivery_date: str) -> dict:
    return {
        "delivery_date": delivery_date,
        "subject": f"公考晨读 {delivery_date}",
        "brief": {"featured_article": {}, "daily_question": {}},
        "quality_gate": {"overall": "ok", "p0_count": 0, "p0_issues": []},
        "quality": {"final": {}},
    }


def test_send_saved_candidate_blocks_when_current_gate_drifts_to_fail(monkeypatch, tmp_path) -> None:
    import candidate_store
    import email_renderer
    import harness_metrics
    import pre_send_cleanliness

    original_output_dir = settings.output_dir
    object.__setattr__(settings, "output_dir", tmp_path)
    metrics_calls: list[dict] = []
    monkeypatch.setattr(candidate_store, "load_candidate", lambda delivery_date: (_candidate(delivery_date), {"candidate_storage": "local"}))
    monkeypatch.setattr(email_renderer, "render_plain_text", lambda brief: "plain")
    monkeypatch.setattr(email_renderer, "render_email_html", lambda brief: "<p>html</p>")
    monkeypatch.setattr(
        pre_send_cleanliness,
        "pre_send_cleanliness_guard",
        lambda payload, enforce_daily_question_structure=False: (payload, {"status": "ok", "unresolved_issues": [], "issues": []}),
    )
    monkeypatch.setattr("main.evaluate_selection_quality", lambda brief: {"issues": []})
    monkeypatch.setattr(
        "main.evaluate_all_quality",
        lambda *args, **kwargs: {
            "daily_question": {
                "issues": [
                    {"severity": "high", "code": "missing_question", "message": "今日一题缺失"},
                ]
            }
        },
    )
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: metrics_calls.append(kwargs) or {"ok": True})
    try:
        result = send_saved_candidate({"delivery_date": "2026-06-23"})
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)

    assert result["status"] == "blocked"
    assert result["reason"] == "morning_gate_drift"
    assert result["stored_quality_gate"]["overall"] == "ok"
    assert result["current_quality_gate"]["overall"] == "fail"
    assert metrics_calls[-1]["status"] == "blocked"
    assert metrics_calls[-1]["reason"] == "morning_gate_drift"


def test_send_saved_candidate_blocks_on_morning_recheck_error_in_prod(monkeypatch, tmp_path) -> None:
    import candidate_store
    import email_renderer
    import harness_metrics
    import pre_send_cleanliness

    original_output_dir = settings.output_dir
    object.__setattr__(settings, "output_dir", tmp_path)
    metrics_calls: list[dict] = []
    monkeypatch.setattr(candidate_store, "load_candidate", lambda delivery_date: (_candidate(delivery_date), {"candidate_storage": "local"}))
    monkeypatch.setattr(email_renderer, "render_plain_text", lambda brief: "plain")
    monkeypatch.setattr(email_renderer, "render_email_html", lambda brief: "<p>html</p>")
    monkeypatch.setattr(
        pre_send_cleanliness,
        "pre_send_cleanliness_guard",
        lambda payload, enforce_daily_question_structure=False: (payload, {"status": "ok", "unresolved_issues": [], "issues": []}),
    )
    monkeypatch.setattr("main.evaluate_selection_quality", lambda brief: {"issues": []})

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("main.evaluate_all_quality", _raise)
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: metrics_calls.append(kwargs) or {"ok": True})
    try:
        result = send_saved_candidate({"delivery_date": "2026-06-23"})
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)

    assert result["status"] == "blocked"
    assert result["reason"] == "morning_gate_recheck_error"
    assert result["error"] == "boom"
    assert metrics_calls[-1]["status"] == "blocked"
    assert metrics_calls[-1]["reason"] == "morning_gate_recheck_error"
