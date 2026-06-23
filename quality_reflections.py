from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TZ = dt.timezone(dt.timedelta(hours=8))
REFLECTION_SCHEMA_VERSION = 1
SUPPORTED_ISSUE_TYPES = {
    "half_sentence",
    "label_leak",
    "policy_weak_match",
    "lite_cta_salesy",
    "weekly_pdf_path_error",
    "internal_trace_leak",
    "daily_question_mismatch",
}
LABEL_LEAK_CODES = {
    "label_leak",
    "label_leaked_in_expression",
    "label_leaked_in_golden_sentence",
    "duplicate_label_prefix",
    "leading_colon",
    "rewritable_expression_label_prefix",
}
HALF_SENTENCE_CODES = {
    "text_truncation",
    "truncated_takeaway",
    "expression_truncated",
    "truncated_answer",
    "truncated_sentence",
    "truncated_label",
    "truncated_usage",
    "truncated_quick_read_one_sentence",
    "incomplete_sentence",
    "incomplete_label",
    "lite_cta_truncated",
    "policy_quote_incomplete",
    "authoritative_quote_incomplete",
    "policy_translation_incomplete",
    "article_connection_incomplete",
    "exam_transfer_incomplete",
}
INTERNAL_TRACE_CODES = {
    "dev_marker_leaked",
    "python_list_leaked",
    "quick_read_dev_marker",
    "lite_internal_marker_leaked",
    "weekly_pdf_internal_marker_leaked",
}
DAILY_QUESTION_CODES = {
    "missing_question",
    "missing_task",
    "too_broad",
    "daily_question_missing_identity",
    "daily_question_missing_scene",
    "daily_question_missing_conflict",
    "daily_question_missing_task",
    "question_type_mismatch",
    "question_too_interview_like",
}
WEEKLY_PDF_PATH_CODES = {
    "weekly_pdf_missing_oss_path",
    "weekly_pdf_lite_preview_missing_oss_path",
    "weekly_pdf_full_path_wrong_variant",
    "weekly_pdf_lite_path_wrong_variant",
    "weekly_pdf_date_range_mismatch",
    "weekly_pdf_invalid_date_range",
}
PROMOTED_STATUS_MAP = {
    "converted_to_rule": "rule",
    "covered_by_checker": "checker",
    "converted_to_script": "checker",
    "converted_to_example": "example",
    "needs_checker": "checker",
}
ROOT_CAUSE_BY_ISSUE_TYPE = {
    "half_sentence": "render",
    "label_leak": "render",
    "policy_weak_match": "generation",
    "lite_cta_salesy": "generation",
    "weekly_pdf_path_error": "OSS",
    "internal_trace_leak": "render",
    "daily_question_mismatch": "generation",
}
DETECTOR_BY_ISSUE_TYPE = {
    "half_sentence": "content_quality",
    "label_leak": "expression_quality",
    "policy_weak_match": "policy_coordinate_quality",
    "lite_cta_salesy": "lite_email_quality",
    "weekly_pdf_path_error": "weekly_pdf_quality",
    "internal_trace_leak": "quality_gate",
    "daily_question_mismatch": "question_quality",
}
AUTO_FIX_BY_ISSUE_TYPE = {
    "half_sentence": "minor_auto_fix_or_rewrite",
    "label_leak": "minor_auto_fix_or_rewrite",
    "policy_weak_match": "hide_policy_coordinate",
    "lite_cta_salesy": "safe_lite_cta_fallback",
    "weekly_pdf_path_error": "needs_manual_fix",
    "internal_trace_leak": "template_cleanup",
    "daily_question_mismatch": "needs_manual_fix",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8-sig")
    except Exception:
        return ""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values() if _text(item)).strip()
    if isinstance(value, list):
        return " ".join(_text(item) for item in value if _text(item)).strip()
    return " ".join(str(value).split()).strip()


def _clip(value: Any, limit: int = 220) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _now_iso() -> str:
    return dt.datetime.now(TZ).isoformat()


def _delivery_date(candidate: dict[str, Any], latest_quality: dict[str, Any], blocked_meta: dict[str, Any]) -> str:
    return str(
        candidate.get("delivery_date")
        or blocked_meta.get("delivery_date")
        or latest_quality.get("delivery_date")
        or ""
    )


def _make_source_run(source: str, delivery_date: str) -> str:
    safe_date = delivery_date or "unknown"
    return f"{source}:{safe_date}"


def _reflection_id(date_text: str, index: int) -> str:
    safe = re.sub(r"[^0-9]", "", date_text or "")[:8] or dt.datetime.now(TZ).strftime("%Y%m%d")
    return f"QR-{safe}-{index:03d}"


def _classify_issue(module: str, issue: dict[str, Any]) -> str | None:
    code = str(issue.get("code") or "").strip().lower()
    message = _text(issue.get("message")).lower()
    module_lower = module.lower()
    if code in HALF_SENTENCE_CODES or "truncat" in code or "incomplete" in code:
        return "half_sentence"
    if code in LABEL_LEAK_CODES or ("label" in code and "leak" in code):
        return "label_leak"
    if module_lower == "policy_coordinate" and ("weak_match" in code or "weak match" in message):
        return "policy_weak_match"
    if module_lower == "lite_email" and code in {"lite_cta_over_sales", "lite_value_not_specific"}:
        return "lite_cta_salesy"
    if code in WEEKLY_PDF_PATH_CODES:
        return "weekly_pdf_path_error"
    if code in INTERNAL_TRACE_CODES or ("internal" in code and "leak" in code) or ("debug" in message and "user" in message):
        return "internal_trace_leak"
    if module_lower == "daily_question" and (code in DAILY_QUESTION_CODES or "daily_question" in code):
        return "daily_question_mismatch"
    return None


def _root_cause(issue_type: str, module: str, issue: dict[str, Any], source_name: str) -> str:
    if source_name == "blocked_run":
        return "send"
    if issue_type == "weekly_pdf_path_error":
        return "OSS"
    if issue_type == "half_sentence" and source_name == "rewrite_comparison":
        return "repair"
    if issue_type == "internal_trace_leak" and module == "weekly_pdf":
        return "render"
    return ROOT_CAUSE_BY_ISSUE_TYPE.get(issue_type, "generation")


def _detector(issue_type: str, module: str, issue: dict[str, Any]) -> str:
    code = str(issue.get("code") or "").strip()
    if code:
        return code
    return DETECTOR_BY_ISSUE_TYPE.get(issue_type, "needs_detector")


def _auto_fix(issue_type: str, issue: dict[str, Any], source_name: str) -> str:
    if issue.get("auto_fixable"):
        return str(issue.get("auto_fix") or issue.get("fix_rule") or AUTO_FIX_BY_ISSUE_TYPE.get(issue_type) or "auto_fixable")
    return AUTO_FIX_BY_ISSUE_TYPE.get(issue_type, "needs_manual_fix")


def _existing_signature(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("source_run") or ""),
        str(row.get("issue_type") or ""),
        str(row.get("module") or ""),
        _clip(row.get("bad_example") or "", 220),
    )


def _promoted_to(row: dict[str, Any]) -> str:
    promoted = str(row.get("promoted_to") or "").strip()
    if promoted:
        return promoted
    status = str(row.get("status") or "").strip()
    return PROMOTED_STATUS_MAP.get(status, "archived")


def _extract_issues_from_quality(quality_payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    final = quality_payload.get("final") if isinstance(quality_payload.get("final"), dict) else {}
    rows: list[tuple[str, dict[str, Any]]] = []
    for module, payload in final.items():
        if not isinstance(payload, dict):
            continue
        for issue in payload.get("issues") or []:
            if isinstance(issue, dict):
                rows.append((str(module), issue))
    gate = quality_payload.get("gate") if isinstance(quality_payload.get("gate"), dict) else {}
    for issue in gate.get("p0_issues") or []:
        if isinstance(issue, dict):
            rows.append((str(issue.get("module") or "quality_gate"), issue))
    return rows


def _extract_rewrite_rows(rewrite_comparison: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for row in rewrite_comparison:
        if not isinstance(row, dict):
            continue
        module = str(row.get("module") or "")
        issues_before = row.get("issues_before") if isinstance(row.get("issues_before"), list) else []
        for issue in issues_before:
            if isinstance(issue, dict):
                rows.append((module, issue, row))
    return rows


def _build_reflection_row(
    *,
    issue_type: str,
    module: str,
    issue: dict[str, Any],
    source_name: str,
    source_run: str,
    rewrite_row: dict[str, Any] | None = None,
    latest_quality_card: str = "",
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate = candidate or {}
    bad_example = _clip(
        issue.get("bad_text")
        or (rewrite_row or {}).get("before")
        or issue.get("message")
        or "",
        320,
    )
    fix_summary = _clip(
        issue.get("suggestion")
        or issue.get("fix_rule")
        or (rewrite_row or {}).get("after")
        or "",
        320,
    )
    severity = str(issue.get("severity") or "").lower() or ("high" if str(issue.get("level") or "").upper() == "P0" else "medium")
    delivery_date = str(candidate.get("delivery_date") or source_run.rsplit(":", 1)[-1])
    payload = {
        "reflection_schema_version": REFLECTION_SCHEMA_VERSION,
        "date": delivery_date,
        "module": module,
        "issue_type": issue_type,
        "severity": severity,
        "source": source_name,
        "source_run": source_run,
        "bad_example": bad_example,
        "reason": _clip(issue.get("message") or "", 320),
        "fix_rule": fix_summary,
        "root_cause": _root_cause(issue_type, module, issue, source_name),
        "detector": _detector(issue_type, module, issue),
        "auto_fix": _auto_fix(issue_type, issue, source_name),
        "regression_case": False,
        "promoted_to": "archived",
        "recurrence_count": 1,
        "related_rule": issue.get("related_rule") or [],
        "checker_to_add": issue.get("checker_to_add") or "",
        "quality_card_excerpt": _clip(latest_quality_card, 220) if latest_quality_card else "",
        "candidate_subject": str(candidate.get("subject") or ""),
    }
    return payload


def _blocked_run_meta(blocked_run_dir: Path | None) -> dict[str, Any]:
    if not blocked_run_dir or not blocked_run_dir.exists():
        return {}
    return _read_json(blocked_run_dir / "run_meta.json")


def _candidate_from_latest(output_dir: Path) -> dict[str, Any]:
    return _read_json(output_dir / "candidates" / "latest.json")


def _latest_blocked_run_dir(output_dir: Path, delivery_date: str = "") -> Path | None:
    blocked_root = output_dir / "blocked_runs"
    if not blocked_root.exists():
        return None
    if delivery_date:
        target = blocked_root / delivery_date
        if target.exists():
            return target
    children = [item for item in blocked_root.iterdir() if item.is_dir()]
    if not children:
        return None
    return sorted(children, key=lambda item: item.stat().st_mtime, reverse=True)[0]


def generate_quality_reflections(
    *,
    output_dir: Path,
    knowledge_dir: Path,
    candidate: dict[str, Any] | None = None,
    latest_quality: dict[str, Any] | None = None,
    latest_quality_card: str | None = None,
    rewrite_comparison: list[dict[str, Any]] | None = None,
    blocked_run_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    knowledge_dir = knowledge_dir.resolve()
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    candidate = candidate or _candidate_from_latest(output_dir)
    latest_quality = latest_quality or _read_json(output_dir / "latest_quality.json")
    latest_quality_card = latest_quality_card if latest_quality_card is not None else _read_text(output_dir / "latest_quality_card.md")
    rewrite_comparison = rewrite_comparison if rewrite_comparison is not None else (
        latest_quality.get("rewrite_comparison") if isinstance(latest_quality.get("rewrite_comparison"), list) else []
    )
    delivery_date = _delivery_date(candidate, latest_quality, _blocked_run_meta(blocked_run_dir))
    blocked_run_dir = blocked_run_dir or _latest_blocked_run_dir(output_dir, delivery_date)
    blocked_meta = _blocked_run_meta(blocked_run_dir)
    existing_rows = _read_jsonl(knowledge_dir / "quality_issues.jsonl")
    existing_signatures = {_existing_signature(row) for row in existing_rows}

    raw_rows: list[dict[str, Any]] = []
    quality_source_run = _make_source_run("latest_quality", delivery_date)
    for module, issue in _extract_issues_from_quality(latest_quality):
        issue_type = _classify_issue(module, issue)
        if issue_type not in SUPPORTED_ISSUE_TYPES:
            continue
        raw_rows.append(
            _build_reflection_row(
                issue_type=issue_type,
                module=module,
                issue=issue,
                source_name="quality_card" if latest_quality_card else "latest_quality",
                source_run=quality_source_run,
                latest_quality_card=latest_quality_card or "",
                candidate=candidate,
            )
        )

    rewrite_source_run = _make_source_run("rewrite_comparison", delivery_date)
    for module, issue, row in _extract_rewrite_rows(rewrite_comparison or []):
        issue_type = _classify_issue(module, issue)
        if issue_type not in SUPPORTED_ISSUE_TYPES:
            continue
        raw_rows.append(
            _build_reflection_row(
                issue_type=issue_type,
                module=module or "rewrite_comparison",
                issue=issue,
                source_name="rewrite_comparison",
                source_run=rewrite_source_run,
                rewrite_row=row,
                latest_quality_card=latest_quality_card or "",
                candidate=candidate,
            )
        )

    blocked_quality = _read_json(blocked_run_dir / "latest_quality.json") if blocked_run_dir else {}
    blocked_source_run = _make_source_run("blocked_run", delivery_date) if blocked_quality else ""
    for module, issue in _extract_issues_from_quality(blocked_quality):
        issue_type = _classify_issue(module, issue)
        if issue_type not in SUPPORTED_ISSUE_TYPES:
            continue
        raw_rows.append(
            _build_reflection_row(
                issue_type=issue_type,
                module=module,
                issue=issue,
                source_name="blocked_run",
                source_run=blocked_source_run,
                latest_quality_card=latest_quality_card or "",
                candidate=candidate,
            )
        )

    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in raw_rows:
        key = (str(row.get("issue_type") or ""), str(row.get("module") or ""), _clip(row.get("bad_example") or "", 220))
        current = deduped.get(key)
        if current is None:
            deduped[key] = row
            continue
        priority = {"blocked_run": 3, "latest_quality": 2, "quality_card": 2, "rewrite_comparison": 1}
        if priority.get(str(row.get("source") or ""), 0) > priority.get(str(current.get("source") or ""), 0):
            deduped[key] = row

    grouped_existing: dict[tuple[str, str], int] = defaultdict(int)
    existing_id_numbers: list[int] = []
    for item in existing_rows:
        grouped_existing[(str(item.get("issue_type") or ""), str(item.get("module") or ""))] += 1
        match = re.match(r"QR-\d{8}-(\d+)$", str(item.get("id") or ""))
        if match:
            existing_id_numbers.append(int(match.group(1)))

    new_rows: list[dict[str, Any]] = []
    next_index = (max(existing_id_numbers) if existing_id_numbers else 0) + 1
    grouped_new_counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in deduped.values():
        signature = _existing_signature(row)
        if signature in existing_signatures:
            continue
        group_key = (str(row.get("issue_type") or ""), str(row.get("module") or ""))
        grouped_new_counts[group_key] += 1
        row["recurrence_count"] = grouped_existing[group_key] + grouped_new_counts[group_key]
        row["id"] = _reflection_id(delivery_date, next_index)
        next_index += 1
        new_rows.append(row)

    if new_rows:
        path = knowledge_dir / "quality_issues.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            for row in new_rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    all_rows = existing_rows + new_rows
    reflection_rows = [row for row in all_rows if int(row.get("reflection_schema_version") or 0) == REFLECTION_SCHEMA_VERSION]
    issue_type_counts = Counter(str(row.get("issue_type") or "unknown") for row in reflection_rows)
    recurring_counts = Counter(
        str(row.get("issue_type") or "unknown")
        for row in reflection_rows
        if int(row.get("recurrence_count") or 0) > 1
    )
    promoted_counts = Counter(_promoted_to(row) for row in reflection_rows)
    latest_payload = {
        "schema_version": REFLECTION_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "delivery_date": delivery_date,
        "source_run": blocked_source_run or quality_source_run,
        "reflection_count": len(new_rows),
        "reflections": new_rows,
        "summary": {
            "supported_issue_types": sorted(SUPPORTED_ISSUE_TYPES),
            "issue_type_counts": dict(issue_type_counts),
            "repeated_issue_types": dict(recurring_counts),
            "promoted_counts": dict(promoted_counts),
        },
        "blocked_run_dir": str(blocked_run_dir) if blocked_run_dir else "",
    }
    _write_json(output_dir / "latest_quality_reflections.json", latest_payload)
    return latest_payload


def load_latest_quality_reflections(output_dir: Path) -> dict[str, Any]:
    return _read_json(output_dir / "latest_quality_reflections.json")


def render_reflection_lines(reflection_payload: dict[str, Any], limit: int = 5) -> list[str]:
    rows = reflection_payload.get("reflections") if isinstance(reflection_payload.get("reflections"), list) else []
    if not rows:
        return ["- 本次未新增 reflection。"]
    lines: list[str] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- {row.get('issue_type')} / {row.get('module')} / {row.get('root_cause')} / "
            f"detector={row.get('detector')} / auto_fix={row.get('auto_fix')}"
        )
    return lines or ["- 本次未新增 reflection。"]
