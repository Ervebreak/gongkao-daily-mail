from __future__ import annotations

import pytest

from pre_send_cleanliness import pre_send_cleanliness_guard


def _payload() -> dict:
    return {
        "brief": {
            "featured_article": {
                "original_reading_focus": "如果点原文，重点看：从追问责任边界入手，避免答",
            },
            "today_takeaway": {
                "framework": "把平台治理、部门协同和群",
                "common_knowledge_points": [],
                "golden_sentences": [],
            },
            "daily_question": {
                "question": "你是某市网信办工作人员，某地出现平台治理问题，请提出对策。",
                "exam_focus": "答题时要同时覆盖平台责任、治理机制和执行抓手三个方面。",
                "breaking_hint": "先定位问题，再提出完整治理思路，最后落到执行闭环。",
                "candidate_answer": "先排查问题，再完善规则，最后压实责任。",
                "thirty_second_answer": "先排查问题，再完善规则，最后压实责任。",
                "output_sentence_template": "关键在于把治理要求落到执行环节。",
            },
            "quick_reads": [
                {"one_sentence": "公开规则和纠偏机制有助于破解供需矛", "exam_value": "用于分析平台治理中的供需失衡。"},
                {"one_sentence": "明确平台审核边界与过错责任", "exam_value": "用于分析平台治理中的责任划分。"},
            ],
        }
    }


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("featured_article.original_reading_focus", "从追问责任边界入手，帮助作答避免空泛。"),
        ("quick_reads[0].one_sentence", "公开规则和纠偏机制有助于破解供需矛盾。"),
        ("quick_reads[1].one_sentence", "明确平台审核边界与过错责任认定。"),
        ("today_takeaway.framework", "把平台治理、部门协同和群众监督结合起来。"),
    ],
)
def test_semantic_truncation_repairs_are_complete(path: str, expected: str) -> None:
    payload = _payload()

    fixed, report = pre_send_cleanliness_guard(payload)

    current = fixed["brief"]
    for part in path.replace("]", "").replace("[", ".").split("."):
        current = current[int(part)] if part.isdigit() else current[part]

    assert current == expected
    assert report["unresolved_issues"] == []


def test_truncated_phrase_is_completed_before_render_or_blocked() -> None:
    payload = _payload()
    payload["brief"]["today_takeaway"]["framework"] = "这些细节是申论对策题拿高"

    fixed, report = pre_send_cleanliness_guard(payload)

    assert "这些细节是申论对策题拿高" not in fixed["brief"]["today_takeaway"]["framework"]
    assert "这些细节是申论对策题拿高" not in fixed.get("plain_text", "")
    assert not any(issue["code"] == "visible_text_truncation" for issue in report["unresolved_issues"])
