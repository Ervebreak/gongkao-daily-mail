from __future__ import annotations

import json
import re
from typing import Any

from config import settings
from llm_client import chat_completion


RERANKER_SYSTEM_PROMPT = """
你是公考晨读邮件的政策坐标精排器。
你的任务不是改写文章，也不是扩写材料，而是从候选权威表达或政策语句中选出最贴合文章核心矛盾的一句。

判断标准：
1. 必须真正解释文章的核心问题、治理偏差或价值导向。
2. 如果只是泛泛对应“基层治理、服务群众、完善机制、压实责任”等空泛表述，不能展示。
3. article_connection 必须具体解释文章核心矛盾，不要空话。
4. exam_transfer 需要简洁，能说明申论/面试迁移方向。
5. 如果没有合格候选，必须返回 hidden。

只返回 JSON 对象，不要输出额外说明。
""".strip()

GENERIC_CONNECTION_TERMS = {
    "基层治理",
    "服务群众",
    "完善机制",
    "压实责任",
    "协同联动",
    "长效机制",
    "强化落实",
    "公共服务",
    "治理效能",
    "系统治理",
    "抓好落实",
    "机制建设",
    "服务大局",
    "grassroots governance",
    "governance",
    "serve the people",
    "service",
    "services",
    "improve mechanisms",
    "mechanism",
    "mechanisms",
    "long-term mechanism",
    "accountability",
}

GENERIC_REASON_TERMS = {
    "贴合",
    "相关",
    "治理",
    "群众",
    "机制",
    "落实",
    "导向",
}


ENGLISH_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "that",
    "this",
    "into",
    "from",
    "over",
    "under",
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    if isinstance(value, dict):
        return " ".join(part for part in (_text(item) for item in value.values()) if part).strip()
    if isinstance(value, (list, tuple, set)):
        return " ".join(part for part in (_text(item) for item in value) if part).strip()
    return " ".join(str(value).split()).strip()


def _clip(value: Any, limit: int) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，。；,; ") + "..."


def _profile_summary(policy_profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = policy_profile if isinstance(policy_profile, dict) else {}
    return {
        "core_problem": _clip(profile.get("core_problem"), 160),
        "governance_logic": _clip(profile.get("governance_logic"), 160),
        "value_orientation": _clip(profile.get("value_orientation"), 120),
        "negative_behaviors": [_clip(item, 24) for item in list(profile.get("negative_behaviors") or [])[:5] if _text(item)],
        "positive_behaviors": [_clip(item, 24) for item in list(profile.get("positive_behaviors") or [])[:5] if _text(item)],
        "fine_anchors": [_clip(item, 24) for item in list(profile.get("fine_anchors") or [])[:8] if _text(item)],
        "retrieval_queries": [_clip(item, 40) for item in list(profile.get("retrieval_queries") or [])[:6] if _text(item)],
    }


def _extract_terms(*values: Any, limit: int = 24) -> list[str]:
    text = _text(values)
    candidates = re.findall(r"[\u4e00-\u9fff]{2,12}|[A-Za-z][A-Za-z\-]{2,24}", text)
    terms: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        compact = item.lower()
        if compact in ENGLISH_STOPWORDS:
            continue
        if compact in seen or compact in {term.lower() for term in GENERIC_CONNECTION_TERMS}:
            continue
        seen.add(compact)
        terms.append(item)
        if len(terms) >= limit:
            break
    return terms


def _profile_terms(policy_profile: dict[str, Any] | None) -> list[str]:
    profile = policy_profile if isinstance(policy_profile, dict) else {}
    return _extract_terms(
        profile.get("core_problem"),
        profile.get("governance_logic"),
        profile.get("value_orientation"),
        profile.get("negative_behaviors"),
        profile.get("positive_behaviors"),
        profile.get("fine_anchors"),
        limit=32,
    )


def _connection_hidden_reason(article_connection: str, policy_profile: dict[str, Any] | None) -> str:
    text = _text(article_connection)
    if not text:
        return "article_connection_missing"
    if len(text) < 18:
        return "article_connection_too_short"
    compact_text = text.lower()
    specific_hits = [term for term in _profile_terms(policy_profile) if term and term.lower() in compact_text]
    if specific_hits:
        return ""
    generic_hits = [term for term in GENERIC_CONNECTION_TERMS if term.lower() in compact_text]
    if generic_hits:
        return f"article_connection_too_generic:{'|'.join(generic_hits[:3])}"
    if len(_extract_terms(text, limit=6)) <= 2:
        return "article_connection_not_specific_enough"
    return ""


def _reason_hidden(reason: str) -> str:
    text = _text(reason)
    if not text:
        return "rerank_hidden"
    compact = text.lower()
    if any(term.lower() in compact for term in GENERIC_REASON_TERMS):
        return text
    return text


def _normalize_candidate(item: dict[str, Any], *, family: str) -> dict[str, Any]:
    candidate_id = _text(item.get("quote_id") or item.get("policy_id"))
    quote = _text(
        item.get("quote_text")
        or item.get("policy_quote")
        or item.get("short_quote")
        or item.get("quote_preview")
    )
    source = _text(item.get("source_title") or item.get("title"))
    source_type = _text(item.get("source_type") or item.get("_match_source") or family)
    try:
        rule_score = float(item.get("_match_score") or item.get("match_score") or 0)
    except (TypeError, ValueError):
        rule_score = 0.0
    return {
        "id": candidate_id,
        "quote": _clip(quote, 160),
        "source": _clip(source, 80),
        "source_type": source_type,
        "rule_score": round(rule_score, 2),
    }


def normalize_rerank_candidates(items: list[dict[str, Any]] | None, *, family: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in list(items or [])[:10]:
        if not isinstance(item, dict):
            continue
        row = _normalize_candidate(item, family=family)
        candidate_id = row["id"]
        if not candidate_id or candidate_id in seen or not row["quote"]:
            continue
        seen.add(candidate_id)
        rows.append(row)
    return rows[:10]


def build_rerank_input_summary(
    *,
    article_title: str,
    policy_profile: dict[str, Any] | None,
    article_summary: str,
    authoritative_candidates: list[dict[str, Any]] | None,
    policy_statement_candidates: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    return {
        "article_title": _clip(article_title, 80),
        "article_summary": _clip(article_summary, 220),
        "article_summary_length": len(_text(article_summary)),
        "policy_profile": _profile_summary(policy_profile),
        "authoritative_candidate_count": len(list(authoritative_candidates or [])[:10]),
        "policy_statement_candidate_count": len(list(policy_statement_candidates or [])[:10]),
        "authoritative_candidate_ids": [_text(item.get("id")) for item in list(authoritative_candidates or [])[:10]],
        "policy_statement_candidate_ids": [_text(item.get("id")) for item in list(policy_statement_candidates or [])[:10]],
    }


def _rerank_models() -> list[str]:
    models: list[str] = []
    preferred = [
        settings.test_content_quality_llm_model if settings.run_mode == "test" else settings.content_quality_llm_model,
        settings.test_content_quality_llm_fallback_model if settings.run_mode == "test" else settings.content_quality_llm_fallback_model,
        settings.test_writing_llm_model if settings.run_mode == "test" else settings.writing_llm_model,
        settings.test_llm_model if settings.run_mode == "test" else settings.llm_model,
        settings.llm_fallback_model,
    ]
    for model in preferred:
        normalized = _text(model)
        if normalized and normalized not in models:
            models.append(normalized)
    return models


def _rerank_prompt(
    *,
    article_title: str,
    policy_profile: dict[str, Any] | None,
    article_summary: str,
    candidate_quotes: list[dict[str, Any]],
    candidate_family: str,
) -> str:
    payload = {
        "article_title": _clip(article_title, 80),
        "policy_profile": _profile_summary(policy_profile),
        "article_summary": _clip(article_summary, 600),
        "candidate_family": candidate_family,
        "candidate_quotes": candidate_quotes[:10],
        "output_schema": {
            "selected_id": "",
            "fit_score": 0,
            "reason": "",
            "article_connection": "",
            "exam_transfer": "",
            "display_level": "A/B/hidden",
        },
        "judgement_rules": [
            "先判断是否真正解释文章核心矛盾，再考虑措辞权威性。",
            "如果只泛泛对应基层治理、服务群众、完善机制等空泛主题，必须 hidden。",
            "article_connection 必须具体指出文章的问题、偏差或治理转向。",
            "不允许杜撰候选列表之外的 id。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _hidden_result(*, reason: str, fit_score: float = 0.0, selected_id: str = "") -> dict[str, Any]:
    return {
        "selected_id": _text(selected_id),
        "fit_score": round(float(fit_score or 0.0), 2),
        "reason": _clip(reason, 180),
        "article_connection": "",
        "exam_transfer": "",
        "display_level": "hidden",
        "hidden_reason": _clip(reason, 180),
    }


def _normalize_rerank_response(
    response: dict[str, Any],
    *,
    candidates: list[dict[str, Any]],
    policy_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    valid_ids = {item["id"] for item in candidates}
    selected_id = _text(response.get("selected_id"))
    try:
        fit_score = float(response.get("fit_score") or 0)
    except (TypeError, ValueError):
        fit_score = 0.0
    display_level = _text(response.get("display_level")).upper() or "HIDDEN"
    if display_level not in {"A", "B", "HIDDEN"}:
        display_level = "HIDDEN"
    reason = _clip(response.get("reason"), 180)
    article_connection = _clip(response.get("article_connection"), 180)
    exam_transfer = _clip(response.get("exam_transfer"), 160)

    if not selected_id or selected_id not in valid_ids:
        return _hidden_result(reason=reason or "selected_id_not_in_candidates", fit_score=fit_score, selected_id=selected_id)
    if display_level == "HIDDEN":
        return _hidden_result(reason=reason or "reranker_marked_hidden", fit_score=fit_score, selected_id=selected_id)

    hidden_reason = _connection_hidden_reason(article_connection, policy_profile)
    if hidden_reason:
        return _hidden_result(reason=hidden_reason, fit_score=fit_score, selected_id=selected_id)

    return {
        "selected_id": selected_id,
        "fit_score": round(fit_score, 2),
        "reason": reason,
        "article_connection": article_connection,
        "exam_transfer": exam_transfer,
        "display_level": display_level.lower(),
        "hidden_reason": "",
    }


def rerank_policy_coordinate_candidates(
    *,
    article_title: str,
    policy_profile: dict[str, Any] | None,
    article_summary: str,
    candidate_quotes: list[dict[str, Any]] | None,
    candidate_family: str,
) -> dict[str, Any]:
    candidates = normalize_rerank_candidates(candidate_quotes, family=candidate_family)
    if not candidates:
        return _hidden_result(reason=f"{candidate_family}_no_candidates")

    prompt = _rerank_prompt(
        article_title=article_title,
        policy_profile=policy_profile,
        article_summary=article_summary,
        candidate_quotes=candidates,
        candidate_family=candidate_family,
    )
    models = _rerank_models()
    last_error = ""
    for model in models:
        try:
            response = chat_completion(
                model,
                prompt,
                timeout=getattr(settings, "content_quality_timeout", None) or settings.llm_timeout,
                trace={"stage": "policy_coordinate_rerank", "candidate_family": candidate_family},
                system_prompt=RERANKER_SYSTEM_PROMPT,
            )
            normalized = _normalize_rerank_response(response, candidates=candidates, policy_profile=policy_profile)
            normalized["model"] = model
            return normalized
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
    return _hidden_result(reason=f"{candidate_family}_rerank_error:{last_error or 'unknown'}")
