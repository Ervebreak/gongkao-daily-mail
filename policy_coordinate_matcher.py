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
    return {
        "article_title": title,
        "article_summary": summary,
        "article_text": text,
        "main_theme": theme,
        "sub_themes": subs,
        "keywords": keys,
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


def match_policy_coordinate_candidates(
    article_title: str = "",
    article_summary: str = "",
    article_text: str = "",
    main_theme: str = "",
    sub_themes: Any = None,
    keywords: Any = None,
    exam_scenarios: Any = None,
    article: dict[str, Any] | None = None,
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

    policy_core_scores = [
        _score_policy(item, query, source="policy_core")
        for item in load_policy_core()
        if not _is_disabled(item) and not _is_background(item)
    ]
    best_policy_score = _best(policy_core_scores)
    if not best_policy_score:
        policy_all_scores = [
            _score_policy(item, query, source="policy_all")
            for item in load_policy_all()
            if _eligible_policy_from_all(item)
        ]
        best_policy_score = _best(policy_all_scores)
    else:
        policy_all_scores = []

    quote_core_scores = [
        _score_qiushi_quote(item, query, source="qiushi_quotes_core")
        for item in load_qiushi_quotes_core()
        if not _is_disabled(item) and not _is_background(item)
    ]
    best_quote_score = _best(quote_core_scores)
    quote_candidate_scores: list[Candidate] = []
    if not best_quote_score:
        quote_candidate_scores = [
            _score_qiushi_quote(item, query, source="qiushi_quotes_candidates")
            for item in load_qiushi_quotes_candidates()
            if not _is_disabled(item)
        ]
        best_quote_score = _best(quote_candidate_scores)

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

    matched_chunks = [_public_result(row) for row in _top(chunk_scores, limit=3, min_score=25)]
    return {
        "matched_policy_coordinate_candidates": {
            "best_policy": _public_result(best_policy_score),
            "best_qiushi_quote": _public_result(best_quote_score),
            "matched_chunks": [row for row in matched_chunks if row],
            "best_framework": _public_result(_best(framework_scores, min_score=30)),
            "debug_scores": {
                "query": {key: value for key, value in query.items() if key != "combined_text"},
                "best_article_index": [_public_result(row) for row in best_article_scores],
                "policy_core_top": [_public_result(row) for row in _top(policy_core_scores, limit=5)],
                "policy_all_top": [_public_result(row) for row in _top(policy_all_scores, limit=5)],
                "qiushi_quotes_core_top": [_public_result(row) for row in _top(quote_core_scores, limit=5)],
                "qiushi_quotes_candidates_top": [_public_result(row) for row in _top(quote_candidate_scores, limit=5)],
                "chunk_top": [_public_result(row) for row in _top(chunk_scores, limit=5)],
                "framework_top": [_public_result(row) for row in _top(framework_scores, limit=3)],
            },
        }
    }
