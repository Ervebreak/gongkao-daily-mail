from __future__ import annotations

from stage3_structured_constraints import STRUCTURED_FIELD_RULES_V1


def test_stage3_constraints_cover_high_risk_fields() -> None:
    required_terms = [
        "daily_question.candidate_answer",
        "daily_question.thirty_second_answer",
        "today_takeaway.framework",
        "quick_reads[].one_sentence",
        "quick_reads[].exam_value",
        "featured_article.original_reading_focus",
    ]
    for term in required_terms:
        assert term in STRUCTURED_FIELD_RULES_V1


def test_stage3_constraints_block_known_truncated_tails() -> None:
    known_tails = ["清退四", "畅通维", "信息透明", "制度保", "探索收", "这是……最"]
    for tail in known_tails:
        assert tail in STRUCTURED_FIELD_RULES_V1


def test_stage3_constraints_require_structured_answer() -> None:
    assert "总起句 + 3—4个短点 + 收束句" in STRUCTURED_FIELD_RULES_V1
    assert "每个短点45—65字" in STRUCTURED_FIELD_RULES_V1
    assert "不要写成单段长铺陈" in STRUCTURED_FIELD_RULES_V1
