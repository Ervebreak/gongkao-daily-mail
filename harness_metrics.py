from __future__ import annotations

import datetime as dt
import json
from typing import Any

from config import settings


TZ = dt.timezone(dt.timedelta(hours=8))


def _now() -> str:
    return dt.datetime.now(TZ).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def _module_scores(quality_payload: dict[str, Any]) -> dict[str, Any]:
    final = quality_payload.get("final") if isinstance(quality_payload.get("final"), dict) else {}
    scores: dict[str, Any] = {}
    for module, result in final.items():
        if isinstance(result, dict):
            scores[module] = result.get("score")
    return scores


def _module_statuses(quality_payload: dict[str, Any]) -> dict[str, Any]:
    final = quality_payload.get("final") if isinstance(quality_payload.get("final"), dict) else {}
    statuses: dict[str, Any] = {}
    for module, result in final.items():
        if isinstance(result, dict):
            statuses[module] = result.get("status") or ("ok" if result.get("ok") else "review")
    return statuses


def _issue_counts(quality_payload: dict[str, Any]) -> dict[str, int]:
    final = quality_payload.get("final") if isinstance(quality_payload.get("final"), dict) else {}
    counts = {"high": 0, "medium": 0, "low": 0}
    for result in final.values():
        if not isinstance(result, dict):
            continue
        for issue in result.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            severity = str(issue.get("severity") or "").lower()
            if severity in counts:
                counts[severity] += 1
    return counts


def _rewrite_modules(rewrite_result: dict[str, Any] | None) -> list[str]:
    if not isinstance(rewrite_result, dict):
        return []
    return [str(item) for item in (rewrite_result.get("rewritten_modules") or [])]


def _p0_repair_attempted(rewrite_result: dict[str, Any] | None) -> bool:
    if not isinstance(rewrite_result, dict):
        return False
    if rewrite_result.get("p0_repair_error"):
        return True
    for item in rewrite_result.get("rounds") or []:
        if isinstance(item, dict) and item.get("round") == "p0_repair":
            return True
    return False


def _llm_metrics(llm_trace_summary: dict[str, Any] | None) -> dict[str, int]:
    token_summary = (
        llm_trace_summary.get("_token_economics")
        if isinstance(llm_trace_summary, dict) and isinstance(llm_trace_summary.get("_token_economics"), dict)
        else {}
    )
    return {
        "llm_call_count": _safe_int(token_summary.get("llm_call_count")),
        "estimated_total_tokens": _safe_int(token_summary.get("estimated_total_tokens")),
        "selection_tokens": _safe_int(token_summary.get("selection_tokens")),
        "writing_tokens": _safe_int(token_summary.get("writing_tokens")),
        "rewrite_tokens": _safe_int(token_summary.get("rewrite_tokens")),
        "policy_rerank_tokens": _safe_int(token_summary.get("policy_rerank_tokens")),
        "lite_cta_tokens": _safe_int(token_summary.get("lite_cta_tokens")),
        "fallback_count": _safe_int(token_summary.get("fallback_count")),
    }


def append_metrics(record: dict[str, Any]) -> dict[str, Any]:
    if not settings.harness_metrics_enabled:
        return {"metrics_appended": False, "metrics_skip_reason": "HARNESS_METRICS_ENABLED=false"}
    path = settings.harness_metrics_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "created_at": _now(), **record}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return {"metrics_appended": True, "metrics_path": str(path)}


def append_nightly_metrics(
    *,
    delivery_date: str,
    test_invocation: bool,
    article_stats: dict[str, Any],
    quality_payload: dict[str, Any],
    rewrite_result: dict[str, Any] | None,
    candidate_save_result: dict[str, Any] | None,
    admin_report_result: dict[str, Any] | None,
    blocked_archive_result: dict[str, Any] | None,
    history_result: dict[str, Any] | None,
    archive_result: dict[str, Any] | None,
    final_selection: dict[str, Any] | None,
    llm_trace_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = quality_payload.get("gate") if isinstance(quality_payload.get("gate"), dict) else {}
    p0_repair_attempted = _p0_repair_attempted(rewrite_result)
    llm_metrics = _llm_metrics(llm_trace_summary)
    record = {
        "date": delivery_date,
        "mode": "nightly_candidate",
        "run_mode": settings.run_mode,
        "test_invocation": test_invocation,
        "quality_gate": gate.get("overall"),
        "p0_count": _safe_int(gate.get("p0_count")),
        "p0_repair_attempted": p0_repair_attempted,
        "p0_repair_success": (gate.get("overall") == "ok") if p0_repair_attempted else None,
        "rewrite_modules": _rewrite_modules(rewrite_result),
        "module_scores": _module_scores(quality_payload),
        "module_statuses": _module_statuses(quality_payload),
        "issue_counts": _issue_counts(quality_payload),
        "candidate_saved": bool(candidate_save_result and candidate_save_result.get("candidate_saved")),
        "candidate_path": (candidate_save_result or {}).get("candidate_oss_path") or (candidate_save_result or {}).get("candidate_local_path"),
        "admin_report_sent": bool(admin_report_result and admin_report_result.get("admin_report_sent")),
        "admin_report_skip_reason": (admin_report_result or {}).get("admin_report_skip_reason"),
        "blocked_archive_saved": bool(blocked_archive_result and blocked_archive_result.get("blocked_archive_saved")),
        "blocked_archive_path": (blocked_archive_result or {}).get("blocked_archive_path"),
        "history_write_ok": bool(history_result and history_result.get("history_write_ok")),
        "archive_saved": bool(archive_result and archive_result.get("daily_archive_saved")),
        "article_count": _safe_int(article_stats.get("candidate_count")),
        "history_excluded_count": _safe_int(article_stats.get("history_excluded_count")),
        "source_candidate_counts": article_stats.get("source_candidate_counts") or {},
        "featured_title": ((final_selection or {}).get("featured") or {}).get("title") if isinstance((final_selection or {}).get("featured"), dict) else None,
        "send_status": "blocked" if gate.get("overall") == "fail" else "pending_morning_send",
        **llm_metrics,
    }
    return append_metrics(record)


def append_morning_metrics(
    *,
    delivery_date: str,
    test_invocation: bool,
    status: str,
    reason: str | None = None,
    candidate: dict[str, Any] | None = None,
    load_meta: dict[str, Any] | None = None,
    send_result: dict[str, Any] | None = None,
    history_result: dict[str, Any] | None = None,
    archive_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate = candidate or {}
    gate = candidate.get("quality_gate") if isinstance(candidate.get("quality_gate"), dict) else {}
    quality_payload = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
    llm_metrics = _llm_metrics(candidate.get("llm_trace_summary") if isinstance(candidate.get("llm_trace_summary"), dict) else None)
    record = {
        "date": delivery_date,
        "mode": "morning_send",
        "run_mode": settings.run_mode,
        "test_invocation": test_invocation,
        "status": status,
        "reason": reason,
        "candidate_loaded": bool(candidate),
        "candidate_storage": (load_meta or {}).get("candidate_storage"),
        "candidate_path": (load_meta or {}).get("candidate_oss_path") or (load_meta or {}).get("candidate_local_path"),
        "quality_gate": gate.get("overall"),
        "p0_count": _safe_int(gate.get("p0_count")),
        "module_scores": _module_scores(quality_payload),
        "module_statuses": _module_statuses(quality_payload),
        "send_success_count": _safe_int((send_result or {}).get("success_count")),
        "send_fail_count": _safe_int((send_result or {}).get("fail_count")),
        "send_status": "sent" if _safe_int((send_result or {}).get("success_count")) > 0 else ("blocked" if status == "blocked" else "skipped"),
        "history_write_ok": bool(history_result and history_result.get("history_write_ok")),
        "archive_saved": bool(archive_result and archive_result.get("daily_archive_saved")),
        **llm_metrics,
    }
    return append_metrics(record)
