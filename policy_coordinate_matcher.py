from __future__ import annotations

import re
from typing import Any

from knowledge_base_loader import (
    load_policy_all,
    load_policy_core,
    load_qiushi_article_index,
    load_qiushi_chunks,
    load_qiushi_quotes_candidates,
    load_qiushi_quotes_core,
    load_topic_frameworks,
)


Candidate = dict[str, Any]

FRESHNESS_SCORE = {
    "annual": 8,
    "current_policy_basis": 7,
    "classic_foundational": 6,
    "historical_framework": -6,
}

USAGE_TIER_SCORE = {
    "core": 8,
    "display": 6,
    "background": -8,
    "disabled": -1000,
}

STOPWORDS = {
    "我们",
    "推进",
    "推动",
    "加强",
    "完善",
    "提升",
    "实现",
    "建设",
    "发展",
    "工作",
    "问题",
    "关于",
    "进行",
    "通过",
    "以及",
    "相关",
    "当前",
}

RECENT_POLICY_REPEAT_PENALTY = -120
RECENT_QIUSHI_QUOTE_REPEAT_PENALTY = -90
CONSECUTIVE_FRAMEWORK_REPEAT_PENALTY = -55
THEME_STREAK_PENALTY = -26

TOPIC_ROUTE_RULES = [
    {
        "trigger_keywords": ["外卖", "网络餐饮", "食品安全", "平台", "证照", "后厨", "明厨亮灶", "市场监管"],
        "route_keywords": ["食品安全", "网络餐饮服务", "平台主体责任", "经营许可", "明厨亮灶", "市场监管", "新业态监管"],
    }
]


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_as_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_as_text(item) for item in value.values())
    return str(value)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,，;；、/|]\s*", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def _contains_any(haystack: str, needles: list[str]) -> int:
    compact_haystack = _compact(haystack)
    count = 0
    for needle in needles:
        compact_needle = _compact(needle)
        if compact_needle and compact_needle in compact_haystack:
            count += 1
    return count


def _parse_usage_date(value: Any) -> tuple[int, str]:
    text = str(value or "")[:10]
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", text)
    if not match:
        return (0, "")
    return (int("".join(match.groups())), text)


def _extract_keywords(*values: Any, limit: int = 30) -> list[str]:
    text = _as_text(values)
    candidates = re.findall(r"[\u4e00-\u9fff]{2,12}|[A-Za-z][A-Za-z0-9_-]{2,}", text)
    seen: set[str] = set()
    keywords: list[str] = []
    for item in candidates:
        item = item.strip()
        if not item or item in STOPWORDS or item in seen:
            continue
        seen.add(item)
        keywords.append(item)
        if len(keywords) >= limit:
            break
    return keywords


def policy_topic_route_keywords(*values: Any) -> list[str]:
    combined = _as_text(values)
    compact_combined = _compact(combined)
    routed: list[str] = []
    seen: set[str] = set()
    for rule in TOPIC_ROUTE_RULES:
        triggers = rule.get("trigger_keywords") or []
        if not any(_compact(keyword) in compact_combined for keyword in triggers if keyword):
            continue
        for keyword in rule.get("route_keywords") or []:
            normalized = str(keyword).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            routed.append(normalized)
    return routed


def normalize_article_input(
    article_title: str = "",
    article_summary: str = "",
    article_text: str = "",
    main_theme: str = "",
    sub_themes: Any = None,
    keywords: Any = None,
    exam_scenarios: Any = None,
    article: dict[str, Any] | None = None,
) -> dict[str, Any]:
    article = article or {}
    title = article_title or _as_text(article.get("article_title") or article.get("title"))
    summary = article_summary or _as_text(article.get("article_summary") or article.get("summary") or article.get("abstract"))
    text = article_text or _as_text(article.get("article_text") or article.get("text") or article.get("content") or article.get("body"))
    theme = main_theme or _as_text(article.get("main_theme") or article.get("theme"))
    subs = _as_list(sub_themes if sub_themes is not None else article.get("sub_themes"))
    keys = _as_list(keywords if keywords is not None else article.get("keywords"))
    scenarios = _as_list(exam_scenarios if exam_scenarios is not None else article.get("exam_scenarios"))
    if not keys:
        keys = _extract_keywords(title, summary, text)
    route_keywords = policy_topic_route_keywords(title, summary, text, theme, subs, keys)
    return {
        "article_title": title,
        "article_summary": summary,
        "article_text": text,
        "main_theme": theme,
        "sub_themes": subs,
        "keywords": keys,
        "topic_route_keywords": route_keywords,
        "exam_scenarios": scenarios,
        "combined_text": " ".join([title, summary, text]),
    }


def _is_disabled(item: Candidate) -> bool:
    return _compact(item.get("usage_tier")) == "disabled" or item.get("display_ready") is False


def _is_background(item: Candidate) -> bool:
    return _compact(item.get("usage_tier")) == "background"


def _eligible_policy_from_all(item: Candidate) -> bool:
    return (
        item.get("quote_status") == "clean"
        and item.get("display_ready") is True
        and item.get("theme_confidence") == "high"
        and item.get("usage_tier") not in {"disabled", "background"}
    )


def _score_common(item: Candidate, query: dict[str, Any], *, text_fields: list[str], theme_fields: list[str]) -> tuple[float, dict[str, Any]]:
    main_theme = _as_text(query.get("main_theme"))
    sub_themes = _as_list(query.get("sub_themes"))
    keywords = _as_list(query.get("keywords"))
    topic_route_keywords = _as_list(query.get("topic_route_keywords"))
    exam_scenarios = _as_list(query.get("exam_scenarios"))

    searchable_text = " ".join(_as_text(item.get(field)) for field in text_fields)
    theme_text = " ".join(_as_text(item.get(field)) for field in theme_fields)
    score = 0.0
    reasons: dict[str, Any] = {}
    semantic_hits = 0

    if main_theme and _contains_any(theme_text, [main_theme]):
        score += 35
        semantic_hits += 1
        reasons["main_theme"] = main_theme

    sub_hits = _contains_any(theme_text, sub_themes)
    if sub_hits:
        score += sub_hits * 18
        semantic_hits += sub_hits
        reasons["sub_theme_hits"] = sub_hits

    keyword_text = " ".join([searchable_text, theme_text, _as_text(item.get("article_match_keywords"))])
    keyword_hits = _contains_any(keyword_text, keywords)
    if keyword_hits:
        score += min(keyword_hits, 8) * 5
        semantic_hits += keyword_hits
        reasons["keyword_hits"] = keyword_hits

    route_hits = _contains_any(keyword_text, topic_route_keywords)
    if route_hits:
        score += min(route_hits, 6) * 9
        semantic_hits += route_hits
        reasons["topic_route_hits"] = route_hits

    exam_text = " ".join(
        [
            _as_text(item.get("exam_usage")),
            _as_text(item.get("suitable_question_types")),
            _as_text(item.get("answer_angles")),
            _as_text(item.get("usage_roles")),
        ]
    )
    exam_hits = _contains_any(exam_text, exam_scenarios)
    if exam_hits:
        score += exam_hits * 8
        semantic_hits += exam_hits
        reasons["exam_scenario_hits"] = exam_hits

    priority = item.get("display_priority", item.get("score", 0))
    try:
        priority_score = float(priority or 0)
    except (TypeError, ValueError):
        priority_score = 0
    score += min(priority_score, 10)
    reasons["display_priority"] = priority_score

    tier = _compact(item.get("usage_tier"))
    tier_score = USAGE_TIER_SCORE.get(tier, 0)
    score += tier_score
    if tier:
        reasons["usage_tier"] = tier

    freshness = _compact(item.get("freshness"))
    freshness_score = FRESHNESS_SCORE.get(freshness, 0)
    score += freshness_score
    if freshness:
        reasons["freshness"] = freshness

    if item.get("display_ready") is True:
        score += 4
    if item.get("theme_confidence") == "high":
        score += 5

    text_hits = _contains_any(searchable_text, keywords + sub_themes + ([main_theme] if main_theme else []))
    if text_hits:
        score += min(text_hits, 6) * 3
        semantic_hits += text_hits
        reasons["text_hits"] = text_hits

    reasons["_semantic_hits"] = semantic_hits
    return score, reasons


def _score_policy(item: Candidate, query: dict[str, Any], *, source: str) -> Candidate:
    score, reasons = _score_common(
        item,
        query,
        text_fields=["policy_quote", "short_quote", "plain_explanation", "exam_usage", "article_match_keywords"],
        theme_fields=["theme_level_1", "theme_level_2"],
    )
    if source == "policy_core":
        score += 12
    return {"score": score, "source": source, "id": item.get("policy_id"), "reasons": reasons, "item": item}


def _score_qiushi_quote(item: Candidate, query: dict[str, Any], *, source: str) -> Candidate:
    score, reasons = _score_common(
        item,
        query,
        text_fields=["quote_text", "short_quote", "plain_explanation", "exam_usage", "article_match_keywords", "source_title"],
        theme_fields=["theme_level_1", "theme_level_2"],
    )
    if source == "qiushi_quotes_core":
        score += 10
    elif source == "qiushi_quotes_candidates":
        score -= 12
    return {"score": score, "source": source, "id": item.get("quote_id"), "article_id": item.get("article_id"), "reasons": reasons, "item": item}


def _score_article_index(item: Candidate, query: dict[str, Any]) -> Candidate:
    score, reasons = _score_common(
        item,
        query,
        text_fields=["title", "article_type", "usage_roles", "source_note"],
        theme_fields=["main_theme", "sub_themes"],
    )
    if item.get("status") == "active":
        score += 3
    return {"score": score, "source": "article_index", "id": item.get("article_id"), "reasons": reasons, "item": item}


def _score_chunk(item: Candidate, query: dict[str, Any], boosted_article_ids: set[str]) -> Candidate:
    score, reasons = _score_common(
        item,
        query,
        text_fields=["title", "section_title", "chunk_text", "article_match_keywords"],
        theme_fields=["theme_tags"],
    )
    if item.get("article_id") in boosted_article_ids:
        score += 10
        reasons["article_id_boost"] = item.get("article_id")
    if _is_background(item):
        score -= 8
    return {"score": score, "source": "article_chunks", "id": item.get("chunk_id"), "article_id": item.get("article_id"), "reasons": reasons, "item": item}


def _score_framework(item: Candidate, query: dict[str, Any], boosted_article_ids: set[str]) -> Candidate:
    score, reasons = _score_common(
        item,
        query,
        text_fields=["framework_name", "framework_items", "answer_pattern", "exam_usage", "suitable_question_types"],
        theme_fields=["theme"],
    )
    if item.get("article_id") in boosted_article_ids:
        score += 8
        reasons["article_id_boost"] = item.get("article_id")
    return {"score": score, "source": "topic_frameworks", "id": item.get("framework_id"), "article_id": item.get("article_id"), "reasons": reasons, "item": item}


def _best(scored: list[Candidate], min_score: float = 1) -> Candidate | None:
    if not scored:
        return None
    scored = [row for row in scored if row.get("reasons", {}).get("_semantic_hits", 0) > 0]
    scored = sorted(scored, key=lambda row: row["score"], reverse=True)
    if not scored:
        return None
    return scored[0] if scored[0]["score"] >= min_score else None


def _top(scored: list[Candidate], *, limit: int, min_score: float = 1) -> list[Candidate]:
    return [
        row
        for row in sorted(scored, key=lambda row: row["score"], reverse=True)
        if row["score"] >= min_score and row.get("reasons", {}).get("_semantic_hits", 0) > 0
    ][:limit]


def _public_result(scored: Candidate | None) -> Candidate | None:
    if not scored:
        return None
    result = dict(scored["item"])
    result["_match_score"] = round(scored["score"], 2)
    result["_match_source"] = scored["source"]
    result["_match_reasons"] = scored["reasons"]
    return result


def _recent_usage_context(recent_usage: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = [item for item in (recent_usage or []) if isinstance(item, dict)]
    rows = sorted(rows, key=lambda item: _parse_usage_date(item.get("date")), reverse=True)
    recent_policy_ids = {
        str(item.get("matched_policy_id") or "").strip()
        for item in rows
        if str(item.get("matched_policy_id") or "").strip()
    }
    recent_qiushi_quote_ids = {
        str(item.get("matched_qiushi_quote_id") or "").strip()
        for item in rows
        if str(item.get("matched_qiushi_quote_id") or "").strip()
    }
    recent_themes = [str(item.get("theme") or "").strip() for item in rows if str(item.get("theme") or "").strip()]
    recent_framework_ids = [
        str(item.get("matched_framework_id") or "").strip()
        for item in rows
        if str(item.get("matched_framework_id") or "").strip()
    ]
    theme_streak = ""
    if len(recent_themes) >= 2 and _compact(recent_themes[0]) == _compact(recent_themes[1]):
        theme_streak = recent_themes[0]
    return {
        "recent_count": len(rows),
        "recent_policy_ids": recent_policy_ids,
        "recent_qiushi_quote_ids": recent_qiushi_quote_ids,
        "recent_themes": recent_themes[:5],
        "theme_streak": theme_streak,
        "theme_streak_key": _compact(theme_streak),
        "last_framework_id": recent_framework_ids[0] if recent_framework_ids else "",
    }


def _apply_usage_penalties(scored: list[Candidate], *, kind: str, usage_context: dict[str, Any]) -> list[Candidate]:
    adjusted: list[Candidate] = []
    for row in scored:
        next_row = dict(row)
        reasons = dict(next_row.get("reasons") or {})
        usage_flags: list[str] = []
        usage_penalty = 0.0
        row_id = str(next_row.get("id") or "").strip()
        item = next_row.get("item") if isinstance(next_row.get("item"), dict) else {}

        if kind == "policy":
            if row_id and row_id in usage_context.get("recent_policy_ids", set()):
                usage_penalty += RECENT_POLICY_REPEAT_PENALTY
                usage_flags.append("recent_policy_id_repeat_14d")
            theme_key = _compact(item.get("theme_level_1") or item.get("theme") or "")
            if usage_context.get("theme_streak_key") and theme_key == usage_context["theme_streak_key"]:
                usage_penalty += THEME_STREAK_PENALTY
                usage_flags.append("theme_three_day_streak_risk")
        elif kind == "qiushi_quote":
            if row_id and row_id in usage_context.get("recent_qiushi_quote_ids", set()):
                usage_penalty += RECENT_QIUSHI_QUOTE_REPEAT_PENALTY
                usage_flags.append("recent_qiushi_quote_repeat_14d")
        elif kind == "framework":
            if row_id and row_id == usage_context.get("last_framework_id"):
                usage_penalty += CONSECUTIVE_FRAMEWORK_REPEAT_PENALTY
                usage_flags.append("consecutive_framework_repeat")

        next_row["raw_score"] = next_row.get("score", 0.0)
        next_row["usage_penalty"] = usage_penalty
        next_row["usage_flags"] = usage_flags
        next_row["score"] = float(next_row.get("score", 0.0)) + usage_penalty

        if usage_flags:
            reasons["usage_history_flags"] = usage_flags
            reasons["usage_penalty"] = usage_penalty
        next_row["reasons"] = reasons
        adjusted.append(next_row)
    return adjusted


def _annotate_repeat_selection(selected: Candidate | None, scored: list[Candidate], *, min_score: float) -> dict[str, Any]:
    if not selected:
        return {}
    flags = list(selected.get("usage_flags") or [])
    if not flags:
        return {}
    eligible_rows = [
        row
        for row in scored
        if row.get("score", 0) >= min_score and row.get("reasons", {}).get("_semantic_hits", 0) > 0
    ]
    non_repeat_rows = [row for row in eligible_rows if not row.get("usage_flags")]
    reason = "repeat_selected_due_to_stronger_match" if non_repeat_rows else "repeat_selected_no_non_repeat_candidate"
    selected_reasons = dict(selected.get("reasons") or {})
    selected_reasons["usage_repeat_allowed"] = reason
    selected["reasons"] = selected_reasons
    return {
        "selected_id": selected.get("id"),
        "flags": flags,
        "reason": reason,
        "best_non_repeat_id": non_repeat_rows[0].get("id") if non_repeat_rows else "",
        "best_non_repeat_score": round(float(non_repeat_rows[0].get("score", 0.0)), 2) if non_repeat_rows else 0.0,
    }


def match_policy_coordinate_candidates(
    article_title: str = "",
    article_summary: str = "",
    article_text: str = "",
    main_theme: str = "",
    sub_themes: Any = None,
    keywords: Any = None,
    exam_scenarios: Any = None,
    article: dict[str, Any] | None = None,
    recent_usage: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    query = normalize_article_input(
        article_title=article_title,
        article_summary=article_summary,
        article_text=article_text,
        main_theme=main_theme,
        sub_themes=sub_themes,
        keywords=keywords,
        exam_scenarios=exam_scenarios,
        article=article,
    )
    usage_context = _recent_usage_context(recent_usage)

    policy_core_scores = [
        _score_policy(item, query, source="policy_core")
        for item in load_policy_core()
        if not _is_disabled(item) and not _is_background(item)
    ]
    policy_core_scores = _apply_usage_penalties(policy_core_scores, kind="policy", usage_context=usage_context)
    policy_all_scores = [
        _score_policy(item, query, source="policy_all")
        for item in load_policy_all()
        if _eligible_policy_from_all(item)
    ]
    policy_all_scores = _apply_usage_penalties(policy_all_scores, kind="policy", usage_context=usage_context)
    best_policy_score = _best(policy_core_scores + policy_all_scores)

    quote_core_scores = [
        _score_qiushi_quote(item, query, source="qiushi_quotes_core")
        for item in load_qiushi_quotes_core()
        if not _is_disabled(item) and not _is_background(item)
    ]
    quote_core_scores = _apply_usage_penalties(quote_core_scores, kind="qiushi_quote", usage_context=usage_context)
    quote_candidate_scores = [
        _score_qiushi_quote(item, query, source="qiushi_quotes_candidates")
        for item in load_qiushi_quotes_candidates()
        if not _is_disabled(item)
    ]
    quote_candidate_scores = _apply_usage_penalties(quote_candidate_scores, kind="qiushi_quote", usage_context=usage_context)
    best_quote_score = _best(quote_core_scores + quote_candidate_scores)

    article_scores = [_score_article_index(item, query) for item in load_qiushi_article_index() if item.get("status", "active") != "disabled"]
    best_article_scores = _top(article_scores, limit=3)
    boosted_article_ids = {str(row.get("id")) for row in best_article_scores if row.get("id")}
    if best_quote_score and best_quote_score.get("article_id"):
        boosted_article_ids.add(str(best_quote_score["article_id"]))

    chunk_scores = [
        _score_chunk(item, query, boosted_article_ids)
        for item in load_qiushi_chunks()
        if not _is_disabled(item)
    ]
    framework_scores = [
        _score_framework(item, query, boosted_article_ids)
        for item in load_topic_frameworks()
        if not _is_disabled(item)
    ]
    framework_scores = _apply_usage_penalties(framework_scores, kind="framework", usage_context=usage_context)

    matched_chunks = [_public_result(row) for row in _top(chunk_scores, limit=3, min_score=25)]
    best_framework_score = _best(framework_scores, min_score=30)
    selected_repeat_notes = {
        "policy": _annotate_repeat_selection(best_policy_score, policy_core_scores + policy_all_scores, min_score=1),
        "qiushi_quote": _annotate_repeat_selection(best_quote_score, quote_core_scores + quote_candidate_scores, min_score=1),
        "framework": _annotate_repeat_selection(best_framework_score, framework_scores, min_score=30),
    }
    return {
        "matched_policy_coordinate_candidates": {
            "best_policy": _public_result(best_policy_score),
            "best_qiushi_quote": _public_result(best_quote_score),
            "matched_chunks": [row for row in matched_chunks if row],
            "best_framework": _public_result(best_framework_score),
            "debug_scores": {
                "query": {key: value for key, value in query.items() if key != "combined_text"},
                "usage_history": {
                    "recent_days": 14,
                    "recent_count": usage_context.get("recent_count", 0),
                    "theme_streak": usage_context.get("theme_streak", ""),
                    "last_framework_id": usage_context.get("last_framework_id", ""),
                    "selected_repeat_notes": {key: value for key, value in selected_repeat_notes.items() if value},
                },
                "best_article_index": [_public_result(row) for row in best_article_scores],
                "policy_core_top": [_public_result(row) for row in _top(policy_core_scores, limit=5)],
                "policy_all_top": [_public_result(row) for row in _top(policy_all_scores, limit=5)],
                "qiushi_quotes_core_top": [_public_result(row) for row in _top(quote_core_scores, limit=5)],
                "qiushi_quotes_candidates_top": [_public_result(row) for row in _top(quote_candidate_scores, limit=5)],
                "chunk_top": [_public_result(row) for row in _top(chunk_scores, limit=5)],
                "framework_top": [_public_result(row) for row in _top(framework_scores, limit=5)],
            },
        }
    }
