from __future__ import annotations

from collections import Counter
from typing import Any


LEVEL_BY_SEVERITY = {
    "high": "P0",
    "medium": "P1",
    "low": "P2",
}


def normalize_issue(
    *,
    code: str,
    message: str,
    severity: str = "medium",
    module: str = "",
    field: str = "",
    bad_text: str = "",
    suggestion: str = "",
    auto_fixable: bool = False,
    level: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    severity = str(severity or "medium").strip().lower()
    if severity not in {"high", "medium", "low"}:
        severity = "medium"
    payload: dict[str, Any] = {
        "level": level or LEVEL_BY_SEVERITY.get(severity, "P1"),
        "severity": severity,
        "code": str(code or "quality_issue"),
        "module": str(module or ""),
        "field": str(field or ""),
        "message": str(message or code or "quality issue"),
        "bad_text": str(bad_text or ""),
        "suggestion": str(suggestion or ""),
        "auto_fixable": bool(auto_fixable),
    }
    if extra:
        payload.update(extra)
    return payload


def issue_counts(quality_payload: dict[str, Any]) -> dict[str, int]:
    final = quality_payload.get("final") if isinstance(quality_payload.get("final"), dict) else {}
    counts: Counter[str] = Counter()
    for result in final.values():
        if not isinstance(result, dict):
            continue
        for issue in result.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            level = str(issue.get("level") or LEVEL_BY_SEVERITY.get(str(issue.get("severity") or "").lower(), "")).upper()
            if level in {"P0", "P1", "P2"}:
                counts[level] += 1
    return {"P0": counts["P0"], "P1": counts["P1"], "P2": counts["P2"]}


def severity_counts(quality_payload: dict[str, Any]) -> dict[str, int]:
    final = quality_payload.get("final") if isinstance(quality_payload.get("final"), dict) else {}
    counts: Counter[str] = Counter()
    for result in final.values():
        if not isinstance(result, dict):
            continue
        for issue in result.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            severity = str(issue.get("severity") or "").strip().lower()
            if severity in {"high", "medium", "low"}:
                counts[severity] += 1
    return {"high": counts["high"], "medium": counts["medium"], "low": counts["low"]}

