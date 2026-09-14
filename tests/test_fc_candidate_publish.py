from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import fc_candidate_publish as target


TOKEN = "daily-publish-test-token-that-must-not-leak"


def _score_detail() -> dict[str, int]:
    return {
        "exam_conversion": 27,
        "problem_awareness": 18,
        "scenario_specificity": 13,
        "contradiction_tension": 12,
        "material_value": 9,
        "authority_timeliness": 9,
    }


def _candidate(date: str = "2026-09-14") -> dict:
    evidence = {
        "schema_version": 1,
        "source_set_hash": "source-hash",
        "all_verified": True,
        "items": {
            "https://example.com/article": {
                "verification_status": "verified",
                "title": "测试文章",
                "url": "https://example.com/article",
            }
        },
    }
    fact_review = {
        "schema_version": 2,
        "ok": True,
        "status": "ok",
        "score": 100,
        "issues": [],
        "binding": {
            "source_set_hash": "source-hash",
            "candidate_fact_hash": "fact-hash",
            "candidate_content_hash": "content-hash",
        },
    }
    score_detail = _score_detail()
    brief = {
        "date": date,
        "_source_evidence": evidence,
        "_fact_review": fact_review,
        "_llm_two_stage": {
            "selection": {
                "featured": {
                    "title": "测试文章",
                    "total_score": sum(score_detail.values()),
                    "score_detail": score_detail,
                }
            }
        },
    }
    gate = {"overall": "ok", "p0_count": 0, "p0_issues": []}
    return {
        "schema_version": 1,
        "generated_at": "2026-09-13T20:00:00+08:00",
        "delivery_date": date,
        "subject": "【公考晨读】测试主题",
        "brief": brief,
        "plain_text": "PLAIN",
        "html_body": "HTML",
        "quality": {"final": {}, "gate": gate},
        "quality_gate": dict(gate),
        "source_evidence": evidence,
        "fact_review": fact_review,
        "article_stats": {},
        "final_selection": {},
        "llm_trace_summary": {},
    }


def _event(candidate: dict, token: str = TOKEN) -> dict:
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "body": json.dumps({"candidate": candidate}, ensure_ascii=False),
    }


def _body(response: dict) -> dict:
    return json.loads(response["body"])


@pytest.fixture(autouse=True)
def _publisher_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAILY_PUBLISH_TOKEN", TOKEN)
    monkeypatch.setattr(target, "settings", SimpleNamespace(candidate_storage="oss", oss_bucket="test-bucket"))
    monkeypatch.setattr(target, "render_plain_text", lambda _brief: "PLAIN")
    monkeypatch.setattr(target, "render_email_html", lambda _brief: "HTML")
    monkeypatch.setattr(target, "fact_review_binding_is_current", lambda _brief, _review: True)
    monkeypatch.setattr(target.candidate_store, "load_candidate", lambda: (None, {"candidate_oss_read_ok": False}))
    monkeypatch.setattr(
        target.candidate_store,
        "save_candidate",
        lambda candidate: {
            "candidate_saved": True,
            "candidate_storage": "oss",
            "candidate_oss_write_ok": True,
            "candidate_oss_latest_write_ok": True,
            "candidate_oss_path": f"oss://test-bucket/gongkao-morning-mailer/candidates/{candidate['delivery_date']}.json",
        },
    )
    monkeypatch.setattr(
        target.candidate_store,
        "candidate_object_key",
        lambda date: f"gongkao-morning-mailer/candidates/{date}.json",
    )
    monkeypatch.setattr(
        target.candidate_store,
        "latest_object_key",
        lambda: "gongkao-morning-mailer/candidates/latest.json",
    )


def test_unauthorized_request_is_rejected() -> None:
    response = target.handler(_event(_candidate(), "wrong"), None)
    assert response["statusCode"] == 401
    assert _body(response)["issue_code"] == "daily_publish_auth_failed"


def test_invalid_json_is_rejected() -> None:
    response = target.handler(
        {"headers": {"Authorization": f"Bearer {TOKEN}"}, "body": "not-json"},
        None,
    )
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_input_invalid"


def test_request_allows_only_candidate_top_level_key() -> None:
    response = target.handler(
        {
            "headers": {"Authorization": f"Bearer {TOKEN}"},
            "body": json.dumps({"candidate": _candidate(), "force": True}),
        },
        None,
    )
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_input_invalid"


def test_date_mismatch_is_rejected() -> None:
    candidate = _candidate()
    candidate["brief"]["date"] = "2026-09-15"
    response = target.handler(_event(candidate), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_date_mismatch"


def test_quality_gate_failure_is_rejected() -> None:
    candidate = _candidate()
    candidate["quality_gate"]["overall"] = "fail"
    candidate["quality"]["gate"]["overall"] = "fail"
    candidate["quality_gate"]["p0_count"] = 1
    candidate["quality"]["gate"]["p0_count"] = 1
    response = target.handler(_event(candidate), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_quality_blocked"


def test_quality_gate_drift_is_rejected_before_normalization() -> None:
    candidate = _candidate()
    candidate["quality"]["gate"] = {"overall": "fail", "p0_count": 1}
    response = target.handler(_event(candidate), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_quality_state_drift"


def test_unverified_source_evidence_is_rejected() -> None:
    candidate = _candidate()
    candidate["source_evidence"]["all_verified"] = False
    candidate["brief"]["_source_evidence"] = candidate["source_evidence"]
    response = target.handler(_event(candidate), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_source_evidence_invalid"


def test_stale_fact_review_binding_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target, "fact_review_binding_is_current", lambda _brief, _review: False)
    response = target.handler(_event(_candidate()), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_fact_review_stale"


def test_fact_review_must_be_final_ok() -> None:
    candidate = _candidate()
    candidate["fact_review"]["status"] = "review"
    candidate["brief"]["_fact_review"] = candidate["fact_review"]
    response = target.handler(_event(candidate), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_fact_review_invalid"


def test_selection_score_must_equal_six_dimensions() -> None:
    candidate = _candidate()
    candidate["brief"]["_llm_two_stage"]["selection"]["featured"]["total_score"] = 99
    response = target.handler(_event(candidate), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_selection_score_invalid"


def test_selection_score_must_meet_publish_threshold() -> None:
    candidate = _candidate()
    detail = candidate["brief"]["_llm_two_stage"]["selection"]["featured"]["score_detail"]
    detail.update(
        {
            "exam_conversion": 20,
            "problem_awareness": 12,
            "scenario_specificity": 10,
            "contradiction_tension": 9,
            "material_value": 7,
            "authority_timeliness": 7,
        }
    )
    candidate["brief"]["_llm_two_stage"]["selection"]["featured"]["total_score"] = sum(detail.values())
    response = target.handler(_event(candidate), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_selection_score_invalid"


def test_render_drift_is_rejected() -> None:
    candidate = _candidate()
    candidate["html_body"] = "STALE HTML"
    response = target.handler(_event(candidate), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "daily_candidate_render_drift"


def test_older_candidate_cannot_replace_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        target.candidate_store,
        "load_candidate",
        lambda: ({"delivery_date": "2026-09-15"}, {"candidate_oss_read_ok": True}),
    )
    response = target.handler(_event(_candidate("2026-09-14")), None)
    assert response["statusCode"] == 409
    assert _body(response)["issue_code"] == "daily_candidate_stale_publish_rejected"


def test_same_date_candidate_may_replace_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        target.candidate_store,
        "load_candidate",
        lambda: ({"delivery_date": "2026-09-14"}, {"candidate_oss_read_ok": True}),
    )
    response = target.handler(_event(_candidate("2026-09-14")), None)
    assert response["statusCode"] == 200
    assert _body(response)["status"] == "published"


def test_publisher_requires_oss_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target, "settings", SimpleNamespace(candidate_storage="local", oss_bucket="test-bucket"))
    response = target.handler(_event(_candidate()), None)
    assert response["statusCode"] == 503
    assert _body(response)["issue_code"] == "daily_candidate_storage_invalid"


def test_daily_oss_failure_is_not_reported_as_published(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        target.candidate_store,
        "save_candidate",
        lambda _candidate: {
            "candidate_saved": True,
            "candidate_storage": "oss",
            "candidate_oss_write_ok": False,
            "candidate_oss_latest_write_ok": True,
        },
    )
    response = target.handler(_event(_candidate()), None)
    assert response["statusCode"] == 502
    assert _body(response)["issue_code"] == "daily_candidate_oss_write_failed"


def test_latest_oss_failure_is_not_reported_as_published(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        target.candidate_store,
        "save_candidate",
        lambda _candidate: {
            "candidate_saved": True,
            "candidate_storage": "oss",
            "candidate_oss_write_ok": True,
            "candidate_oss_latest_write_ok": False,
        },
    )
    response = target.handler(_event(_candidate()), None)
    assert response["statusCode"] == 502
    assert _body(response)["issue_code"] == "daily_candidate_latest_write_failed"


def test_success_publishes_daily_and_latest() -> None:
    response = target.handler(_event(_candidate()), None)
    body = _body(response)
    assert response["statusCode"] == 200
    assert body["status"] == "published"
    assert body["delivery_date"] == "2026-09-14"
    assert body["daily_write_ok"] is True
    assert body["latest_write_ok"] is True
    assert body["daily_path"].endswith("/2026-09-14.json")
    assert body["latest_path"].endswith("/latest.json")


def test_entrypoint_has_no_model_fetch_send_or_subscriber_dependencies() -> None:
    source = Path(target.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "llm_client",
        "content_quality_reviewer",
        "fetch_articles",
        "generate_brief",
        "rewrite_content_issues",
        "email_sender",
        "send_email(",
        "subscribers",
        "run_daily_brief",
    ):
        assert forbidden not in source
