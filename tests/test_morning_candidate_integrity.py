from __future__ import annotations

import copy

from fact_evidence import current_fact_review_binding
from morning_candidate_integrity import (
    BOUND_CONTENT_REVIEW_KEY,
    SEND_SNAPSHOT_KEY,
    attach_candidate_send_snapshot,
    content_quality_review_binding_is_current,
    restore_bound_render_snapshot,
    validate_live_content_quality_review,
)


def _brief() -> dict:
    return {
        "email_subject": "测试晨读",
        "today_theme": "测试主题",
        "featured_article": {"title": "测试主文", "source": "人民日报", "url": "https://example.com/a"},
        "daily_question": {"question": "【模拟情境】你是工作人员，请提出建议。"},
        "_source_evidence": {
            "schema_version": 1,
            "source_set_hash": "source-set-test",
            "items": {},
            "all_verified": True,
        },
    }


def _review(brief: dict) -> dict:
    binding = current_fact_review_binding(brief)
    return {
        "ok": True,
        "status": "ok",
        "score": 93,
        "can_send": True,
        "scores": {
            "topic_fit": 19,
            "user_safety": 14,
            "exam_value": 19,
            "source_alignment": 14,
            "information_gain": 9,
            "naturalness": 8,
            "module_coherence": 5,
            "cleanliness": 5,
        },
        "checks": binding,
        "issues": [],
    }


def _candidate() -> dict:
    brief = _brief()
    review = _review(brief)
    return {
        "delivery_date": "2026-09-15",
        "subject": "【公考晨读】测试晨读",
        "brief": brief,
        "plain_text": "AUDITED PLAIN TEXT",
        "html_body": "<html><body>AUDITED HTML</body></html>",
        "quality": {"final": {"content_quality": review}},
        "quality_gate": {"overall": "ok", "p0_count": 0, "p0_issues": []},
    }


def test_loaded_candidate_attaches_bound_render_and_semantic_review() -> None:
    candidate = attach_candidate_send_snapshot(_candidate())
    snapshot = candidate["quality"][SEND_SNAPSHOT_KEY]
    assert snapshot["plain_text"] == "AUDITED PLAIN TEXT"
    assert snapshot["html_body"] == "<html><body>AUDITED HTML</body></html>"
    assert BOUND_CONTENT_REVIEW_KEY in candidate["brief"]
    assert content_quality_review_binding_is_current(
        candidate["brief"], candidate["brief"][BOUND_CONTENT_REVIEW_KEY]
    )


def test_bound_render_snapshot_wins_over_send_time_rerender() -> None:
    candidate = attach_candidate_send_snapshot(_candidate())
    data = {
        "brief": candidate["brief"],
        "subject": "【公考晨读】测试晨读",
        "plain_text": "NEW RENDER THAT MUST NOT REPLACE AUDITED OUTPUT",
        "html_body": "<html><body>NEW RENDER</body></html>",
        "quality": candidate["quality"],
    }
    restored, reused = restore_bound_render_snapshot(data)
    assert reused is True
    assert restored["plain_text"] == "AUDITED PLAIN TEXT"
    assert restored["html_body"] == "<html><body>AUDITED HTML</body></html>"


def test_brief_change_invalidates_render_and_semantic_bindings() -> None:
    candidate = attach_candidate_send_snapshot(_candidate())
    changed = copy.deepcopy(candidate)
    changed["brief"]["today_theme"] = "已经变化的主题"
    restored, reused = restore_bound_render_snapshot(
        {
            "brief": changed["brief"],
            "subject": changed["subject"],
            "plain_text": changed["plain_text"],
            "html_body": changed["html_body"],
            "quality": changed["quality"],
        }
    )
    assert reused is False
    assert restored["plain_text"] == changed["plain_text"]
    assert not content_quality_review_binding_is_current(
        changed["brief"], changed["brief"][BOUND_CONTENT_REVIEW_KEY]
    )


def test_content_quality_hook_reuses_stored_review_without_live_llm() -> None:
    candidate = attach_candidate_send_snapshot(_candidate())

    import content_quality_reviewer

    result = content_quality_reviewer.evaluate_content_quality(
        candidate["brief"],
        "DIFFERENT SEND-TIME TEXT",
        "<html>DIFFERENT SEND-TIME HTML</html>",
        test_mode=False,
    )
    assert result["score"] == 93
    assert result["scores"]["source_alignment"] == 14
    assert result["checks"]["morning_review_reused"] is True


def test_malformed_live_review_is_not_misreported_as_zero_content_quality() -> None:
    malformed_normalized_review = {
        "ok": False,
        "status": "fail",
        "score": 0,
        "can_send": False,
        "scores": {
            "topic_fit": 0,
            "user_safety": 0,
            "exam_value": 0,
            "source_alignment": 0,
            "information_gain": 0,
            "naturalness": 0,
            "module_coherence": 0,
            "cleanliness": 0,
        },
        "raw_review": {"one_sentence_judgment": "missing scores"},
        "issues": [],
    }
    result = validate_live_content_quality_review(malformed_normalized_review)
    assert result["status"] == "fail"
    assert result["issues"] == [
        {
            "severity": "high",
            "code": "content_quality_reviewer_error",
            "message": "内容质量审稿返回的 scores 不完整，缺少：topic_fit、user_safety、exam_value、source_alignment、information_gain、naturalness、module_coherence、cleanliness",
        }
    ]
    assert all(issue["code"] != "low_content_quality" for issue in result["issues"])
