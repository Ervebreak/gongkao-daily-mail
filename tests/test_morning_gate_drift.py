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
            "content_quality": {
                "status": "fail",
                "can_send": False,
                "issues": [
                    {"severity": "high", "code": "content_quality_p0", "message": "正文存在阻断级问题"},
                ],
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


def test_send_saved_candidate_ignores_daily_question_only_morning_failures(monkeypatch, tmp_path) -> None:
    import candidate_store
    import email_renderer
    import email_sender
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
        lambda payload, enforce_daily_question_structure=False: (
            payload,
            {
                "status": "fail",
                "issues": [{"severity": "high", "code": "daily_question_missing_identity", "path": "brief.daily_question.question"}],
                "unresolved_issues": [{"severity": "high", "code": "daily_question_missing_identity", "path": "brief.daily_question.question", "blocking": True}],
            },
        ),
    )
    monkeypatch.setattr("main.evaluate_selection_quality", lambda brief: {"issues": []})
    monkeypatch.setattr(
        "main.evaluate_all_quality",
        lambda *args, **kwargs: {
            "daily_question": {
                "issues": [
                    {"severity": "high", "code": "missing_question", "path": "brief.daily_question.question"},
                ]
            },
            "content_quality": {
                "status": "fail",
                "can_send": False,
                "issues": [
                    {
                        "severity": "high",
                        "code": "text_truncation",
                        "path": "brief.daily_question.question",
                        "bad_text": "群众争议",
                    }
                ],
            },
        },
    )
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
    monkeypatch.setattr("main.render_lite_email", lambda candidate: {"plain_text": "lite", "html_body": "<p>lite</p>"})
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: metrics_calls.append(kwargs) or {"ok": True})
    try:
        result = send_saved_candidate({"delivery_date": "2026-06-23"})
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)

    assert result["status"] == "ok"
    assert result["mode"] == "morning_send"
    assert metrics_calls[-1]["status"] == "ok"


def test_send_saved_candidate_ignores_daily_question_plain_text_truncation(monkeypatch, tmp_path) -> None:
    import candidate_store
    import email_renderer
    import email_sender
    import harness_metrics
    import pre_send_cleanliness

    original_output_dir = settings.output_dir
    object.__setattr__(settings, "output_dir", tmp_path)
    metrics_calls: list[dict] = []
    candidate = _candidate("2026-06-23")
    candidate["brief"]["daily_question"] = {
        "question": "请你围绕群众对项目推进的争议，谈谈如何回应并推动后续落实",
        "breaking_hint": "先回应疑虑，再公开协商，最后闭环反馈",
    }
    monkeypatch.setattr(candidate_store, "load_candidate", lambda delivery_date: (candidate, {"candidate_storage": "local"}))
    monkeypatch.setattr(email_renderer, "render_plain_text", lambda brief: "群众对项目推进的争议需要回应并推动后续落实")
    monkeypatch.setattr(email_renderer, "render_email_html", lambda brief: "<p>群众对项目推进的争议需要回应并推动后续落实</p>")
    monkeypatch.setattr(
        pre_send_cleanliness,
        "pre_send_cleanliness_guard",
        lambda payload, enforce_daily_question_structure=False: (
            payload,
            {
                "status": "fail",
                "issues": [
                    {
                        "severity": "high",
                        "code": "visible_text_truncation",
                        "path": "plain_text",
                        "bad_text": "群众对项目推进的争议",
                        "blocking": True,
                    }
                ],
                "unresolved_issues": [
                    {
                        "severity": "high",
                        "code": "visible_text_truncation",
                        "path": "plain_text",
                        "bad_text": "群众对项目推进的争议",
                        "blocking": True,
                    }
                ],
            },
        ),
    )
    monkeypatch.setattr("main.evaluate_selection_quality", lambda brief: {"issues": []})
    monkeypatch.setattr(
        "main.evaluate_all_quality",
        lambda *args, **kwargs: {
            "content_quality": {
                "status": "fail",
                "can_send": False,
                "issues": [
                    {
                        "severity": "high",
                        "code": "visible_text_truncation",
                        "path": "plain_text",
                        "bad_text": "群众对项目推进的争议",
                    }
                ],
            }
        },
    )
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
    monkeypatch.setattr("main.render_lite_email", lambda candidate: {"plain_text": "lite", "html_body": "<p>lite</p>"})
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: metrics_calls.append(kwargs) or {"ok": True})
    try:
        result = send_saved_candidate({"delivery_date": "2026-06-23"})
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)

    assert result["status"] == "ok"
    assert result["mode"] == "morning_send"
    assert metrics_calls[-1]["status"] == "ok"
