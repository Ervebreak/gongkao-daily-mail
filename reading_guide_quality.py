from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any


ALLOWED_ANCHOR_MODULES = {
    "今日精读",
    "政策坐标",
    "今日一题",
    "今日可带走",
    "今日速读",
}

GENERIC_READING_GUIDE_PHRASES = (
    "提升能力",
    "积累热点素材",
    "拓宽视野",
    "了解热点",
    "认真阅读",
    "帮助学习",
    "增强理解",
    "提高申论水平",
)

MODULE_CATALOG_PHRASES = (
    "本邮件包括",
    "依次阅读",
    "各模块",
    "今日精读今日一题今日可带走",
)

HYPE_READING_GUIDE_PHRASES = (
    "必考",
    "押题",
    "不看后悔",
    "一定会考",
    "上岸",
)


def _issue(code: str, severity: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
    }


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(ch for ch in text if not ch.isspace())


def _is_highly_repeated(core_value: str, subject: str) -> bool:
    if not core_value or not subject:
        return False
    if core_value == subject:
        return True
    if core_value in subject or subject in core_value:
        return True
    return SequenceMatcher(None, core_value, subject).ratio() >= 0.8


def evaluate_reading_guide_quality(brief: dict) -> dict[str, Any]:
    guide = (brief or {}).get("reading_guide")
    subject = str((brief or {}).get("email_subject") or "").strip()
    issues: list[dict[str, str]] = []

    if not isinstance(guide, dict):
        issues.append(
            _issue(
                "missing_reading_guide",
                "medium",
                "reading_guide 缺失或结构不正确，无法提供稳定的首屏价值导读。",
            )
        )
        guide = {}

    core_value = str(guide.get("core_value") or "").strip()
    focus_path = str(guide.get("focus_path") or "").strip()
    learning_outcome = str(guide.get("learning_outcome") or "").strip()
    anchor_module = str(guide.get("anchor_module") or "").strip()

    if not core_value or not focus_path or not learning_outcome:
        issues.append(
            _issue(
                "empty_reading_guide_field",
                "medium",
                "reading_guide 的核心价值、重点路径或带走结果存在空项。",
            )
        )

    if anchor_module and anchor_module not in ALLOWED_ANCHOR_MODULES:
        issues.append(
            _issue(
                "invalid_anchor_module",
                "low",
                "reading_guide.anchor_module 不在允许的模块范围内。",
            )
        )

    combined_text = " ".join(part for part in (core_value, focus_path, learning_outcome) if part)
    compact_text = _normalize_text(combined_text)

    if any(phrase in combined_text for phrase in GENERIC_READING_GUIDE_PHRASES):
        issues.append(
            _issue(
                "generic_reading_guide",
                "medium",
                "reading_guide 表达偏空泛，没有说明今天具体该学什么、怎么学、带走什么。",
            )
        )

    if any(phrase in combined_text for phrase in MODULE_CATALOG_PHRASES) or (
        "今日精读" in compact_text and "今日一题" in compact_text and "今日可带走" in compact_text
    ):
        issues.append(
            _issue(
                "module_catalog_intro",
                "medium",
                "reading_guide 更像栏目介绍，而不是当天内容的动态价值导读。",
            )
        )

    if any(phrase in combined_text for phrase in HYPE_READING_GUIDE_PHRASES):
        issues.append(
            _issue(
                "hype_reading_guide",
                "medium",
                "reading_guide 含有营销或押题式表述，语气不稳妥。",
            )
        )

    if len(core_value) > 45 or len(focus_path) > 55 or len(learning_outcome) > 55:
        issues.append(
            _issue(
                "reading_guide_too_long",
                "low",
                "reading_guide 字段偏长，首屏展示容易发散或被截断。",
            )
        )

    if _is_highly_repeated(core_value, subject):
        issues.append(
            _issue(
                "repeated_subject",
                "low",
                "reading_guide.core_value 与邮件标题重复度过高，首屏新增信息不足。",
            )
        )

    score = 100
    has_medium = False
    for issue in issues:
        severity = str(issue.get("severity") or "").lower()
        if severity == "medium":
            score -= 15
            has_medium = True
        elif severity == "low":
            score -= 6
    score = max(0, min(100, score))

    if score >= 85 and not has_medium:
        status = "ok"
    elif score >= 65:
        status = "review"
    else:
        status = "fail"

    return {
        "ok": status == "ok",
        "status": status,
        "score": score,
        "issues": issues,
    }
