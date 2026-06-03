from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from knowledge_base_loader import load_policy_all, load_policy_core, load_qiushi_quotes_candidates, load_qiushi_quotes_core


GENERIC_PHRASES = [
    "体现了高质量发展",
    "具有重要意义",
    "具有重要作用",
    "意义重大",
    "有利于推动发展",
    "值得关注",
]

DANGLING_ENDINGS = (
    "通过",
    "由于",
    "为了",
    "围绕",
    "依靠",
    "立足",
    "推动",
    "促进",
    "实现",
    "提升",
    "强化",
    "完善",
    "构建",
    "形成",
    "建立",
    "转向",
    "转为",
    "赋能",
    "让",
    "把",
    "和",
    "与",
    "及",
    "并",
    "但",
    "在",
    "的",
)

ANSWER_ANGLE_KEYWORDS = [
    "平台",
    "机制",
    "诉求",
    "协同",
    "闭环",
    "服务",
    "监管",
    "法治",
    "数字",
    "人才",
    "就业",
    "民生",
    "治理",
    "落实",
    "反馈",
]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_text(item) for item in value if _text(item)).strip()
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values() if _text(item)).strip()
    return " ".join(str(value).split()).strip()


def _coordinate(brief: dict[str, Any]) -> dict[str, Any]:
    value = brief.get("policy_coordinate")
    return value if isinstance(value, dict) else {}


def _issue(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _looks_incomplete(text: str) -> bool:
    text = _text(text)
    if not text:
        return False
    if any(marker in text for marker in ("...", "……", "…")):
        return True
    if text.count("“") != text.count("”") or text.count("《") != text.count("》"):
        return True
    return text.endswith(DANGLING_ENDINGS)


def _specific_angle_count(text: str, angles: list[Any]) -> int:
    combined = f"{text} {' '.join(_text(item) for item in angles)}"
    hits = {keyword for keyword in ANSWER_ANGLE_KEYWORDS if keyword in combined}
    return len(hits)


def _policy_ids() -> set[str]:
    return {str(item.get("policy_id") or "") for item in load_policy_core() + load_policy_all() if item.get("policy_id")}


def _qiushi_quote_ids() -> set[str]:
    return {str(item.get("quote_id") or "") for item in load_qiushi_quotes_core() + load_qiushi_quotes_candidates() if item.get("quote_id")}


def _similarity(a: str, b: str) -> float:
    a = _text(a)
    b = _text(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a[:500], b[:500]).ratio()


def _large_repetition(brief: dict[str, Any], coordinate: dict[str, Any]) -> bool:
    coordinate_text = _text(
        [
            coordinate.get("policy_translation"),
            coordinate.get("article_connection"),
            coordinate.get("exam_transfer"),
        ]
    )
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    takeaway = brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    surfaces = [
        _text(featured),
        _text(takeaway),
        _text(question),
    ]
    return any(_similarity(coordinate_text, surface) >= 0.78 and len(coordinate_text) >= 80 for surface in surfaces)


def _display_type(coordinate: dict[str, Any]) -> str:
    value = _text(coordinate.get("display_evidence_type")).lower()
    return value or "none"


def _policy_coordinate_weak_match_issue(coordinate: dict[str, Any], disabled_reason: str) -> dict[str, str] | None:
    if "weak_match" in disabled_reason or "policy_score=" in disabled_reason:
        return _issue("medium", "policy_coordinate_weak_match", disabled_reason)
    try:
        policy_score = float(_text(coordinate.get("policy_match_score")) or 0)
    except (TypeError, ValueError):
        policy_score = 0.0
    source_type = _text(coordinate.get("source_type")).lower()
    if source_type == "policy_only" and policy_score < 65:
        return _issue(
            "medium",
            "policy_coordinate_weak_match",
            f"policy_only score too low for backend keep: policy_match_score={policy_score:.1f} < 65.",
        )
    if policy_score < 60:
        return _issue(
            "medium",
            "policy_coordinate_weak_match",
            f"policy_match_score too low for backend keep: {policy_score:.1f} < 60.",
        )
    return None


def evaluate_policy_coordinate_quality(brief: dict[str, Any], plain_text: str = "", html_body: str = "") -> dict[str, Any]:
    coordinate = _coordinate(brief)
    disabled_reason = _text(brief.get("_policy_coordinate_disabled_reason"))
    if not coordinate or not any(_text(value) for value in coordinate.values()):
        issues = []
        if disabled_reason:
            weak_match_issue = _policy_coordinate_weak_match_issue({}, disabled_reason)
            issues.append(weak_match_issue or _issue("low", "policy_coordinate_disabled", disabled_reason))
        weak_match = any(item["code"] == "policy_coordinate_weak_match" for item in issues)
        return {
            "ok": not weak_match,
            "status": "ok" if not issues else ("skipped" if weak_match else "review"),
            "score": 84 if weak_match else (100 if not issues else 92),
            "checks": {"present": False, "disabled_reason": disabled_reason},
            "issues": issues,
        }

    display_type = _display_type(coordinate)
    if display_type == "none":
        issues = []
        if disabled_reason:
            weak_match_issue = _policy_coordinate_weak_match_issue(coordinate, disabled_reason)
            issues.append(weak_match_issue or _issue("low", "policy_coordinate_disabled", disabled_reason))
        weak_match = any(item["code"] == "policy_coordinate_weak_match" for item in issues)
        return {
            "ok": not weak_match,
            "status": "ok" if not issues else ("skipped" if weak_match else "review"),
            "score": 84 if weak_match else (100 if not issues else 92),
            "checks": {"present": False, "display_evidence_type": "none", "disabled_reason": disabled_reason},
            "issues": issues,
        }

    issues: list[dict[str, str]] = []
    policy_quote = _text(coordinate.get("policy_quote"))
    policy_source = _text(coordinate.get("policy_source"))
    policy_translation = _text(coordinate.get("policy_translation"))
    article_connection = _text(coordinate.get("article_connection"))
    exam_transfer = _text(coordinate.get("exam_transfer"))
    authoritative_quote = _text(coordinate.get("authoritative_quote"))
    authoritative_source = _text(coordinate.get("authoritative_source"))
    matched_policy_id = _text(coordinate.get("matched_policy_id"))
    matched_qiushi_quote_id = _text(coordinate.get("matched_qiushi_quote_id"))
    show_policy = display_type in {"policy", "both"}
    show_qiushi = display_type in {"qiushi", "both"}
    weak_match_issue = _policy_coordinate_weak_match_issue(coordinate, disabled_reason)
    if weak_match_issue:
        issues.append(weak_match_issue)

    if show_policy and not policy_quote:
        issues.append(_issue("high", "policy_quote_missing", "展示政策原文时，policy_quote 不能为空。"))
    elif show_policy and len(policy_quote) > 90:
        issues.append(_issue("high", "policy_quote_too_long", "policy_quote 超过 90 字，不适合邮件展示。"))
    if show_policy and not policy_source:
        issues.append(_issue("high", "policy_source_missing", "展示政策原文时，policy_source 不能为空。"))
    if show_policy and not policy_translation:
        issues.append(_issue("medium", "policy_translation_missing", "policy_translation 为空，缺少政策转译。"))
    if not article_connection:
        issues.append(_issue("medium", "article_connection_missing", "article_connection 为空，无法连接当天文章。"))
    if not exam_transfer:
        issues.append(_issue("medium", "exam_transfer_missing", "exam_transfer 为空，缺少申论/面试迁移。"))
    elif _specific_angle_count(exam_transfer, coordinate.get("answer_angles") or []) < 2:
        issues.append(_issue("medium", "exam_transfer_too_generic", "exam_transfer 缺少至少 2 个具体答题角度。"))

    if show_qiushi and not authoritative_quote:
        issues.append(_issue("high", "authoritative_quote_missing", "展示权威论述时，authoritative_quote 不能为空。"))
    if authoritative_quote:
        if len(authoritative_quote) > 120:
            issues.append(_issue("medium", "authoritative_quote_too_long", "authoritative_quote 超过 120 字。"))
        if show_qiushi and not authoritative_source:
            issues.append(_issue("high", "authoritative_source_missing", "authoritative_quote 存在但 authoritative_source 为空。"))

    if show_policy and ("求是" in policy_source or "《求是》" in policy_source):
        issues.append(_issue("high", "qiushi_used_as_policy_source", "《求是》论述不得作为政策原文来源。"))
    if show_policy and "求是" in policy_quote and not policy_source:
        issues.append(_issue("high", "qiushi_rendered_as_policy_quote", "疑似把《求是》论述写成政策原文。"))
    for field_name, value in {
        "policy_quote": policy_quote if show_policy else "",
        "authoritative_quote": authoritative_quote if show_qiushi else "",
        "policy_translation": policy_translation,
        "article_connection": article_connection,
        "exam_transfer": exam_transfer,
    }.items():
        if _looks_incomplete(value):
            issues.append(_issue("high", f"{field_name}_incomplete", f"{field_name} 疑似半截句或标点不完整。"))

    if show_policy and show_qiushi and _similarity(policy_quote, authoritative_quote) >= 0.72:
        issues.append(_issue("high", "duplicate_evidence_quotes", "政策原文与权威论述高度重复，不应同时展示。"))

    combined = _text(coordinate)
    if "某领导人指出" in combined and not authoritative_source:
        issues.append(_issue("high", "vague_leader_source", "出现“某领导人指出”但没有具体来源。"))

    if show_policy and not matched_policy_id:
        issues.append(_issue("high", "matched_policy_id_missing", "matched_policy_id 为空，无法回查政策库。"))
    elif show_policy and matched_policy_id not in _policy_ids():
        issues.append(_issue("high", "matched_policy_id_not_found", f"matched_policy_id 不存在于政策库：{matched_policy_id}"))
    if matched_qiushi_quote_id and matched_qiushi_quote_id not in _qiushi_quote_ids():
        issues.append(_issue("high", "matched_qiushi_quote_id_not_found", f"matched_qiushi_quote_id 不存在于《求是》权威表达库：{matched_qiushi_quote_id}"))

    if show_policy and any(phrase in policy_translation for phrase in GENERIC_PHRASES) and len(policy_translation) < 45:
        issues.append(_issue("medium", "policy_translation_too_generic", "policy_translation 使用空泛表达但缺少具体转译。"))
    if any(phrase in article_connection for phrase in GENERIC_PHRASES) and len(article_connection) < 45:
        issues.append(_issue("medium", "article_connection_too_generic", "article_connection 表达空泛，缺少文章具体落点。"))

    if _large_repetition(brief, coordinate):
        issues.append(_issue("medium", "policy_coordinate_repeats_other_modules", "policy_coordinate 与今日精读/今日可带走/今日一题存在大段重复。"))

    rendered_policy_line = re.search(r"政策原文[:：].*?(求是|权威论述|authoritative)", plain_text + " " + html_body, flags=re.IGNORECASE)
    if rendered_policy_line:
        issues.append(_issue("high", "qiushi_rendered_in_policy_line", "渲染结果疑似把《求是》论述放进政策原文行。"))

    score = 100
    for item in issues:
        if item["severity"] == "high":
            score -= 28
        elif item["severity"] == "medium":
            score -= 14
        else:
            score -= 6
    score = max(0, min(100, score))
    high_count = sum(1 for item in issues if item["severity"] == "high")
    medium_count = sum(1 for item in issues if item["severity"] == "medium")
    ok = high_count == 0 and medium_count == 0
    return {
        "ok": ok,
        "status": "ok" if ok else ("fail" if high_count else ("skipped" if weak_match_issue else "review")),
        "score": score,
        "checks": {
            "present": True,
            "display_evidence_type": display_type,
            "policy_quote_length": len(policy_quote),
            "authoritative_quote_length": len(authoritative_quote),
            "specific_angle_count": _specific_angle_count(exam_transfer, coordinate.get("answer_angles") or []),
        },
        "issues": issues,
    }


AUTH_ISSUE_CODES = {
    "authoritative_quote_missing",
    "authoritative_quote_too_long",
    "authoritative_source_missing",
    "matched_qiushi_quote_id_not_found",
}

POLICY_CRITICAL_CODES = {
    "policy_quote_missing",
    "policy_quote_too_long",
    "policy_source_missing",
    "qiushi_used_as_policy_source",
    "qiushi_rendered_as_policy_quote",
    "qiushi_rendered_in_policy_line",
    "matched_policy_id_missing",
    "matched_policy_id_not_found",
    "authoritative_source_missing",
    "vague_leader_source",
    "policy_quote_incomplete",
    "authoritative_quote_incomplete",
}


def classify_policy_coordinate_issues(quality: dict[str, Any]) -> dict[str, bool]:
    codes = {str(issue.get("code") or "") for issue in quality.get("issues") or [] if isinstance(issue, dict)}
    return {
        "has_authoritative_issue": bool(codes & AUTH_ISSUE_CODES),
        "has_policy_critical_issue": bool(codes & POLICY_CRITICAL_CODES),
        "has_remaining_issue": bool(codes),
    }
