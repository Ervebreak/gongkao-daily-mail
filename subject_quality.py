from __future__ import annotations

from typing import Any

from subject_line import has_exam_value_marker, has_hype_word, is_generic_subject, strip_subject_prefix


def _issue(code: str, severity: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
    }


def evaluate_subject_quality(brief: dict) -> dict[str, Any]:
    subject = str((brief or {}).get("email_subject") or "").strip()
    stripped = strip_subject_prefix(subject)
    issues: list[dict[str, str]] = []

    if "【公考晨读】" in subject:
        issues.append(
            _issue(
                "duplicate_subject_prefix",
                "medium",
                "brief.email_subject 不应携带统一前缀，发送层会自动添加。",
            )
        )

    if has_hype_word(stripped):
        issues.append(
            _issue(
                "hype_subject_word",
                "medium",
                "标题存在夸张营销或押题感，建议改为“高频/常考方向/申论素材”等稳妥表达。",
            )
        )

    if is_generic_subject(stripped):
        issues.append(
            _issue(
                "generic_subject",
                "medium",
                "标题只表达主题，没有体现考试收益。",
            )
        )

    if stripped and not has_exam_value_marker(stripped):
        issues.append(
            _issue(
                "missing_exam_value_marker",
                "low",
                "标题缺少打开价值提示。",
            )
        )

    if len(stripped) > 26:
        issues.append(
            _issue(
                "subject_too_long",
                "low",
                "标题偏长，收件箱展示可能被截断。",
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
