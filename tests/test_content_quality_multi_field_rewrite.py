from __future__ import annotations

from content_quality_reviewer import _normalize_review


def test_truncation_error_generates_multiple_field_rewrite_targets() -> None:
    raw = {
        "overall_score": 70,
        "score": 70,
        "can_send": False,
        "risk_level": "high",
        "scores": {
            "topic_fit": 18,
            "user_safety": 15,
            "exam_value": 18,
            "source_alignment": 14,
            "information_gain": 8,
            "naturalness": 8,
            "module_coherence": 4,
            "cleanliness": 4,
        },
        "issues": [
            {
                "severity": "high",
                "code": "truncation_error",
                "message": "original_reading_focus 出现 避免答，quick_reads[0] 出现 供需矛，quick_reads[1] 出现 过错责任，today_takeaway.framework 出现 和群。",
            }
        ],
        "raw_review": {
            "notes": "original_reading_focus 避免答 / quick_reads[0] 供需矛 / quick_reads[1] 过错责任 / today_takeaway.framework 和群"
        },
    }

    result = _normalize_review(raw, model="mock")
    fields = {item["field"] for item in result["rewrite_targets"]}

    assert "brief.featured_article.original_reading_focus" in fields
    assert "brief.quick_reads[0].one_sentence" in fields
    assert "brief.quick_reads[1].one_sentence" in fields
    assert "brief.today_takeaway.framework" in fields

