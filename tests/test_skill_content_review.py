import copy

import pytest

import content_quality_reviewer
from brief_schema import ensure_brief_schema
from content_quality_reviewer import DIMENSION_LIMITS
from email_renderer import render_email_html, render_plain_text
from quality_gate import build_gate_from_quality_map, evaluate_all_quality
from skill_content_review import REQUIRED_SECTIONS, evaluate_skill_content_review, review_binding


@pytest.fixture
def audit_case():
    # Contract-only fixture; it is never published as a live semantic review.
    brief = {"date": "2026-10-03", "email_subject": "部门协同如何落地",
             "_source_evidence": {"source_set_hash": "test-evidence", "items": {"featured": {"verification_status": "verified"}}}}
    brief, _ = ensure_brief_schema(brief, brief["date"])
    from lite_email_renderer import render_lite_email
    render_lite_email({"brief": brief})
    review = {"schema_version": 1, "review_origin": "skill", "delivery_date": brief["date"],
              "reviewer": {"name": "fixture", "model": "fixture-reviewer"},
              "reviewed_at": "2026-10-03T20:00:00+08:00", "binding": review_binding(brief),
              "dimension_reviews": {key: {"score": limit, "reason": f"Test evidence for {key}"} for key, limit in DIMENSION_LIMITS.items()},
              "section_checks": {key: {"status": "pass", "reason": f"Test evidence for {key}"} for key in REQUIRED_SECTIONS},
              "overall_score": 100, "risk_level": "low", "issues": [], "one_sentence_judgment": "Fixture contract review"}
    return brief, review


def check(brief, review):
    result = evaluate_skill_content_review(brief, render_plain_text(brief), render_email_html(brief), review)
    return result, build_gate_from_quality_map({"content_quality": result})


def test_skill_mode_never_calls_api_even_when_audit_missing(monkeypatch, audit_case):
    def forbidden(*args, **kwargs):
        raise AssertionError("Model API must not be called")
    monkeypatch.setattr(content_quality_reviewer, "evaluate_content_quality", forbidden)
    brief, review = audit_case
    for supplied in (review, None):
        quality = evaluate_all_quality(copy.deepcopy(brief), render_plain_text(brief), render_email_html(brief),
                                       test_invocation=False, content_review_mode="skill", skill_review=supplied)
        assert quality["content_quality"]["checks"]["additional_model_api_called"] is False
    assert check(brief, None)[1]["p0_count"] > 0


def test_valid_bound_audit_uses_existing_thresholds(audit_case):
    brief, review = audit_case
    assert check(brief, review)[0]["status"] == "ok"
    review["dimension_reviews"]["user_safety"]["score"] = 9
    review["overall_score"] = 94
    assert check(brief, review)[1]["p0_count"] > 0


@pytest.mark.parametrize("mutation", ["content", "source", "lite", "date", "incomplete", "mock", "score"])
def test_stale_or_incomplete_audit_blocks(audit_case, mutation):
    brief, review = audit_case
    if mutation == "content":
        brief["daily_question"] = {"candidate_answer": "Changed answer"}
    elif mutation == "source":
        brief["_source_evidence"]["source_set_hash"] = "changed"
    elif mutation == "lite":
        review["binding"]["lite_payload_hash"] = "changed"
    elif mutation == "date":
        review["delivery_date"] = "2026-10-04"
    elif mutation == "incomplete":
        del review["section_checks"]["cta"]
    elif mutation == "mock":
        review["reviewer"]["model"] = "mock"
    else:
        review["overall_score"] = 99
    assert check(brief, review)[1]["p0_count"] > 0


def test_lite_block_and_required_review_are_not_lost(audit_case):
    brief, review = audit_case
    review["section_checks"]["lite"] = {"status": "block", "reason": "Reference answer leaked"}
    assert check(brief, review)[1]["p0_count"] > 0
    review["section_checks"]["lite"]["status"] = "review"
    assert check(brief, review)[0]["status"] == "review"
    assert check(brief, review)[0]["can_send"] is False


def test_embedded_quality_cannot_implicitly_disable_api(monkeypatch, audit_case):
    brief, _ = audit_case
    brief["_skill_review"] = {"status": "ok"}
    called = []
    def api(*args, **kwargs):
        called.append(True)
        return {"status": "fail", "can_send": False, "issues": []}
    monkeypatch.setattr(content_quality_reviewer, "evaluate_content_quality", api)
    evaluate_all_quality(brief, render_plain_text(brief), render_email_html(brief), test_invocation=False)
    assert called == [True]


def test_validator_rejects_stale_saved_html_before_cleaning(audit_case):
    from scripts.validate_daily_brief import build_report
    brief, review = audit_case
    report = build_report(brief, plain_text=render_plain_text(brief), html_body="<p>stale artifact</p>",
                          content_review_mode="skill", skill_review=review)
    assert report["overall"] == "block"
    assert any("快照" in x["message"] for x in report["p0_issues"])


def test_binding_helper_does_not_change_candidate(audit_case):
    brief, _ = audit_case
    del brief["lite_paid_highlight"]
    before = copy.deepcopy(brief)
    review_binding(brief)
    assert brief == before
