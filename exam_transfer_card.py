from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values() if _text(item))
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clip_text(value: Any, limit: int) -> str:
    text = _text(value).replace("...", "").replace("……", "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    head = text[:limit].rstrip("，、：:；; ")
    cut = max(head.rfind(mark) for mark in "。；;！？")
    if cut >= max(12, int(limit * 0.55)):
        return head[: cut + 1].strip()
    return head.rstrip("，、：:和与及并但通过")


def _strip_display_prefix(value: Any, *prefixes: str) -> str:
    text = _text(value)
    candidates = prefixes or (
        "可用表达",
        "换成考场话",
        "考场话",
        "审题关键",
        "作答主线",
    )
    changed = True
    while changed:
        changed = False
        for prefix in candidates:
            clean_prefix = str(prefix or "").strip()
            if not clean_prefix:
                continue
            for candidate in (clean_prefix, f"{clean_prefix}：", f"{clean_prefix}:"):
                if text.startswith(candidate):
                    text = text[len(candidate):].strip()
                    changed = True
                    break
            if changed:
                break
    return text


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return default


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_angle(value: Any) -> str:
    if isinstance(value, dict):
        label = _text(value.get("label") or value.get("title") or value.get("name"))
        content = _text(value.get("content") or value.get("text") or value.get("summary"))
        merged = f"{label}：{content}" if label and content else (label or content)
        return _clip_text(merged, 42)
    text = _strip_display_prefix(value)
    if not text:
        return ""
    for mark in ("：", ":"):
        if mark in text:
            label, content = text.split(mark, 1)
            label = label.strip()
            content = content.strip()
            if label and content:
                return _clip_text(f"{label}：{content}", 42)
    return _clip_text(text, 42)


def _dedupe_keep_order(items: list[str], limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _text(item)
        key = text.replace("：", "").replace(":", "").replace(" ", "")
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def _quotes_distinct(left: str, right: str) -> bool:
    left_key = left.replace("，", "").replace("。", "").replace("、", "").replace(" ", "")
    right_key = right.replace("，", "").replace("。", "").replace("、", "").replace(" ", "")
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return False
    shorter = left_key if len(left_key) <= len(right_key) else right_key
    longer = right_key if shorter == left_key else left_key
    return shorter not in longer


def _fallback_transfer_summary(featured: dict[str, Any], question: dict[str, Any], angles: list[str]) -> str:
    scenarios = _dedupe_keep_order(
        [
            _text(featured.get("theme")),
            _text(question.get("question_type")),
            _text(question.get("topic_category")),
            *[_normalize_angle(item).split("：", 1)[0] for item in angles[:3]],
        ],
        limit=4,
    )
    if scenarios:
        return _clip_text(
            f"这篇文章适合迁移到{'、'.join(scenarios[:4])}类综合分析、对策推进和面试实务场景，重点不是复述事件，而是把治理判断转成可执行的答题表达。",
            140,
        )
    return "这篇文章适合迁移到综合分析、基层治理和公共服务优化类题目，关键是把现实矛盾转成治理思路、执行路径和闭环表达。"


def _fallback_expression(featured: dict[str, Any], question: dict[str, Any], takeaway: dict[str, Any]) -> str:
    golden = _as_list(takeaway.get("golden_sentences"))
    golden_sentence = ""
    if golden:
        first = golden[0]
        golden_sentence = _text(first.get("sentence")) if isinstance(first, dict) else _text(first)
    return _clip_text(
        _strip_display_prefix(
            _first_text(
                featured.get("rewritable_expression"),
                golden_sentence,
                question.get("thirty_second_answer"),
                default="不能只停留在表态层面，关键是把问题找准、把措施做实、把结果反馈到位。",
            ),
            "可用表达",
        ),
        80,
    )


def build_exam_transfer_card(brief: dict[str, Any]) -> dict[str, Any]:
    featured = _ensure_dict(brief.get("featured_article"))
    question = _ensure_dict(brief.get("daily_question"))
    takeaway = _ensure_dict(brief.get("today_takeaway"))
    coordinate = _ensure_dict(brief.get("policy_coordinate"))
    existing = _ensure_dict(brief.get("exam_transfer_card"))

    policy_quote = _clip_text(coordinate.get("policy_quote"), 120)
    policy_source = _clip_text(coordinate.get("policy_source"), 60)
    authoritative_quote = _clip_text(coordinate.get("authoritative_quote"), 120)
    authoritative_source = _clip_text(coordinate.get("authoritative_source"), 60)
    policy_score = _to_float(coordinate.get("policy_match_score"))
    qiushi_score = _to_float(coordinate.get("qiushi_match_score"))
    display_type = _text(coordinate.get("display_evidence_type")).lower()

    both_allowed = (
        display_type == "both"
        and
        policy_quote
        and policy_source
        and authoritative_quote
        and authoritative_source
        and policy_score >= 75
        and qiushi_score >= 70
        and _quotes_distinct(policy_quote, authoritative_quote)
    )
    if both_allowed:
        evidence_type = "both"
    elif authoritative_quote and authoritative_source and (display_type == "qiushi" or qiushi_score >= 70):
        evidence_type = "qiushi"
        policy_quote = ""
        policy_source = ""
    elif policy_quote and policy_source and (display_type == "policy" or policy_score >= 75):
        evidence_type = "policy"
        authoritative_quote = ""
        authoritative_source = ""
    else:
        evidence_type = "none"
        policy_quote = ""
        policy_source = ""
        authoritative_quote = ""
        authoritative_source = ""

    existing_angles = [_normalize_angle(item) for item in _as_list(existing.get("transfer_angles"))]
    coordinate_angles = [_normalize_angle(item) for item in _as_list(coordinate.get("answer_angles"))]
    question_angles = [_normalize_angle(item) for item in _as_list(question.get("answer_framework"))[:5]]
    featured_angles = [_normalize_angle(item) for item in _as_list(featured.get("three_useful_points"))[:3]]
    transfer_angles = _dedupe_keep_order(
        [*existing_angles, *coordinate_angles, *question_angles, *featured_angles],
        limit=5,
    )
    if len(transfer_angles) < 3:
        transfer_angles = _dedupe_keep_order(
            [
                *transfer_angles,
                "先把表面矛盾说清：明确题目谈的到底是哪类现实堵点。",
                "再把深层逻辑讲透：说明问题为什么会卡在执行、协同或反馈环节。",
                "最后落到治理闭环：把回应诉求、部门协同和结果跟踪接起来。",
            ],
            limit=5,
        )

    surface_issue = _clip_text(
        _first_text(
            existing.get("surface_issue"),
            featured.get("one_sentence"),
            _as_list(featured.get("three_useful_points"))[:1],
            featured.get("core_viewpoint"),
            default=f"文章表面讲的是{_text(featured.get('title') or brief.get('today_theme') or '一个治理场景')}里的现实问题。",
        ),
        100,
    )
    deep_logic = _clip_text(
        _strip_display_prefix(
            _first_text(
                existing.get("deep_logic"),
                _as_list(featured.get("exam_use"))[:1],
                _as_list(featured.get("usable_for_exam"))[:1],
                question.get("exam_focus"),
                coordinate.get("article_connection"),
                default="真正考的不是事件本身，而是能否把现实矛盾转成治理判断、执行路径和可复述的考场表达。",
            ),
            "换成考场话",
            "考场话",
            "审题关键",
        ),
        140,
    )
    exam_transfer = _clip_text(
        _first_text(
            existing.get("exam_transfer"),
            coordinate.get("exam_transfer"),
            default=_fallback_transfer_summary(featured, question, transfer_angles),
        ),
        150,
    )
    exam_expression = _fallback_expression(featured, question, takeaway)
    if _text(existing.get("exam_expression")):
        exam_expression = _clip_text(_strip_display_prefix(existing.get("exam_expression"), "可用表达"), 80)

    return {
        "surface_issue": surface_issue,
        "deep_logic": deep_logic,
        "evidence_type": evidence_type,
        "policy_quote": policy_quote,
        "policy_source": policy_source,
        "authoritative_quote": authoritative_quote,
        "authoritative_source": authoritative_source,
        "transfer_angles": transfer_angles[:5],
        "exam_transfer": exam_transfer,
        "exam_expression": exam_expression,
    }


def apply_exam_transfer_card(brief: dict[str, Any]) -> dict[str, Any]:
    brief["exam_transfer_card"] = build_exam_transfer_card(brief)
    return brief
