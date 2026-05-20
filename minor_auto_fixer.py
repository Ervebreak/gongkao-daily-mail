from __future__ import annotations

import copy
from typing import Any


DEFAULT_FIXABLE_CODES = {"repeated_word", "authority_overclaim", "legal_overstatement"}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _replace_in_value(value: Any, bad: str, replacement: str) -> tuple[Any, bool]:
    if not bad or not replacement:
        return value, False
    if isinstance(value, str):
        updated = value.replace(bad, replacement)
        return updated, updated != value
    if isinstance(value, list):
        changed = False
        result = []
        for item in value:
            updated, item_changed = _replace_in_value(item, bad, replacement)
            changed = changed or item_changed
            result.append(updated)
        return result, changed
    if isinstance(value, dict):
        changed = False
        result = {}
        for key, item in value.items():
            updated, item_changed = _replace_in_value(item, bad, replacement)
            changed = changed or item_changed
            result[key] = updated
        return result, changed
    return value, False


def _resolve_field(root: dict[str, Any], field: str) -> tuple[Any, str] | None:
    path = str(field or "")
    if path.startswith("brief."):
        path = path[len("brief.") :]
    if not path:
        return None
    parts = path.split(".")
    current: Any = root
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    if not isinstance(current, dict):
        return None
    return current, parts[-1]


def _module_from_field(field: str) -> str:
    if "daily_question" in field:
        return "daily_question"
    if "today_takeaway" in field:
        return "today_takeaway"
    if "featured_article" in field:
        return "featured_article"
    if "quick_reads" in field:
        return "quick_reads"
    return "brief"


def apply_minor_auto_fixes(brief: dict[str, Any], quality_results: list[dict[str, Any]]) -> dict[str, Any]:
    updated = copy.deepcopy(brief)
    fixes: list[dict[str, Any]] = []
    changed_modules: list[str] = []

    for quality in quality_results:
        if not isinstance(quality, dict):
            continue
        for issue in quality.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or issue.get("issue_code") or "")
            if not issue.get("auto_fixable") and code not in DEFAULT_FIXABLE_CODES:
                continue
            field = str(issue.get("field") or "")
            bad = str(issue.get("bad_text") or "")
            replacement = str(issue.get("suggestion") or "")
            if not (field and bad and replacement):
                continue
            resolved = _resolve_field(updated, field)
            if not resolved:
                continue
            parent, key = resolved
            before = parent.get(key)
            after, changed = _replace_in_value(before, bad, replacement)
            if not changed:
                continue
            parent[key] = after
            module = _module_from_field(field)
            if module not in changed_modules:
                changed_modules.append(module)
            fixes.append({
                "code": code,
                "level": issue.get("level") or "P1",
                "field": field,
                "module": module,
                "bad_text": bad,
                "replacement": replacement,
                "message": issue.get("message") or code,
            })

    return {
        "brief": updated,
        "changed": bool(fixes),
        "fixes": fixes,
        "changed_modules": changed_modules,
    }


def merge_minor_fixes_into_rewrite(
    rewrite_result: dict[str, Any] | None,
    minor_fix_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not minor_fix_result or not minor_fix_result.get("changed"):
        return rewrite_result
    merged: dict[str, Any] = {
        "rewritten_modules": [],
        "details": {},
        "rounds": [],
    }
    if isinstance(rewrite_result, dict):
        merged.update({key: value for key, value in rewrite_result.items() if key not in {"brief", "rewritten_modules", "details", "rounds"}})
        merged["rewritten_modules"] = _as_list(rewrite_result.get("rewritten_modules"))
        merged["details"] = dict(rewrite_result.get("details") or {})
        merged["rounds"] = _as_list(rewrite_result.get("rounds"))
    for module in minor_fix_result.get("changed_modules") or []:
        label = f"minor_fix:{module}"
        if label not in merged["rewritten_modules"]:
            merged["rewritten_modules"].append(label)
    merged["details"]["minor_auto_fixes"] = minor_fix_result.get("fixes") or []
    merged["rounds"].append({
        "round": "minor_auto_fix",
        "changed_modules": minor_fix_result.get("changed_modules") or [],
        "fixes": minor_fix_result.get("fixes") or [],
    })
    return merged
