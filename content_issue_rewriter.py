from __future__ import annotations

import copy
import json
from typing import Any

from brief_schema import ensure_brief_schema
from config import settings
from llm_client import chat_completion


ALLOWED_FIELD_PREFIXES = {
    "brief.daily_question.question",
    "brief.daily_question.exam_focus",
    "brief.daily_question.breaking_hint",
    "brief.daily_question.answer_framework",
    "brief.daily_question.answer_frame",
    "brief.daily_question.candidate_answer",
    "brief.daily_question.thirty_second_answer",
    "brief.daily_question.output_prompt",
    "brief.daily_question.output_sentence_template",
    "brief.featured_article.exam_use",
    "brief.featured_article.usable_for_exam",
    "brief.featured_article.rewritable_expression",
    "brief.featured_article.article_framework_map.main_thread",
    "brief.featured_article.article_framework_map.steps",
    "brief.today_takeaway.common_knowledge_points",
    "brief.today_takeaway.golden_sentences",
    "brief.today_takeaway.framework",
}


def _normalize_field(field: Any) -> str:
    value = str(field or "").strip()
    if value and not value.startswith("brief."):
        value = f"brief.{value}"
    return value


def _is_allowed_field(field: str) -> bool:
    return field in ALLOWED_FIELD_PREFIXES


def _module_from_field(field: str) -> str:
    if "daily_question" in field:
        return "daily_question"
    if "today_takeaway" in field:
        return "today_takeaway"
    if "featured_article" in field:
        return "featured_article"
    return "brief"


def _resolve_field(root: dict[str, Any], field: str) -> tuple[dict[str, Any], str] | None:
    path = field[len("brief.") :] if field.startswith("brief.") else field
    parts = [part for part in path.split(".") if part]
    if not parts:
        return None
    current: Any = root
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    if not isinstance(current, dict):
        return None
    return current, parts[-1]


def _target_key(target: dict[str, Any]) -> tuple[str, str]:
    return (_normalize_field(target.get("field")), str(target.get("issue_code") or target.get("code") or ""))


def normalize_rewrite_targets(content_quality: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in content_quality.get("rewrite_targets") or []:
        if not isinstance(raw, dict):
            continue
        field = _normalize_field(raw.get("field"))
        if not _is_allowed_field(field):
            continue
        issue_code = str(raw.get("issue_code") or raw.get("code") or "").strip() or "content_quality_review"
        target = {
            "field": field,
            "module": str(raw.get("module") or _module_from_field(field)),
            "issue_code": issue_code,
            "reason": str(raw.get("reason") or raw.get("message") or issue_code).strip(),
            "action": str(raw.get("action") or raw.get("suggestion") or "Rewrite this field locally.").strip(),
            "severity": str(raw.get("severity") or "medium").strip().lower(),
            "auto_fixable": bool(raw.get("auto_fixable", True)),
        }
        if raw.get("bad_text"):
            target["bad_text"] = str(raw.get("bad_text"))
        if raw.get("suggestion"):
            target["suggestion"] = str(raw.get("suggestion"))
        key = _target_key(target)
        if key in seen:
            continue
        seen.add(key)
        targets.append(target)
        if len(targets) >= limit:
            break
    return targets


def _replace_text(value: Any, bad_text: str, suggestion: str) -> tuple[Any, bool]:
    if not bad_text or not suggestion:
        return value, False
    if isinstance(value, str):
        updated = value.replace(bad_text, suggestion)
        return updated, updated != value
    if isinstance(value, list):
        changed = False
        result = []
        for item in value:
            updated, item_changed = _replace_text(item, bad_text, suggestion)
            changed = changed or item_changed
            result.append(updated)
        return result, changed
    if isinstance(value, dict):
        changed = False
        result = {}
        for key, item in value.items():
            updated, item_changed = _replace_text(item, bad_text, suggestion)
            changed = changed or item_changed
            result[key] = updated
        return result, changed
    return value, False


def _model_candidates(test_mode: bool) -> list[str]:
    if test_mode:
        candidates = [
            settings.test_writing_llm_model,
            settings.test_llm_model,
            settings.writing_llm_model,
            settings.writing_llm_fallback_model,
            settings.llm_model,
            settings.llm_fallback_model,
        ]
    else:
        candidates = [
            settings.writing_llm_model,
            settings.writing_llm_fallback_model,
            settings.llm_model,
            settings.llm_fallback_model,
        ]
    result: list[str] = []
    seen: set[str] = set()
    for model in candidates:
        model = str(model or "").strip()
        if model and model not in seen:
            seen.add(model)
            result.append(model)
    return result


def _mock_rewrite_value(value: Any, target: dict[str, Any]) -> Any:
    code = str(target.get("issue_code") or "")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return value
        replacements = {
            "必须": "应当",
            "严禁": "避免",
            "一律": "一般应",
            "全面强化": "进一步完善",
            "坚决落实": "稳妥推进",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        if code == "weak_student_voice":
            text = text.replace("需聚焦", "可以从").replace("重点抓好", "重点做好")
        if code == "near_duplicate_viewpoint":
            text = text.replace("关键是", "考场上可以写成")
        return text
    if isinstance(value, list):
        return [_mock_rewrite_value(item, target) for item in value]
    if isinstance(value, dict):
        return {key: _mock_rewrite_value(item, target) for key, item in value.items()}
    return value


def _build_rewrite_prompt(brief: dict[str, Any], field: str, current_value: Any, target: dict[str, Any]) -> str:
    payload = {
        "field": field,
        "current_value": current_value,
        "target": target,
        "context": {
            "today_theme": brief.get("today_theme"),
            "today_focus": brief.get("today_focus"),
            "featured_article": {
                "title": (brief.get("featured_article") or {}).get("title") if isinstance(brief.get("featured_article"), dict) else "",
                "source": (brief.get("featured_article") or {}).get("source") if isinstance(brief.get("featured_article"), dict) else "",
                "one_sentence": (brief.get("featured_article") or {}).get("one_sentence") if isinstance(brief.get("featured_article"), dict) else "",
                "core_viewpoint": (brief.get("featured_article") or {}).get("core_viewpoint") if isinstance(brief.get("featured_article"), dict) else "",
            },
            "daily_question": brief.get("daily_question"),
            "today_takeaway": brief.get("today_takeaway"),
        },
    }
    return f"""
你是公考晨读邮件的局部改稿员。只允许改 payload.field 指定的字段，不允许改整封邮件。

要求：
- 保留事实、题意、来源含义和原有结构。
- 不要改标题、来源、发布时间、URL。
- 输出必须是合法 JSON，且只包含 rewritten_value。
- rewritten_value 的类型必须和 current_value 一致；字符串仍是字符串，数组仍是数组，对象仍是对象。
- 表达要更自然、更像考生能复述的考场语言，不要堆口号。

payload:
{json.dumps(payload, ensure_ascii=False, default=str)}
""".strip()


def _call_rewriter(value: Any, brief: dict[str, Any], field: str, target: dict[str, Any], test_mode: bool) -> tuple[Any, str]:
    if any(model.lower() == "mock" for model in _model_candidates(test_mode)):
        return _mock_rewrite_value(value, target), "mock"
    prompt = _build_rewrite_prompt(brief, field, value, target)
    errors: list[str] = []
    for model in _model_candidates(test_mode):
        try:
            response = chat_completion(model, prompt, timeout=settings.llm_writing_timeout)
            if "rewritten_value" in response:
                return response["rewritten_value"], model
            if "value" in response:
                return response["value"], model
        except Exception as exc:
            errors.append(f"{model}: {exc}")
    raise RuntimeError("content issue rewrite failed: " + " | ".join(errors))


def rewrite_content_issues(
    brief: dict[str, Any],
    content_quality: dict[str, Any],
    *,
    test_mode: bool = False,
    today: str | None = None,
    max_targets: int = 5,
) -> dict[str, Any]:
    targets = normalize_rewrite_targets(content_quality, limit=max_targets)
    updated = copy.deepcopy(brief)
    rewrites: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    changed_modules: list[str] = []

    for target in targets:
        field = _normalize_field(target.get("field"))
        resolved = _resolve_field(updated, field)
        if not resolved:
            skipped.append({"field": field, "reason": "field_not_found", "target": target})
            continue
        parent, key = resolved
        before = parent.get(key)
        after, direct_changed = _replace_text(before, str(target.get("bad_text") or ""), str(target.get("suggestion") or ""))
        model = "direct_replace" if direct_changed else ""
        if not direct_changed:
            if not target.get("auto_fixable", True):
                skipped.append({"field": field, "reason": "not_auto_fixable", "target": target})
                continue
            try:
                after, model = _call_rewriter(before, updated, field, target, test_mode)
            except Exception as exc:
                skipped.append({"field": field, "reason": "rewrite_failed", "error": str(exc), "target": target})
                continue
        if type(after) is not type(before):
            skipped.append({"field": field, "reason": "type_changed", "target": target})
            continue
        if after == before:
            skipped.append({"field": field, "reason": "unchanged", "target": target})
            continue
        parent[key] = after
        module = str(target.get("module") or _module_from_field(field))
        if module not in changed_modules:
            changed_modules.append(module)
        rewrites.append(
            {
                "field": field,
                "module": module,
                "issue_code": target.get("issue_code"),
                "reason": target.get("reason"),
                "action": target.get("action"),
                "model": model,
                "before": before,
                "after": after,
            }
        )

    if rewrites:
        updated, warnings = ensure_brief_schema(updated, today or str(updated.get("date") or ""))
    else:
        warnings = []
    return {
        "brief": updated,
        "changed": bool(rewrites),
        "rewritten_modules": [f"content_issue:{module}" for module in changed_modules],
        "changed_modules": changed_modules,
        "changed_fields": [item["field"] for item in rewrites],
        "rewrites": rewrites,
        "skipped": skipped,
        "details": {"content_issue_rewrites": rewrites, "skipped": skipped, "schema_warnings": warnings},
    }
