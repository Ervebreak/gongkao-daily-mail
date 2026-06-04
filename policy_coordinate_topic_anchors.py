from __future__ import annotations

from typing import Any


POLICY_FINE_TOPIC_TERMS = [
    "基层减负",
    "形式主义",
    "形式主义隐形变异",
    "留痕",
    "造痕补痕",
    "层层加码",
    "问责",
    "考核",
    "容错",
    "容错纠错",
    "容错纠错机制",
    "抓落实",
]


def _anchor_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_anchor_text(item) for item in value if _anchor_text(item)).strip()
    if isinstance(value, dict):
        return " ".join(_anchor_text(item) for item in value.values() if _anchor_text(item)).strip()
    return " ".join(str(value).split()).strip()


def _anchor_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts: list[str] = []
        for segment in value.replace("；", ";").replace("，", ",").replace("、", ",").split(","):
            for item in segment.split(";"):
                text = _anchor_text(item)
                if text:
                    parts.append(text)
        return parts
    if isinstance(value, list):
        return [_anchor_text(item) for item in value if _anchor_text(item)]
    return [_anchor_text(value)] if _anchor_text(value) else []


def _append_anchor(items: list[str], value: Any) -> None:
    text = _anchor_text(value)
    if text and text not in items:
        items.append(text)


def build_policy_topic_anchors(brief: dict[str, Any]) -> dict[str, Any]:
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    three = brief.get("today_three_things") if isinstance(brief.get("today_three_things"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    framework_map = featured.get("article_framework_map") if isinstance(featured.get("article_framework_map"), dict) else {}

    primary_candidates: list[str] = []
    for value in [
        brief.get("today_theme"),
        three.get("theme"),
        framework_map.get("overall_exam_value"),
        featured.get("one_sentence"),
    ]:
        _append_anchor(primary_candidates, value)

    fine_grained_tags: list[str] = []
    for value in [
        framework_map.get("exam_tags"),
        framework_map.get("overall_exam_value"),
        featured.get("one_sentence"),
        featured.get("three_useful_points"),
        question.get("upper_exam_points"),
    ]:
        for item in _anchor_list(value):
            _append_anchor(fine_grained_tags, item)

    fine_surface = " ".join(primary_candidates + fine_grained_tags)
    for term in POLICY_FINE_TOPIC_TERMS:
        if term in fine_surface:
            _append_anchor(fine_grained_tags, term)

    fallback_theme = _anchor_text(featured.get("theme"))
    if fallback_theme and not primary_candidates and not fine_grained_tags:
        _append_anchor(primary_candidates, fallback_theme)

    query_parts: list[str] = []
    for value in primary_candidates + fine_grained_tags:
        _append_anchor(query_parts, value)

    return {
        "primary_theme": primary_candidates[0] if primary_candidates else fallback_theme,
        "fine_grained_tags": fine_grained_tags,
        "query_text": " ".join(query_parts),
    }
