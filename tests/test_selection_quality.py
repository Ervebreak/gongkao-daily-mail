from __future__ import annotations

from quality_gate import evaluate_selection_quality


def _base_brief() -> dict:
    return {
        "_llm_two_stage": {"selection": {"featured": {}}},
        "featured_article": {
            "title": "基层治理要把群众诉求办成闭环",
            "url": "https://example.com/featured",
            "theme": "基层治理",
        },
        "final_selection": {
            "featured": {
                "title": "基层治理要把群众诉求办成闭环",
                "url": "https://example.com/featured",
            }
        },
        "content_quality": {"status": "ok", "can_send": True, "risk_level": "medium"},
        "daily_question": {"question": "某地基层治理中群众诉求复杂，请提出对策。"},
        "today_three_things": {"theme": "基层治理"},
    }


def test_selection_metadata_missing_does_not_become_p0_when_final_selection_is_valid() -> None:
    brief = _base_brief()
    brief["_llm_two_stage"]["selection"]["featured"] = {"title": "", "url": "", "total_score": 0}

    report = evaluate_selection_quality(brief)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["status"] == "review"
    assert "selection_metadata_missing" in codes
    assert "weak_featured_selection" not in codes
    assert report["checks"]["selection_metadata_missing"] is True
    assert report["checks"]["final_selection_present"] is True
    assert report["checks"]["score_source"] == "final_selection_fallback"


def test_real_low_selection_score_still_blocks() -> None:
    brief = _base_brief()
    brief["_llm_two_stage"]["selection"]["featured"] = {
        "title": "基层治理要把群众诉求办成闭环",
        "url": "https://example.com/featured",
        "total_score": 60,
    }

    report = evaluate_selection_quality(brief)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["status"] == "fail"
    assert "weak_featured_selection" in codes
    assert report["checks"]["selection_metadata_missing"] is False
    assert report["checks"]["score_source"] == "llm_selection"


def test_missing_final_selection_still_blocks() -> None:
    brief = _base_brief()
    brief["_llm_two_stage"]["selection"]["featured"] = {"title": "", "url": "", "total_score": 0}
    brief["featured_article"] = {}
    brief["final_selection"] = {}

    report = evaluate_selection_quality(brief)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["status"] == "fail"
    assert "missing_final_selection" in codes
    assert report["checks"]["final_selection_present"] is False


def test_sensitive_topic_with_missing_metadata_only_reviews_when_final_selection_is_valid() -> None:
    brief = _base_brief()
    brief["_llm_two_stage"]["selection"]["featured"] = {"title": "", "url": "", "total_score": 0}
    brief["email_subject"] = "彩礼治理如何回到基层协商"
    brief["today_theme"] = "彩礼治理"
    brief["daily_question"]["question"] = "某地围绕彩礼治理引发争议，请提出治理对策。"

    report = evaluate_selection_quality(brief)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["status"] == "review"
    assert "selection_metadata_missing" in codes
    assert "sensitive_topic_needs_review" in codes
    assert "weak_featured_selection" not in codes
    assert report["checks"]["score_source"] == "final_selection_fallback"
