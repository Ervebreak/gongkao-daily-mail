from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

try:
    import requests
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass

from config import settings
from feedback import handle_feedback, is_feedback_invocation
from logger import RunLogger


TZ = dt.timezone(dt.timedelta(hours=8))


def normalize_event(event: Any) -> dict[str, Any]:
    def _merge_fc_timer_payload(payload: dict[str, Any]) -> dict[str, Any]:
        raw_payload = payload.get("payload")
        if not isinstance(raw_payload, str) or not raw_payload.strip():
            return payload
        try:
            inner = json.loads(raw_payload)
        except Exception:
            return payload
        if not isinstance(inner, dict):
            return payload
        # Aliyun timer events wrap the configured trigger message in a
        # top-level "payload" string. Inner fields must win, otherwise mode
        # falls back to RUN_MODE=prod and can accidentally enter the send path.
        return {**payload, **inner, "_fc_trigger_payload": raw_payload}

    if isinstance(event, dict):
        return _merge_fc_timer_payload(event)
    if isinstance(event, (bytes, bytearray)):
        try:
            parsed = json.loads(event.decode("utf-8"))
            return _merge_fc_timer_payload(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    if isinstance(event, str):
        try:
            parsed = json.loads(event)
            return _merge_fc_timer_payload(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _context_value(context: Any, *names: str) -> Any:
    if context is None:
        return None
    for name in names:
        if hasattr(context, name):
            value = getattr(context, name)
            if value not in (None, ""):
                return value
    return None


def extract_request_id(event: Any, context: Any | None = None) -> str:
    payload = normalize_event(event)
    for key in ("requestId", "request_id", "requestid", "fc_request_id"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else {}
    for key in ("x-fc-request-id", "x-request-id"):
        value = headers.get(key) or headers.get(key.title())
        if value not in (None, ""):
            return str(value)
    value = _context_value(context, "request_id", "requestId")
    return str(value) if value not in (None, "") else ""


def extract_trigger_name(event: Any) -> str:
    payload = normalize_event(event)
    for key in ("triggerName", "trigger_name", "trigger"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def extract_trigger_time(event: Any) -> str:
    payload = normalize_event(event)
    for key in ("triggerTime", "trigger_time", "eventTime"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def build_log_context(event: Any, context: Any | None = None) -> dict[str, Any]:
    payload = normalize_event(event)
    return {
        "request_id": extract_request_id(payload, context),
        "trigger_name": extract_trigger_name(payload),
        "trigger_time": extract_trigger_time(payload),
        "fc_service": _context_value(context, "service_name", "serviceName"),
        "fc_function": _context_value(context, "function_name", "functionName"),
        "fc_qualifier": _context_value(context, "qualifier"),
    }


def summarize_llm_trace(events: list[dict[str, Any]]) -> dict[str, Any]:
    stage_summary: dict[str, dict[str, Any]] = {}
    for event in events:
        stage = str(event.get("stage") or "unknown")
        item = stage_summary.setdefault(
            stage,
            {
                "attempted_models": [],
                "successful_models": [],
                "failed_models": [],
                "final_model": "",
                "attempt_count": 0,
            },
        )
        model = str(event.get("model") or "").strip()
        if model and model not in item["attempted_models"]:
            item["attempted_models"].append(model)
        if event.get("event") == "llm_request_start":
            item["attempt_count"] += 1
        if event.get("event") == "llm_stage_attempt_succeeded":
            if model and model not in item["successful_models"]:
                item["successful_models"].append(model)
            if model:
                item["final_model"] = model
        if event.get("event") == "llm_stage_attempt_failed" and model and model not in item["failed_models"]:
            item["failed_models"].append(model)
    return stage_summary


def is_test_invocation(event: Any) -> bool:
    payload = normalize_event(event)
    mode = str(payload.get("mode") or payload.get("run_mode") or "").strip().lower()
    trigger = str(payload.get("trigger") or payload.get("source") or "").strip().lower()
    return mode == "test" or trigger == "manual_test" or settings.run_mode == "test"


def event_mode(event: Any) -> str:
    payload = normalize_event(event)
    return str(payload.get("mode") or payload.get("run_mode") or settings.run_mode or "").strip().lower()


def is_nightly_candidate_invocation(event: Any) -> bool:
    return event_mode(event) in {"nightly_candidate", "candidate_generate", "generate_candidate", "nightly"}


def is_morning_candidate_send_invocation(event: Any) -> bool:
    return event_mode(event) in {"morning_send", "candidate_send", "send_candidate"}


def is_weekly_pdf_candidate_invocation(event: Any) -> bool:
    return event_mode(event) in {"weekly_pdf_candidate", "weekly_candidate", "nightly_weekly_pdf"}


def should_generate_weekly_pdf_candidate_today(event: Any, delivery_date: str) -> bool:
    payload = normalize_event(event)
    force_daily = str(payload.get("force_daily") or payload.get("skip_weekly_pdf_candidate") or "").strip().lower() in {"1", "true", "yes", "y", "on"}
    if force_daily or not settings.enable_weekly_pdf:
        return False
    try:
        candidate_day = dt.date.fromisoformat(delivery_date[:10])
    except Exception:
        return False
    return candidate_day.weekday() == settings.weekly_pdf_weekday


def resolve_delivery_date(event: Any, *, nightly_candidate: bool = False) -> str:
    payload = normalize_event(event)
    explicit = str(payload.get("delivery_date") or payload.get("candidate_date") or payload.get("date") or "").strip()
    if explicit:
        return explicit[:10]
    base = dt.datetime.now(TZ).date()
    if nightly_candidate:
        base = base + dt.timedelta(days=1)
    return base.isoformat()


def is_feedback_test_email_invocation(event: Any) -> bool:
    payload = normalize_event(event)
    task = str(payload.get("task") or payload.get("type") or "").strip().lower()
    mode = str(payload.get("mode") or payload.get("run_mode") or "").strip().lower()
    return task in {"feedback_test_email", "feedback_buttons_test"} or mode in {"feedback_test_email", "feedback_buttons_test"}


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _quality_issue_signature(issue: Any) -> tuple[str, str, str]:
    if not isinstance(issue, dict):
        return ("", "", str(issue))
    return (
        str(issue.get("module") or ""),
        str(issue.get("code") or ""),
        str(issue.get("message") or ""),
    )


def apply_manual_quality_override(previous_gate: dict[str, Any], current_gate: dict[str, Any]) -> dict[str, Any]:
    if previous_gate.get("overall") != "ok" or not previous_gate.get("manual_override"):
        return current_gate
    if current_gate.get("overall") == "ok":
        return current_gate

    original_gate = previous_gate.get("original_quality_gate")
    if not isinstance(original_gate, dict):
        return current_gate

    original_p0 = {_quality_issue_signature(issue) for issue in original_gate.get("p0_issues") or []}
    current_p0 = {_quality_issue_signature(issue) for issue in current_gate.get("p0_issues") or []}
    if current_p0 and current_p0 == original_p0:
        merged_gate = dict(previous_gate)
        merged_gate["current_quality_gate"] = current_gate
        merged_gate["manual_override_reapplied"] = True
        return merged_gate
    return current_gate


def build_quality_gate(
    question_quality: dict[str, Any],
    framework_quality: dict[str, Any],
    takeaway_quality: dict[str, Any] | None = None,
    brief_quality: dict[str, Any] | None = None,
    quick_reads_quality: dict[str, Any] | None = None,
    duplication_quality: dict[str, Any] | None = None,
    expression_quality: dict[str, Any] | None = None,
    module_redundancy_quality: dict[str, Any] | None = None,
    content_risk_quality: dict[str, Any] | None = None,
    selection_quality: dict[str, Any] | None = None,
    content_quality: dict[str, Any] | None = None,
    cleanliness_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p0_codes = {
        "missing_question",
        "missing_task",
        "too_broad",
        "missing_candidate_answer",
        "truncated_answer",
        "isolated_number",
        "incomplete_sentence",
        "suspected_truncated_sentence",
        "grassroots_authority_overreach",
        "incomplete_label",
        "exam_migration_step",
        "missing_main_line",
        "too_few_steps",
        "empty_golden_sentence",
        "label_leaked_in_golden_sentence",
        "truncated_takeaway",
        "truncated_golden_usage",
        "truncated_common_knowledge",
        "email_too_short",
        "missing_html",
        "dev_marker_leaked",
        "python_list_leaked",
        "truncated_email",
        "incomplete_sentence_line",
        "quick_read_dev_marker",
        "empty_quick_read",
        "missing_quick_read_one_sentence",
        "truncated_quick_read_one_sentence",
        "truncated_quick_read_exam_value",
        "quick_read_url_not_valid",
        "quick_reads_all_news_summary",
        "weak_featured_selection",
        "sensitive_topic_needs_review",
        "dev_marker_repeated",
        "abnormal_copy_duplication",
        "repeated_expression_across_modules",
        "module_role_overlap",
        "expression_dev_marker",
        "expression_truncated",
        "label_leaked_in_expression",
        "fixed_framework_template",
        "universal_framework_content",
        "content_quality_p0",
        "low_content_quality",
        "low_user_safety",
        "low_exam_value",
        "low_source_alignment",
        "unsafe_sensitive_framing",
        "unsupported_claims",
        "mainline_incoherent",
        "content_quality_reviewer_error",
        "duplicate_label_prefix",
        "leading_colon",
        "rewritable_expression_label_prefix",
        "duplicate_subject_prefix",
        "daily_question_missing_identity",
        "daily_question_missing_scene",
        "daily_question_missing_conflict",
        "daily_question_missing_task",
    }
    p0_issues: list[dict[str, str]] = []
    modules = (
        ("daily_question", question_quality),
        ("framework_map", framework_quality),
        ("today_takeaway", takeaway_quality or {}),
        ("brief_cleanliness", brief_quality or {}),
        ("quick_reads", quick_reads_quality or {}),
        ("duplication", duplication_quality or {}),
        ("expression_quality", expression_quality or {}),
        ("module_redundancy", module_redundancy_quality or {}),
        ("content_risk", content_risk_quality or {}),
        ("selection", selection_quality or {}),
        ("content_quality", content_quality or {}),
        ("pre_send_cleanliness", cleanliness_quality or {}),
    )
    for module, quality in modules:
        for issue in quality.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "")
            severity = str(issue.get("severity") or "").lower()
            if severity == "high" and code in p0_codes:
                p0_issues.append({
                    "module": str(issue.get("module_override") or module),
                    "code": code,
                    "message": str(issue.get("message") or code),
                })
    return {
        "overall": "fail" if p0_issues else "ok",
        "p0_count": len(p0_issues),
        "p0_issues": p0_issues[:8],
    }


SENSITIVE_TOPIC_TERMS = (
    "彩礼",
    "婚育",
    "性别",
    "女性",
    "男方",
    "女方",
    "恐婚",
    "生育",
    "家庭伦理",
)

GENDER_SENSITIVE_EXPRESSIONS = (
    "女性稀缺性",
    "女性被定价",
    "女性被简化为商品",
    "婚姻成本转嫁给男方家庭",
    "彩礼等于身价",
)


def _stringify_for_quality(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_stringify_for_quality(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_stringify_for_quality(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _selection_sensitive_surface(brief: dict[str, Any], featured: dict[str, Any], article: dict[str, Any]) -> str:
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    three = brief.get("today_three_things") if isinstance(brief.get("today_three_things"), dict) else {}
    framework_map = article.get("article_framework_map") if isinstance(article.get("article_framework_map"), dict) else {}
    values = [
        brief.get("email_subject"),
        brief.get("today_theme"),
        three.get("theme"),
        three.get("daily_question"),
        featured.get("title"),
        featured.get("theme"),
        article.get("title"),
        article.get("theme"),
        question.get("question"),
        question.get("topic_category"),
        framework_map.get("main_thread"),
        framework_map.get("overall_exam_value"),
        framework_map.get("steps"),
        article.get("article_framework"),
    ]
    return _stringify_for_quality(values)


def evaluate_selection_quality(brief: dict[str, Any]) -> dict[str, Any]:
    two_stage = brief.get("_llm_two_stage") if isinstance(brief.get("_llm_two_stage"), dict) else {}
    selection = two_stage.get("selection") if isinstance(two_stage.get("selection"), dict) else {}
    featured = selection.get("featured") if isinstance(selection.get("featured"), dict) else {}
    article = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    issues: list[dict[str, str]] = []
    score = featured.get("total_score")
    try:
        total_score = int(score)
    except Exception:
        total_score = -1
    if total_score >= 0 and total_score < 75:
        issues.append({
            "severity": "high",
            "code": "weak_featured_selection",
            "message": f"主线文章选题分过低：{total_score}，应重新选题或进入人工复核",
        })
    sensitive_surface = _selection_sensitive_surface(brief, featured, article)
    sensitive_hits = [term for term in SENSITIVE_TOPIC_TERMS if term in sensitive_surface]
    if sensitive_hits and total_score >= 0 and total_score < 85:
        issues.append({
            "severity": "high",
            "code": "sensitive_topic_needs_review",
            "message": f"敏感主题选题分低于 85（{total_score}），命中：{'、'.join(sensitive_hits[:5])}，需人工复核或重选。",
        })
    body_text = _stringify_for_quality(brief)
    expression_hits = [term for term in GENDER_SENSITIVE_EXPRESSIONS if term in body_text]
    if expression_hits:
        issues.append({
            "severity": "high",
            "code": "gender_sensitive_expression",
            "message": f"正文含性别/婚育敏感表达：{'、'.join(expression_hits[:5])}，需改写为中性治理表述。",
        })
    if featured.get("risk_note"):
        issues.append({
            "severity": "medium",
            "code": "selection_risk_note",
            "message": str(featured.get("risk_note")),
        })
    high_count = sum(1 for issue in issues if issue.get("severity") == "high")
    return {
        "ok": high_count == 0,
        "status": "fail" if high_count else ("review" if issues else "ok"),
        "score": 100 if not issues else (60 if high_count else 82),
        "checks": {"featured_total_score": total_score, "featured_title": featured.get("title") or article.get("title")},
        "issues": issues,
    }


def _quality_for_p0_repair(
    quality: dict[str, Any],
    module: str,
    p0_issues: list[dict[str, Any]],
    force: bool = False,
) -> dict[str, Any]:
    module_issues = [issue for issue in p0_issues if issue.get("module") == module]
    if not module_issues and not force:
        return {"ok": True, "status": "ok", "score": quality.get("score", 100), "issues": []}
    issues = module_issues or [
        {
            "severity": "high",
            "code": "brief_cleanliness_p0",
            "message": "整封邮件清洁度 P0，需重写该内容模块以排除泄露、截断或异常格式。",
        }
    ]
    repaired = dict(quality or {})
    repaired["ok"] = False
    repaired["status"] = "fail"
    repaired["issues"] = list(issues)
    return repaired


def merge_rewrite_results(primary: dict[str, Any] | None, secondary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not primary and not secondary:
        return None
    merged: dict[str, Any] = {
        "rewritten_modules": [],
        "details": {},
        "rounds": [],
    }
    for label, item in (("initial", primary), ("p0_repair", secondary)):
        if not isinstance(item, dict):
            continue
        if item.get("rolled_back"):
            continue
        merged["rounds"].append({"round": label, **{key: value for key, value in item.items() if key != "brief"}})
        for module in item.get("rewritten_modules") or []:
            if module not in merged["rewritten_modules"]:
                merged["rewritten_modules"].append(module)
        if isinstance(item.get("details"), dict):
            for key, value in item["details"].items():
                merged["details"][f"{label}:{key}"] = value
        if item.get("error"):
            merged[f"{label}_error"] = item.get("error")
    return merged


def build_history_records(brief: dict[str, Any], today: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    featured = brief.get("featured_article", {})
    if featured.get("title") or featured.get("url"):
        records.append(
            {
                "date": today,
                "title": featured.get("title", ""),
                "url": featured.get("url", ""),
                "source": featured.get("source", ""),
                "published_at": featured.get("published_at", ""),
                "role": "featured",
                "theme": featured.get("theme") or brief.get("today_theme", ""),
            }
        )
    for item in brief.get("quick_reads", []):
        records.append(
            {
                "date": today,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "published_at": item.get("published_at", ""),
                "role": "quick_read",
                "theme": item.get("theme") or "",
            }
        )
    common = brief.get("daily_common_knowledge", {})
    if common.get("knowledge_point"):
        records.append(
            {
                "date": today,
                "title": common.get("knowledge_point", ""),
                "url": "",
                "source": "邮件模块",
                "published_at": today,
                "role": "common_knowledge",
                "theme": brief.get("today_theme", ""),
            }
        )
    return records


def summarize_final_selection(brief: dict[str, Any]) -> dict[str, Any]:
    def scalar_text(value: Any) -> str:
        if isinstance(value, list):
            return " / ".join(str(item) for item in value if item)
        if isinstance(value, dict):
            return " / ".join(str(item) for item in value.values() if item)
        return str(value) if value else ""

    featured = brief.get("featured_article", {})
    quick_reads = brief.get("quick_reads", [])
    sources = [scalar_text(featured.get("source"))] + [scalar_text(item.get("source")) for item in quick_reads]
    themes = [scalar_text(featured.get("theme"))] + [scalar_text(item.get("theme")) for item in quick_reads]
    sources = [item for item in sources if item]
    themes = [item for item in themes if item]
    return {
        "featured": {
            "title": featured.get("title"),
            "source": featured.get("source"),
            "theme": scalar_text(featured.get("theme")),
            "published_at": featured.get("published_at"),
            "url": featured.get("url"),
        },
        "quick_reads": [
            {
                "title": item.get("title"),
                "source": item.get("source"),
                "theme": scalar_text(item.get("theme")),
                "published_at": item.get("published_at"),
                "url": item.get("url"),
            }
            for item in quick_reads
        ],
        "featured_quick_sources_diverse": len(set(sources)) > 1 if len(sources) > 1 else True,
        "featured_quick_themes_diverse": len(set(themes)) > 1 if len(themes) > 1 else True,
    }


def detect_theme_changes(articles: list[Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    article_theme_by_url = {getattr(item, "url", ""): " / ".join(getattr(item, "themes", [])[:2]) for item in articles}
    article_theme_by_title = {getattr(item, "title", ""): " / ".join(getattr(item, "themes", [])[:2]) for item in articles}
    rows: list[dict[str, str]] = []
    final_items = [brief.get("featured_article", {})] + list(brief.get("quick_reads", []))
    for item in final_items:
        title = str(item.get("title", ""))
        url = str(item.get("url", ""))
        candidate_theme = article_theme_by_url.get(url) or article_theme_by_title.get(title) or ""
        final_theme = str(item.get("theme", ""))
        if candidate_theme and final_theme and candidate_theme != final_theme:
            rows.append(
                {
                    "title": title,
                    "candidate_theme": candidate_theme,
                    "final_theme": final_theme,
                    "reason": "最终主题由大模型重判或 brief_schema 兜底字段修正导致",
                }
            )
    return rows



def compact_source_fetch_status(fetch_status: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for source, status in (fetch_status or {}).items():
        if not isinstance(status, dict):
            compact[source] = status
            continue
        diagnostics = status.get("diagnostics") or {}
        page_rows = []
        for row in (status.get("page_debug") or [])[:5]:
            if not isinstance(row, dict):
                continue
            page_rows.append({
                "column": row.get("column"),
                "url": row.get("url"),
                "status": row.get("status"),
                "html_chars": row.get("html_chars"),
                "anchors": row.get("anchors"),
                "parsed_anchor_candidates": row.get("parsed_anchor_candidates"),
                "parsed_embedded_candidates": row.get("parsed_embedded_candidates"),
                "unique_candidates": row.get("unique_candidates"),
                "recent_candidates": row.get("recent_candidates"),
                "article_fetch_ok": row.get("article_fetch_ok"),
                "article_fetch_failed": row.get("article_fetch_failed"),
                "error": row.get("error"),
                "sample_titles": row.get("sample_titles"),
            })
        compact[source] = {
            "called": status.get("called"),
            "found": status.get("found"),
            "status": status.get("status"),
            "errors": status.get("errors"),
            "diagnostics": diagnostics,
            "page_debug": page_rows,
        }
    return compact


def compact_article_stats(article_stats: dict[str, Any]) -> dict[str, Any]:
    # Avoid FC log-line truncation: source_candidate_details/rejected_sample can be huge.
    keys = [
        "candidate_count",
        "raw_candidate_count",
        "recent_48h_count",
        "recent_7d_count",
        "unknown_date_count",
        "older_than_7d_count",
        "source_candidate_counts",
        "source_zero_reasons",
        "history_path",
        "history_excluded_count",
        "configured_article_sources",
        "reserved_sources_note",
    ]
    return {key: article_stats.get(key) for key in keys if key in article_stats}

def should_attach_weekly_pdf_today(event: Any, today: str, test_invocation: bool = False) -> tuple[bool, dict[str, Any]]:
    """判断普通晨读邮件是否自动附带周 PDF。

    默认只在 WEEKLY_PDF_WEEKDAY 当天触发；手动测试可在测试事件里加
    {"force_weekly_pdf": true} 直接强制生成并附加。
    """
    payload = normalize_event(event)
    force = str(payload.get("force_weekly_pdf") or payload.get("attach_weekly_pdf") or "").strip().lower() in {"1", "true", "yes", "y", "on"}
    now = dt.datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=TZ)
    weekday = now.weekday()
    enabled = settings.enable_weekly_pdf and settings.weekly_pdf_attach_on_weekend and settings.weekly_pdf_attach
    should = bool((enabled and weekday == settings.weekly_pdf_weekday) or force)
    meta = {
        "enabled": settings.enable_weekly_pdf,
        "attach_on_weekend": settings.weekly_pdf_attach_on_weekend,
        "weekly_pdf_attach": settings.weekly_pdf_attach,
        "weekly_pdf_weekday": settings.weekly_pdf_weekday,
        "today_weekday": weekday,
        "force_weekly_pdf": force,
        "test_invocation": test_invocation,
        "should_attach": should,
    }
    return should, meta


def send_feedback_test_email(event: Any | None = None) -> dict[str, Any]:
    from email_renderer import render_feedback_buttons
    from email_sender import send_email

    today = dt.datetime.now(TZ).strftime("%Y-%m-%d")
    mail_id = f"feedback-test-{today}"
    brief = {"date": today, "mail_id": mail_id}
    buttons = render_feedback_buttons(brief)
    subject_prefix = getattr(settings, "subject_prefix", "【公考晨读】")
    subject = f"{subject_prefix}反馈按钮测试"
    html_body = f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f6f8fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;color:#0f172a;">
  <div style="max-width:620px;margin:0 auto;padding:18px 12px;">
    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:14px;padding:18px 20px;">
      <div style="font-size:18px;font-weight:900;margin-bottom:10px;">反馈按钮测试</div>
      <div style="font-size:14px;line-height:1.7;color:#334155;margin-bottom:12px;">这封邮件只用于测试内测反馈按钮，不会触发抓取文章、写文、周 PDF 或历史记录。</div>
      <div style="font-size:15px;font-weight:900;color:#0f172a;margin-bottom:8px;">内测反馈｜可多选，点一下就行</div>
      <div style="font-size:13px;line-height:1.72;margin-bottom:8px;">今天这封你觉得？</div>
      <div style="line-height:1.9;">{buttons}</div>
      <div style="font-size:13px;line-height:1.72;margin-top:8px;color:#64748b;">如果你愿意，也可以直接回复邮件说两句。</div>
    </div>
  </div>
</body>
</html>"""
    plain_text = (
        "反馈按钮测试\n"
        "这封邮件只用于测试内测反馈按钮，不会触发抓取文章、写文、周 PDF 或历史记录。\n"
        "请在 HTML 邮件里点击反馈按钮。"
    )
    send_result = send_email(subject, plain_text, html_body, test_mode=True)
    return {
        "status": "ok",
        "task": "feedback_test_email",
        "date": today,
        "mail_id": mail_id,
        "feedback_base_url": settings.feedback_base_url,
        "sent": True,
        "send_result": send_result,
    }


def build_run_summary(
    article_stats: dict[str, Any],
    final_selection: dict[str, Any],
    history_result: dict[str, Any],
    send_result: dict[str, Any] | None,
) -> str:
    send_result = send_result or {"success_count": 0, "fail_count": 0}
    source_counts = article_stats.get("source_candidate_counts", {})
    zero_reasons = article_stats.get("source_zero_reasons", {})
    featured = final_selection.get("featured", {})
    quick_reads = final_selection.get("quick_reads", [])
    lines = [
        "【今日运行摘要】",
        f"各来源候选数量：{source_counts}",
        f"来源为0的原因：{zero_reasons or '无'}",
        f"历史记录路径：{history_result.get('history_path') or article_stats.get('history_path')}",
        (
            "历史是否稳定持久化：本次为测试/非晨发窗口，按设置不写入；已有 OSS 历史仍可用于去重。"
            if history_result.get("history_skip_reason")
            else (
                "历史是否稳定持久化：是，当前 HISTORY_STORAGE=oss。"
                if history_result.get("history_storage") == "oss" and history_result.get("history_write_ok")
                else "历史是否稳定持久化：否。当前 HISTORY_STORAGE=local 或 OSS 未写入成功；若位于 /tmp，阿里云 FC 冷启动或跨实例时可能丢失。"
            )
        ),
        f"历史去重排除文章数量：{article_stats.get('history_excluded_count', 0)}",
        f"最终精读：{featured.get('title')}｜{featured.get('source')}｜{featured.get('theme')}｜{featured.get('published_at')}",
        "最终速读：" + "；".join(
            f"{item.get('title')}｜{item.get('source')}｜{item.get('theme')}｜{item.get('published_at')}"
            for item in quick_reads
        ),
        f"精读与速读来源是否不同：{final_selection.get('featured_quick_sources_diverse')}",
        f"精读与速读主题是否不同：{final_selection.get('featured_quick_themes_diverse')}",
    ]
    if not final_selection.get("featured_quick_sources_diverse"):
        lines.append(f"来源未均衡原因：{article_stats.get('source_balance_note') or '其他来源无候选或考试转化价值较低'}")
    if not final_selection.get("featured_quick_themes_diverse"):
        lines.append("主题未均衡原因：可用候选主题集中，未找到更合适的不同主题文章")
    lines.extend(
        [
            f"邮件发送成功数量：{send_result.get('success_count', 0)}",
            f"邮件发送失败数量：{send_result.get('fail_count', 0)}",
        ]
    )
    return "\n".join(lines)


def _read_oss_bytes_from_path(oss_path: str) -> tuple[bytes | None, dict[str, Any]]:
    meta: dict[str, Any] = {"source": "oss", "path": oss_path, "ok": False}
    if not oss_path or not oss_path.startswith("oss://"):
        meta["error"] = "invalid oss path"
        return None, meta
    try:
        from history import oss_config, oss_headers, oss_ready, oss_url
    except Exception as exc:
        meta["error"] = f"OSS helpers unavailable: {exc}"
        return None, meta
    if not oss_ready():
        meta["error"] = "OSS config is incomplete."
        return None, meta
    bucket_and_key = oss_path[len("oss://"):]
    bucket, _, object_key = bucket_and_key.partition("/")
    if not bucket or not object_key:
        meta["error"] = "invalid oss path"
        return None, meta
    try:
        cfg = oss_config()
        cfg["bucket"] = bucket
        cfg["object_key"] = object_key
        response = requests.get(oss_url(cfg), headers=oss_headers("GET", cfg), timeout=20)
        if response.status_code == 404:
            meta["error"] = "weekly pdf not found on OSS"
            return None, meta
        response.raise_for_status()
    except Exception as exc:
        meta["error"] = str(exc)
        return None, meta
    meta["ok"] = True
    meta["bytes"] = len(response.content)
    return response.content, meta


def weekly_pdf_attachment_from_candidate(candidate: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    weekly = candidate.get("weekly_pdf") if isinstance(candidate.get("weekly_pdf"), dict) else {}
    filename = str(weekly.get("attachment_filename") or "gongkao-weekly.pdf")
    local_pdf_text = str(weekly.get("local_pdf") or "").strip()
    local_pdf = Path(local_pdf_text) if local_pdf_text else None
    if local_pdf and local_pdf.exists() and local_pdf.is_file():
        content = local_pdf.read_bytes()
        return {"filename": filename, "content": content, "content_type": "application/pdf"}, {
            "source": "local",
            "path": str(local_pdf),
            "ok": True,
            "bytes": len(content),
        }
    content, meta = _read_oss_bytes_from_path(str(weekly.get("oss_pdf_path") or ""))
    if content:
        return {"filename": filename, "content": content, "content_type": "application/pdf"}, meta
    return None, meta


def send_weekly_pdf_candidate(
    *,
    candidate: dict[str, Any],
    delivery_date: str,
    test_invocation: bool,
    load_meta: dict[str, Any],
    logger: RunLogger,
) -> dict[str, Any]:
    from email_sender import get_effective_recipients, send_email
    from harness_metrics import append_morning_metrics

    recipients, recipient_source = get_effective_recipients(test_mode=test_invocation)
    attachment, attachment_meta = weekly_pdf_attachment_from_candidate(candidate)
    logger.info(
        "weekly pdf candidate attachment status",
        **attachment_meta,
        attach_enabled=settings.weekly_pdf_attach,
        valid_recipient_count=len(recipients),
        recipient_source=recipient_source,
    )
    if settings.weekly_pdf_attach and not attachment:
        try:
            metrics_result = append_morning_metrics(
                delivery_date=delivery_date,
                test_invocation=test_invocation,
                status="blocked",
                reason="weekly_pdf_attachment_missing",
                candidate=candidate,
                load_meta=load_meta,
            )
            logger.info("harness metrics", **metrics_result)
        except Exception as exc:
            logger.info("harness metrics failed", error=str(exc))
        log_path = logger.save("latest_candidate_send.log")
        logger.dump_to_stdout()
        return {
            "status": "blocked",
            "reason": "weekly_pdf_attachment_missing",
            "delivery_date": delivery_date,
            "attachment_meta": attachment_meta,
            "log": str(log_path),
        }

    subject = str(candidate.get("subject") or f"{settings.subject_prefix}weekly review")
    plain_text = str(candidate.get("plain_text") or "")
    html_body = str(candidate.get("html_body") or "")
    attachments = [attachment] if (settings.weekly_pdf_attach and attachment) else []
    send_result: dict[str, Any] | None = None
    if settings.send_email:
        send_result = send_email(subject, plain_text, html_body, test_mode=test_invocation, attachments=attachments)
        logger.info("weekly pdf candidate email send result", subject=subject, attachment_count=len(attachments), **send_result)
    else:
        logger.info("weekly pdf candidate email skipped", reason="SEND_EMAIL=false", attachment_count=len(attachments))

    history_result = {
        "history_write_ok": False,
        "history_storage": settings.history_storage,
        "history_path": str(settings.history_path),
        "history_appended": 0,
        "history_skip_reason": "weekly review day; no daily article history is written.",
    }
    archive_result = {
        "daily_archive_saved": False,
        "daily_archive_reason": "weekly review day; no daily article archive is written.",
    }
    try:
        metrics_result = append_morning_metrics(
            delivery_date=delivery_date,
            test_invocation=test_invocation,
            status="ok",
            candidate=candidate,
            load_meta=load_meta,
            send_result=send_result,
            history_result=history_result,
            archive_result=archive_result,
        )
        logger.info("harness metrics", **metrics_result)
    except Exception as exc:
        logger.info("harness metrics failed", error=str(exc))
    weekly = candidate.get("weekly_pdf") if isinstance(candidate.get("weekly_pdf"), dict) else {}
    print(
        "\n".join(
            [
                "[weekly pdf send summary]",
                f"delivery_date: {delivery_date}",
                f"pdf_range: {weekly.get('start_date')} to {weekly.get('end_date')}",
                f"attachment_count: {len(attachments)}",
                f"success_count: {(send_result or {}).get('success_count', 0)}",
            ]
        )
    )
    log_path = logger.save("latest_candidate_send.log")
    logger.dump_to_stdout()
    return {
        "status": "ok",
        "mode": "weekly_pdf_morning_send",
        "delivery_date": delivery_date,
        "sent": bool(send_result and int(send_result.get("success_count", 0)) > 0),
        "send_result": send_result,
        "weekly_pdf": weekly,
        "attachment_meta": attachment_meta,
        "output_dir": str(settings.output_dir),
        "log": str(log_path),
    }


def evaluate_candidate_with_current_quality(
    candidate: dict[str, Any],
    delivery_date: str,
    *,
    test_invocation: bool = False,
) -> dict[str, Any]:
    from brief_schema import ensure_brief_schema
    from brief_quality import evaluate_brief_cleanliness
    from content_quality_reviewer import evaluate_content_quality, get_content_quality_model_plan
    from content_risk_quality import evaluate_content_risks
    from duplication_quality import evaluate_duplication
    from email_renderer import render_email_html, render_plain_text
    from expression_quality import evaluate_expression_quality
    from framework_quality import evaluate_framework_map
    from module_redundancy_quality import evaluate_module_redundancy
    from pre_send_cleanliness import pre_send_cleanliness_guard
    from question_quality import evaluate_daily_question
    from quick_reads_quality import evaluate_quick_reads
    from takeaway_quality import evaluate_takeaway

    brief = candidate.get("brief") if isinstance(candidate.get("brief"), dict) else {}
    if not brief:
        failed_gate = {
            "overall": "fail",
            "p0_count": 1,
            "p1_count": 0,
            "p2_count": 0,
            "p0_issues": [{"module": "candidate", "code": "missing_brief", "message": "Candidate does not contain a valid brief object."}],
            "p1_issues": [],
            "p2_issues": [],
        }
        return {"quality_gate": failed_gate, "quality": {"final": {}}, "brief": {}, "plain_text": "", "html_body": "", "subject": f"公考晨读 {delivery_date}"}

    brief, schema_warnings = ensure_brief_schema(brief, delivery_date)
    subject = brief.get("email_subject") or f"公考晨读 {delivery_date}"
    if not str(subject).startswith(settings.subject_prefix):
        subject = f"{settings.subject_prefix}{subject}"

    plain_text = render_plain_text(brief)
    html_body = render_email_html(brief)
    guarded, cleanliness_quality = pre_send_cleanliness_guard(
        {"brief": brief, "subject": str(subject), "plain_text": plain_text, "html_body": html_body, "quality": {}}
    )
    brief = guarded.get("brief") if isinstance(guarded.get("brief"), dict) else brief
    subject = str(guarded.get("subject") or subject)
    plain_text = str(guarded.get("plain_text") or plain_text)
    html_body = str(guarded.get("html_body") or html_body)
    question_quality = evaluate_daily_question(brief)
    framework_quality = evaluate_framework_map(brief)
    takeaway_quality = evaluate_takeaway(brief)
    brief_quality = evaluate_brief_cleanliness(brief, plain_text, html_body)
    quick_reads_quality = evaluate_quick_reads(brief)
    duplication_quality = evaluate_duplication(brief)
    expression_quality = evaluate_expression_quality(brief)
    module_redundancy_quality = evaluate_module_redundancy(brief)
    content_risk_quality = evaluate_content_risks(brief, plain_text, html_body)
    selection_quality = evaluate_selection_quality(brief)
    content_quality = evaluate_content_quality(brief, plain_text, html_body, test_mode=test_invocation)
    quality_gate = build_quality_gate(
        question_quality,
        framework_quality,
        takeaway_quality,
        brief_quality,
        quick_reads_quality,
        duplication_quality,
        expression_quality,
        module_redundancy_quality,
        content_risk_quality,
        selection_quality,
        content_quality,
        cleanliness_quality,
    )
    return {
        "brief": brief,
        "plain_text": plain_text,
        "html_body": html_body,
        "subject": str(subject),
        "schema_warnings": schema_warnings,
        "quality_gate": quality_gate,
        "quality": {
            "final": {
                "daily_question": question_quality,
                "framework_map": framework_quality,
                "today_takeaway": takeaway_quality,
                "brief_cleanliness": brief_quality,
                "quick_reads": quick_reads_quality,
                "duplication": duplication_quality,
                "expression_quality": expression_quality,
                "module_redundancy": module_redundancy_quality,
                "content_risk": content_risk_quality,
                "selection": selection_quality,
                "content_quality": content_quality,
                "cleanliness": cleanliness_quality,
            }
        },
    }


def send_saved_candidate(event: Any | None = None) -> dict[str, Any]:
    from candidate_store import load_candidate
    from daily_archive import archive_daily_content
    from email_sender import get_effective_recipients, send_email
    from harness_metrics import append_morning_metrics
    from history import append_records

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(settings.output_dir)
    payload = normalize_event(event)
    test_invocation = is_test_invocation(payload)
    delivery_date = resolve_delivery_date(payload)
    candidate, load_meta = load_candidate(delivery_date)
    logger.info(
        "candidate send started",
        run_mode=settings.run_mode,
        delivery_date=delivery_date,
        test_invocation=test_invocation,
        event=payload,
        **load_meta,
    )
    if not candidate:
        logger.info("candidate send blocked", reason="candidate_missing", delivery_date=delivery_date)
        try:
            metrics_result = append_morning_metrics(
                delivery_date=delivery_date,
                test_invocation=test_invocation,
                status="blocked",
                reason="candidate_missing",
                load_meta=load_meta,
            )
            logger.info("harness metrics", **metrics_result)
        except Exception as exc:
            logger.info("harness metrics failed", error=str(exc))
        log_path = logger.save("latest_candidate_send.log")
        logger.dump_to_stdout()
        return {"status": "blocked", "reason": "candidate_missing", "delivery_date": delivery_date, "log": str(log_path)}

    candidate_date = str(candidate.get("delivery_date") or "")
    quality_gate = candidate.get("quality_gate") if isinstance(candidate.get("quality_gate"), dict) else {}
    if candidate_date != delivery_date:
        logger.info("candidate send blocked", reason="candidate_date_mismatch", candidate_date=candidate_date, delivery_date=delivery_date)
        try:
            metrics_result = append_morning_metrics(
                delivery_date=delivery_date,
                test_invocation=test_invocation,
                status="blocked",
                reason="candidate_date_mismatch",
                candidate=candidate,
                load_meta=load_meta,
            )
            logger.info("harness metrics", **metrics_result)
        except Exception as exc:
            logger.info("harness metrics failed", error=str(exc))
        log_path = logger.save("latest_candidate_send.log")
        logger.dump_to_stdout()
        return {"status": "blocked", "reason": "candidate_date_mismatch", "delivery_date": delivery_date, "candidate_date": candidate_date, "log": str(log_path)}

    if candidate.get("candidate_type") != "weekly_pdf":
        logger.info(
            "candidate send using stored quality gate",
            quality_gate=quality_gate,
            candidate_recheck_skipped=True,
            reason="trust_nightly_candidate_quality_gate",
        )
    if quality_gate.get("overall") != "ok":
        logger.info("candidate send blocked", reason="quality_gate_fail", quality_gate=quality_gate)
        try:
            metrics_result = append_morning_metrics(
                delivery_date=delivery_date,
                test_invocation=test_invocation,
                status="blocked",
                reason="quality_gate_fail",
                candidate=candidate,
                load_meta=load_meta,
            )
            logger.info("harness metrics", **metrics_result)
        except Exception as exc:
            logger.info("harness metrics failed", error=str(exc))
        log_path = logger.save("latest_candidate_send.log")
        logger.dump_to_stdout()
        return {"status": "blocked", "reason": "quality_gate_fail", "delivery_date": delivery_date, "quality_gate": quality_gate, "log": str(log_path)}

    if candidate.get("candidate_type") == "weekly_pdf":
        return send_weekly_pdf_candidate(
            candidate=candidate,
            delivery_date=delivery_date,
            test_invocation=test_invocation,
            load_meta=load_meta,
            logger=logger,
        )

    subject = str(candidate.get("subject") or f"公考晨读 {delivery_date}")
    plain_text = str(candidate.get("plain_text") or "")
    html_body = str(candidate.get("html_body") or "")
    brief = candidate.get("brief") if isinstance(candidate.get("brief"), dict) else {}
    final_selection = candidate.get("final_selection") if isinstance(candidate.get("final_selection"), dict) else summarize_final_selection(brief)
    article_stats = candidate.get("article_stats") if isinstance(candidate.get("article_stats"), dict) else {}
    recipients, recipient_source = get_effective_recipients(test_mode=test_invocation)
    logger.info("candidate recipient stats", valid_recipient_count=len(recipients), recipient_source=recipient_source, send_mode=settings.send_mode)

    send_result: dict[str, Any] | None = None
    if settings.send_email:
        send_result = send_email(subject, plain_text, html_body, test_mode=test_invocation)
        logger.info("candidate email send result", subject=subject, **send_result)
    else:
        logger.info("candidate email skipped", reason="SEND_EMAIL=false", valid_recipient_count=len(recipients), recipient_source=recipient_source)

    if test_invocation:
        history_result = {
            "history_write_ok": False,
            "history_storage": settings.history_storage,
            "history_path": str(settings.history_path),
            "history_appended": 0,
            "history_skip_reason": "candidate send test mode.",
        }
        archive_result = {
            "daily_archive_saved": False,
            "daily_archive_reason": "candidate send test mode.",
        }
    elif send_result and int(send_result.get("success_count", 0)) > 0:
        history_result = append_records(settings.history_path, build_history_records(brief, delivery_date))
        archive_result = archive_daily_content(
            delivery_date,
            brief,
            html_body,
            plain_text,
            subject,
            send_success_count=int(send_result.get("success_count", 0)),
        )
    else:
        history_result = {
            "history_write_ok": False,
            "history_storage": settings.history_storage,
            "history_path": str(settings.history_path),
            "history_appended": 0,
            "history_skip_reason": "candidate email not sent.",
        }
        archive_result = {
            "daily_archive_saved": False,
            "daily_archive_reason": "candidate email not sent.",
        }
    logger.info("candidate sent history updated", **history_result)
    logger.info("candidate daily archive", **archive_result)
    try:
        metrics_result = append_morning_metrics(
            delivery_date=delivery_date,
            test_invocation=test_invocation,
            status="ok",
            candidate=candidate,
            load_meta=load_meta,
            send_result=send_result,
            history_result=history_result,
            archive_result=archive_result,
        )
        logger.info("harness metrics", **metrics_result)
    except Exception as exc:
        logger.info("harness metrics failed", error=str(exc))
    run_summary = build_run_summary(article_stats, final_selection, history_result, send_result)
    logger.info("candidate run summary text", summary=run_summary)
    print(run_summary)
    log_path = logger.save("latest_candidate_send.log")
    logger.dump_to_stdout()
    return {
        "status": "ok",
        "mode": "morning_send",
        "delivery_date": delivery_date,
        "sent": bool(send_result and int(send_result.get("success_count", 0)) > 0),
        "send_result": send_result,
        "output_dir": str(settings.output_dir),
        "log": str(log_path),
    }


def build_weekly_pdf_candidate_message(weekly_pdf: dict[str, Any]) -> tuple[str, str]:
    from weekly_pdf_tracking import build_weekly_pdf_tracking_placeholder

    start_date = str(weekly_pdf.get("start_date") or "")
    end_date = str(weekly_pdf.get("end_date") or "")
    filename = str(weekly_pdf.get("attachment_filename") or "公考晨读周复盘资料包.pdf")
    pdf_url = str(weekly_pdf.get("oss_pdf_path") or weekly_pdf.get("pdf_url") or "")
    week_key = f"{start_date}_to_{end_date}"
    download_url = build_weekly_pdf_tracking_placeholder(pdf_url, week_key) if pdf_url else ""
    plain_text = "\n".join(
        [
            "本周 PDF 资料包已附上",
            "",
            "今天不推送新的精读文章和速读文章，只做本周复盘。",
            "",
            "这周怎么复习：",
            "1. 先看本周主题总览，快速回忆这周学过哪些公共治理场景；",
            "2. 再看每日复盘卡，重点看文章框架、考场迁移和今日一题；",
            "3. 最后看本周表达素材库，挑 2-3 句真正能写进申论或面试里的表达。",
            "",
            "想麻烦你回复一点反馈：",
            "这版 PDF 是按「周复盘资料包」的形式整理，不是简单把 6 封邮件拼在一起。你可以直接回复本邮件，不用写很多，随便说一两句都可以。",
            "- 这个 PDF 排版读起来是否舒服？",
            "- 每日复盘卡里，哪些部分最有用，哪些可以删减？",
            "- 「今日一题」保留参考答案，对你复习有没有帮助？",
            "- 你更希望周报完整一点，还是更短一点、只保留重点？",
            "",
            f"汇总范围：{start_date} 至 {end_date}",
            f"附件：{filename}",
            "如果你的邮箱不方便查看附件，请打开邮件 HTML 里的下载按钮。",
        ]
    )
    download_block = (
        f"""
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:16px;padding:20px 24px;margin-bottom:16px;">
      <div style="font-size:18px;font-weight:900;color:#165dff;margin-bottom:10px;">下载 PDF</div>
      <div style="font-size:15px;line-height:1.8;color:#334155;margin-bottom:14px;">如果邮箱附件打开不方便，可以点击下面按钮下载本周资料包。</div>
      <a href="{download_url}" style="display:inline-block;background:#165dff;color:#fff;text-decoration:none;padding:10px 16px;border-radius:10px;font-size:15px;font-weight:900;">下载本周 PDF</a>
    </div>
"""
        if download_url
        else ""
    )
    html_body = f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f6f8fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;color:#334155;">
  <div style="max-width:720px;margin:0 auto;padding:28px 14px;">
    <div style="background:linear-gradient(135deg,#1f66a6,#1f7fbd);color:#fff;border-radius:18px;padding:24px 26px;margin-bottom:16px;">
      <div style="font-size:13px;letter-spacing:2px;font-weight:900;opacity:.9;">WEEKLY REVIEW 周日复盘</div>
      <div style="font-size:30px;font-weight:900;line-height:1.35;margin-top:10px;">本周 PDF 资料包已附上</div>
      <div style="font-size:16px;line-height:1.75;margin-top:12px;opacity:.96;">今天不推送新的精读文章和速读文章，只做本周复盘。</div>
    </div>

    <div style="background:#fff;border:1px solid #dfe7f2;border-radius:16px;padding:22px 24px;margin-bottom:16px;">
      <div style="font-size:18px;font-weight:900;color:#165dff;margin-bottom:12px;">这周怎么复习</div>
      <div style="font-size:16px;line-height:1.9;">本周一到周六的晨读内容已经整理成 PDF 附件。建议今天不用追新内容，花 20-30 分钟把本周材料过一遍。</div>
      <ol style="font-size:16px;line-height:1.9;margin:16px 0 0;padding-left:24px;">
        <li>先看<b>本周主题总览</b>，快速回忆这周学过哪些公共治理场景；</li>
        <li>再看<b>每日复盘卡</b>，重点看文章框架、考场迁移和今日一题；</li>
        <li>最后看<b>本周表达素材库</b>，挑 2-3 句真正能写进申论或面试里的表达。</li>
      </ol>
    </div>

{download_block}

    <div style="background:#fffdf6;border:1px solid #f8dba5;border-radius:16px;padding:22px 24px;margin-bottom:16px;">
      <div style="font-size:18px;font-weight:900;color:#b45309;margin-bottom:12px;">想麻烦你回复一点反馈</div>
      <div style="font-size:16px;line-height:1.9;">这版 PDF 是我们按「周复盘资料包」的形式整理，不是简单把 6 封邮件拼在一起。你可以直接回复本邮件，不用写很多，随便说一两句都可以。</div>
      <ul style="font-size:16px;line-height:1.9;margin:14px 0 0;padding-left:22px;">
        <li>这个 PDF 排版读起来是否舒服？</li>
        <li>每日复盘卡里，哪些部分最有用，哪些可以删减？</li>
        <li>「今日一题」保留参考答案，对你复习有没有帮助？</li>
        <li>你更希望周报完整一点，还是更短一点、只保留重点？</li>
      </ul>
      <div style="font-size:16px;line-height:1.9;margin-top:14px;">你的反馈会直接用于下周版本优化。谢谢你参与内测。</div>
    </div>

    <div style="background:#fff;border:1px solid #dfe7f2;border-radius:16px;padding:16px 22px;color:#64748b;font-size:15px;line-height:1.8;">
      <div>汇总范围：{start_date} 至 {end_date}</div>
      <div>附件：{filename}</div>
    </div>
  </div>
</body>
</html>"""
    return plain_text, html_body


def generate_weekly_pdf_candidate(event: Any | None = None) -> dict[str, Any]:
    from candidate_store import save_candidate
    from weekly_report import build_weekly_assets

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(settings.output_dir)
    payload = normalize_event(event)
    delivery_date = resolve_delivery_date(payload, nightly_candidate=True)
    weekly_event = dict(payload)
    for key in ("delivery_date", "candidate_date", "date"):
        weekly_event.pop(key, None)
    weekly_event.setdefault("end_date", dt.datetime.now(TZ).date().isoformat())
    assets = build_weekly_assets(weekly_event)
    subject = f"{settings.subject_prefix}本周晨读完整汇编｜{assets['start_date']}至{assets['end_date']}"
    quality_gate = {"overall": "ok", "p0_count": 0, "p0_issues": []}
    quality = {
        "final": {
            "weekly_pdf": {
                "ok": True,
                "status": "ok",
                "score": 100,
                "issues": [],
                "archives_loaded": assets.get("archives_loaded"),
                "misses": assets.get("misses") or [],
                "pdf_engine": assets.get("pdf_engine"),
            }
        },
        "gate": quality_gate,
    }
    weekly_pdf = {
        "start_date": assets.get("start_date"),
        "end_date": assets.get("end_date"),
        "days_requested": assets.get("days_requested"),
        "archives_loaded": assets.get("archives_loaded"),
        "misses": assets.get("misses") or [],
        "local_pdf": assets.get("local_pdf"),
        "local_md": assets.get("local_md"),
        "local_html": assets.get("local_html"),
        "oss_pdf_path": ((assets.get("oss_upload") or {}).get("pdf") or {}).get("oss_path"),
        "attachment_filename": (assets.get("attachment") or {}).get("filename") or "gongkao-weekly.pdf",
        "pdf_engine": assets.get("pdf_engine"),
        "typst_meta": assets.get("typst_meta"),
    }
    plain_text, html_body = build_weekly_pdf_candidate_message(weekly_pdf)
    candidate_payload = {
        "schema_version": 1,
        "candidate_type": "weekly_pdf",
        "generated_at": dt.datetime.now(TZ).isoformat(),
        "delivery_date": delivery_date,
        "subject": subject,
        "brief": {},
        "plain_text": plain_text,
        "html_body": html_body,
        "quality": quality,
        "quality_gate": quality_gate,
        "weekly_pdf": weekly_pdf,
        "article_stats": {
            "weekly_pdf_only": True,
            "daily_article_generation_skipped": True,
            "history_read_ok": True,
        },
        "final_selection": {},
    }
    candidate_save_result = save_candidate(candidate_payload)
    logger.info(
        "weekly pdf candidate saved",
        delivery_date=delivery_date,
        weekly_end_date=assets.get("end_date"),
        archives_loaded=assets.get("archives_loaded"),
        local_pdf=assets.get("local_pdf"),
        **candidate_save_result,
    )
    log_path = logger.save("latest_weekly_pdf_candidate.log")
    logger.dump_to_stdout()
    return {
        "status": "ok",
        "mode": "weekly_pdf_candidate",
        "delivery_date": delivery_date,
        "weekly_pdf": weekly_pdf,
        "candidate_save_result": candidate_save_result,
        "log": str(log_path),
    }


def run_daily_brief(event: Any | None = None, context: Any | None = None) -> dict[str, Any]:
    if is_weekly_pdf_candidate_invocation(event):
        return generate_weekly_pdf_candidate(event)
    if is_morning_candidate_send_invocation(event):
        return send_saved_candidate(event)

    from brief_schema import ensure_brief_schema
    from admin_report import build_quality_card_markdown, send_admin_quality_report
    from candidate_store import build_candidate_payload, save_candidate
    from content_risk_quality import evaluate_content_risks
    from content_issue_rewriter import rewrite_content_issues
    from content_quality_reviewer import evaluate_content_quality, get_content_quality_model_plan
    from daily_archive import archive_daily_content, is_official_morning_run
    from email_renderer import render_email_html, render_plain_text
    from email_sender import get_effective_recipients, send_email
    from fetch_articles import get_candidate_articles_with_stats
    from duplication_quality import evaluate_duplication
    from expression_quality import evaluate_expression_quality
    from framework_quality import evaluate_framework_map
    from harness_audit import build_rewrite_comparison, clone_jsonable, save_blocked_run
    from harness_metrics import append_nightly_metrics
    from history import append_records
    from llm_client import (
        clear_llm_trace_hook,
        generate_brief,
        get_stage_model_plan,
        rewrite_failed_modules_once,
        set_llm_trace_hook,
    )
    from minor_auto_fixer import apply_minor_auto_fixes, merge_minor_fixes_into_rewrite
    from module_redundancy_quality import evaluate_module_redundancy
    from pre_send_cleanliness import pre_send_cleanliness_guard
    from question_quality import evaluate_daily_question
    from quick_reads_quality import evaluate_quick_reads
    from takeaway_quality import evaluate_takeaway
    from brief_quality import evaluate_brief_cleanliness
    from url_checker import annotate_brief_urls
    from weekly_report import build_weekly_assets

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(settings.output_dir)
    logger.bind(**build_log_context(event, context))
    test_invocation = is_test_invocation(event)
    candidate_invocation = is_nightly_candidate_invocation(event)
    today = resolve_delivery_date(event, nightly_candidate=candidate_invocation)
    if candidate_invocation and should_generate_weekly_pdf_candidate_today(event, today):
        weekly_event = normalize_event(event)
        weekly_event["delivery_date"] = today
        return generate_weekly_pdf_candidate(weekly_event)
    llm_trace_events: list[dict[str, Any]] = []

    def _llm_trace_hook(entry: dict[str, Any]) -> None:
        llm_trace_events.append(dict(entry))
        logger.info("llm trace", **entry)

    set_llm_trace_hook(_llm_trace_hook)
    logger.info(
        "run started",
        run_mode=settings.run_mode,
        mode=event_mode(event),
        today=today,
        test_invocation=test_invocation,
        candidate_invocation=candidate_invocation,
        event=normalize_event(event),
    )

    articles, article_stats = get_candidate_articles_with_stats()
    if not articles:
        raise RuntimeError("No candidate articles found.")
    logger.info("source fetch diagnostics", source_fetch_status=compact_source_fetch_status(article_stats.get("source_fetch_status", {})))
    logger.info("article selection stats compact", **compact_article_stats(article_stats))
    logger.info(
        "candidate articles selected",
        count=len(articles),
        titles=[a.title for a in articles],
        published_at=[a.published_at for a in articles],
    )

    stage_model_plan = get_stage_model_plan(test_invocation)
    logger.info(
        "llm selection",
        test_invocation=test_invocation,
        llm_two_stage_enabled=settings.llm_two_stage_enabled,
        selection_models=stage_model_plan.get("selection", []),
        writing_models=stage_model_plan.get("writing", []),
        prod_selection_llm_model=settings.selection_llm_model or settings.llm_model,
        prod_writing_llm_model=settings.writing_llm_model or settings.llm_model,
        test_selection_llm_model=settings.test_selection_llm_model or settings.test_llm_model or "",
        test_writing_llm_model=settings.test_writing_llm_model or settings.test_llm_model or "",
        featured_article_max_chars=settings.featured_article_max_chars,
        quick_read_article_max_chars=settings.quick_read_article_max_chars,
    )
    logger.info(
        "content quality model plan",
        test_invocation=test_invocation,
        content_quality_models=get_content_quality_model_plan(test_invocation),
        content_quality_timeout=settings.content_quality_timeout,
    )
    raw_brief = generate_brief(articles, today, test_mode=test_invocation, selection_context=article_stats)
    logger.info("llm two-stage diagnostics", diagnostics=raw_brief.get("_llm_two_stage", {}) if isinstance(raw_brief, dict) else {})
    brief, warnings = ensure_brief_schema(raw_brief, today)
    question_bank_meta = brief.get("_question_bank") if isinstance(brief.get("_question_bank"), dict) else {}
    logger.info(
        "question bank context",
        question_bank_enabled=question_bank_meta.get("question_bank_enabled"),
        question_bank_used=bool(question_bank_meta.get("question_bank_refs")),
        question_bank_source=question_bank_meta.get("question_bank_source"),
        question_bank_count=question_bank_meta.get("question_bank_count"),
        question_bank_warnings=question_bank_meta.get("question_bank_warnings") or [],
        question_bank_refs=question_bank_meta.get("question_bank_refs") or [],
    )
    initial_brief = clone_jsonable(brief)
    logger.info("brief generated", warnings=warnings)
    initial_selection_quality = evaluate_selection_quality(brief)
    logger.info("selection quality", **initial_selection_quality)
    initial_question_quality = evaluate_daily_question(brief)
    logger.info("today question quality", **initial_question_quality)
    initial_framework_quality = evaluate_framework_map(brief)
    logger.info("framework map quality", **initial_framework_quality)
    initial_takeaway_quality = evaluate_takeaway(brief)
    logger.info("today takeaway quality", **initial_takeaway_quality)
    initial_quick_reads_quality = evaluate_quick_reads(brief)
    logger.info("quick reads quality", **initial_quick_reads_quality)
    initial_duplication_quality = evaluate_duplication(brief)
    logger.info("duplication quality", **initial_duplication_quality)
    initial_expression_quality = evaluate_expression_quality(brief)
    logger.info("expression quality", **initial_expression_quality)
    initial_module_redundancy_quality = evaluate_module_redundancy(brief)
    logger.info("module redundancy quality", **initial_module_redundancy_quality)
    initial_content_risk_quality = evaluate_content_risks(brief)
    logger.info("content risk quality", **initial_content_risk_quality)
    rewrite_result = None
    p0_repair_result = None
    content_issue_rewrite_result = None
    minor_fix_result = None
    question_quality = initial_question_quality
    framework_quality = initial_framework_quality
    takeaway_quality = initial_takeaway_quality
    quick_reads_quality = initial_quick_reads_quality
    duplication_quality = initial_duplication_quality
    expression_quality = initial_expression_quality
    module_redundancy_quality = initial_module_redundancy_quality
    content_risk_quality = initial_content_risk_quality
    selection_quality = initial_selection_quality
    if settings.quality_rewrite_enabled and settings.quality_rewrite_max_rounds > 0 and (
        not question_quality.get("ok")
        or not framework_quality.get("ok")
        or not takeaway_quality.get("ok")
        or not quick_reads_quality.get("ok")
    ):
        try:
            rewrite_result = rewrite_failed_modules_once(
                brief,
                articles,
                question_quality,
                framework_quality,
                takeaway_quality,
                quick_reads_quality,
                test_mode=test_invocation,
            )
            if rewrite_result.get("rewritten_modules"):
                logger.info("quality rewrite triggered", rewritten_modules=rewrite_result.get("rewritten_modules"), details=rewrite_result.get("details", {}))
                brief, rewrite_warnings = ensure_brief_schema(rewrite_result.get("brief") or brief, today)
                if rewrite_warnings:
                    logger.info("quality rewrite warnings", warnings=rewrite_warnings)
                question_quality = evaluate_daily_question(brief)
                logger.info("today question quality after rewrite", **question_quality)
                framework_quality = evaluate_framework_map(brief)
                logger.info("framework map quality after rewrite", **framework_quality)
                takeaway_quality = evaluate_takeaway(brief)
                logger.info("today takeaway quality after rewrite", **takeaway_quality)
                quick_reads_quality = evaluate_quick_reads(brief)
                logger.info("quick reads quality after rewrite", **quick_reads_quality)
                duplication_quality = evaluate_duplication(brief)
                logger.info("duplication quality after rewrite", **duplication_quality)
                expression_quality = evaluate_expression_quality(brief)
                logger.info("expression quality after rewrite", **expression_quality)
                module_redundancy_quality = evaluate_module_redundancy(brief)
                logger.info("module redundancy quality after rewrite", **module_redundancy_quality)
                content_risk_quality = evaluate_content_risks(brief)
                logger.info("content risk quality after rewrite", **content_risk_quality)
        except Exception as exc:
            logger.info("quality rewrite failed", error=str(exc))
            rewrite_result = {"error": str(exc), "rewritten_modules": []}
    brief, url_checks = annotate_brief_urls(brief)
    logger.info("source url checks", checks=url_checks)
    final_selection = summarize_final_selection(brief)
    logger.info("final article roles", **final_selection)
    theme_changes = detect_theme_changes(articles, brief)
    logger.info("theme comparison", theme_changes=theme_changes)
    selection_quality = evaluate_selection_quality(brief)
    logger.info("selection quality final", **selection_quality)

    subject = brief.get("email_subject") or f"公考晨读 {today}"
    if not str(subject).startswith(settings.subject_prefix):
        subject = f"{settings.subject_prefix}{subject}"

    plain_text = render_plain_text(brief)
    html_body = render_email_html(brief)
    brief_quality = evaluate_brief_cleanliness(brief, plain_text, html_body)
    logger.info("brief cleanliness quality", **brief_quality)
    quick_reads_quality = evaluate_quick_reads(brief)
    logger.info("quick reads quality final", **quick_reads_quality)
    duplication_quality = evaluate_duplication(brief)
    logger.info("duplication quality final", **duplication_quality)
    expression_quality = evaluate_expression_quality(brief)
    logger.info("expression quality final", **expression_quality)
    module_redundancy_quality = evaluate_module_redundancy(brief)
    logger.info("module redundancy quality final", **module_redundancy_quality)
    content_risk_quality = evaluate_content_risks(brief, plain_text, html_body)
    logger.info("content risk quality final", **content_risk_quality)
    if settings.quality_rewrite_enabled:
        try:
            minor_fix_result = apply_minor_auto_fixes(brief, [content_risk_quality])
            if minor_fix_result.get("changed"):
                logger.info("minor auto fixes applied", fixes=minor_fix_result.get("fixes", []), changed_modules=minor_fix_result.get("changed_modules", []))
                brief, minor_fix_warnings = ensure_brief_schema(minor_fix_result.get("brief") or brief, today)
                if minor_fix_warnings:
                    logger.info("minor auto fix warnings", warnings=minor_fix_warnings)
                brief, url_checks = annotate_brief_urls(brief)
                logger.info("source url checks after minor auto fixes", checks=url_checks)
                final_selection = summarize_final_selection(brief)
                logger.info("final article roles after minor auto fixes", **final_selection)
                theme_changes = detect_theme_changes(articles, brief)
                logger.info("theme comparison after minor auto fixes", theme_changes=theme_changes)
                selection_quality = evaluate_selection_quality(brief)
                logger.info("selection quality after minor auto fixes", **selection_quality)
                subject = brief.get("email_subject") or f"公考晨读 {today}"
                if not str(subject).startswith(settings.subject_prefix):
                    subject = f"{settings.subject_prefix}{subject}"
                question_quality = evaluate_daily_question(brief)
                logger.info("today question quality after minor auto fixes", **question_quality)
                framework_quality = evaluate_framework_map(brief)
                logger.info("framework map quality after minor auto fixes", **framework_quality)
                takeaway_quality = evaluate_takeaway(brief)
                logger.info("today takeaway quality after minor auto fixes", **takeaway_quality)
                plain_text = render_plain_text(brief)
                html_body = render_email_html(brief)
                brief_quality = evaluate_brief_cleanliness(brief, plain_text, html_body)
                logger.info("brief cleanliness quality after minor auto fixes", **brief_quality)
                quick_reads_quality = evaluate_quick_reads(brief)
                logger.info("quick reads quality after minor auto fixes", **quick_reads_quality)
                duplication_quality = evaluate_duplication(brief)
                logger.info("duplication quality after minor auto fixes", **duplication_quality)
                expression_quality = evaluate_expression_quality(brief)
                logger.info("expression quality after minor auto fixes", **expression_quality)
                module_redundancy_quality = evaluate_module_redundancy(brief)
                logger.info("module redundancy quality after minor auto fixes", **module_redundancy_quality)
                content_risk_quality = evaluate_content_risks(brief, plain_text, html_body)
                logger.info("content risk quality after minor auto fixes", **content_risk_quality)
        except Exception as exc:
            logger.info("minor auto fixes failed", error=str(exc))
            minor_fix_result = {"error": str(exc), "changed": False, "fixes": []}
    content_quality = evaluate_content_quality(brief, plain_text, html_body, test_mode=test_invocation)
    logger.info("content quality final", **content_quality)
    if settings.quality_rewrite_enabled:
        try:
            content_minor_fix = apply_minor_auto_fixes(brief, [content_quality])
            if content_minor_fix.get("changed"):
                logger.info("content quality minor fixes applied", fixes=content_minor_fix.get("fixes", []), changed_modules=content_minor_fix.get("changed_modules", []))
                if isinstance(minor_fix_result, dict):
                    minor_fix_result["changed"] = bool(minor_fix_result.get("changed") or content_minor_fix.get("changed"))
                    minor_fix_result["fixes"] = list(minor_fix_result.get("fixes") or []) + list(content_minor_fix.get("fixes") or [])
                    minor_fix_result["changed_modules"] = list(dict.fromkeys(list(minor_fix_result.get("changed_modules") or []) + list(content_minor_fix.get("changed_modules") or [])))
                else:
                    minor_fix_result = content_minor_fix
                brief, content_minor_warnings = ensure_brief_schema(content_minor_fix.get("brief") or brief, today)
                if content_minor_warnings:
                    logger.info("content quality minor fix warnings", warnings=content_minor_warnings)
                brief, url_checks = annotate_brief_urls(brief)
                logger.info("source url checks after content quality minor fixes", checks=url_checks)
                final_selection = summarize_final_selection(brief)
                logger.info("final article roles after content quality minor fixes", **final_selection)
                theme_changes = detect_theme_changes(articles, brief)
                logger.info("theme comparison after content quality minor fixes", theme_changes=theme_changes)
                selection_quality = evaluate_selection_quality(brief)
                logger.info("selection quality after content quality minor fixes", **selection_quality)
                subject = brief.get("email_subject") or f"公考晨读 {today}"
                if not str(subject).startswith(settings.subject_prefix):
                    subject = f"{settings.subject_prefix}{subject}"
                plain_text = render_plain_text(brief)
                html_body = render_email_html(brief)
                question_quality = evaluate_daily_question(brief)
                framework_quality = evaluate_framework_map(brief)
                takeaway_quality = evaluate_takeaway(brief)
                brief_quality = evaluate_brief_cleanliness(brief, plain_text, html_body)
                quick_reads_quality = evaluate_quick_reads(brief)
                duplication_quality = evaluate_duplication(brief)
                expression_quality = evaluate_expression_quality(brief)
                module_redundancy_quality = evaluate_module_redundancy(brief)
                content_risk_quality = evaluate_content_risks(brief, plain_text, html_body)
                content_quality = evaluate_content_quality(brief, plain_text, html_body, test_mode=test_invocation)
                logger.info("content quality after content minor fixes", **content_quality)

            content_issue_rewrite_result = rewrite_content_issues(brief, content_quality, test_mode=test_invocation, today=today)
            if content_issue_rewrite_result.get("changed"):
                before_content_issue_rewrite = {
                    "brief": brief,
                    "subject": subject,
                    "plain_text": plain_text,
                    "html_body": html_body,
                    "question_quality": question_quality,
                    "framework_quality": framework_quality,
                    "takeaway_quality": takeaway_quality,
                    "brief_quality": brief_quality,
                    "quick_reads_quality": quick_reads_quality,
                    "duplication_quality": duplication_quality,
                    "expression_quality": expression_quality,
                    "module_redundancy_quality": module_redundancy_quality,
                    "content_risk_quality": content_risk_quality,
                    "selection_quality": selection_quality,
                    "content_quality": content_quality,
                }
                before_content_score = int(content_quality.get("score") or 0)
                logger.info(
                    "content issue rewrite applied",
                    rewritten_modules=content_issue_rewrite_result.get("rewritten_modules", []),
                    changed_fields=content_issue_rewrite_result.get("changed_fields", []),
                )
                brief, content_rewrite_warnings = ensure_brief_schema(content_issue_rewrite_result.get("brief") or brief, today)
                if content_rewrite_warnings:
                    logger.info("content issue rewrite warnings", warnings=content_rewrite_warnings)
                brief, url_checks = annotate_brief_urls(brief)
                logger.info("source url checks after content issue rewrite", checks=url_checks)
                final_selection = summarize_final_selection(brief)
                logger.info("final article roles after content issue rewrite", **final_selection)
                theme_changes = detect_theme_changes(articles, brief)
                logger.info("theme comparison after content issue rewrite", theme_changes=theme_changes)
                selection_quality = evaluate_selection_quality(brief)
                logger.info("selection quality after content issue rewrite", **selection_quality)
                subject = brief.get("email_subject") or f"公考晨读 {today}"
                if not str(subject).startswith(settings.subject_prefix):
                    subject = f"{settings.subject_prefix}{subject}"
                plain_text = render_plain_text(brief)
                html_body = render_email_html(brief)
                question_quality = evaluate_daily_question(brief)
                logger.info("today question quality after content issue rewrite", **question_quality)
                framework_quality = evaluate_framework_map(brief)
                logger.info("framework map quality after content issue rewrite", **framework_quality)
                takeaway_quality = evaluate_takeaway(brief)
                logger.info("today takeaway quality after content issue rewrite", **takeaway_quality)
                brief_quality = evaluate_brief_cleanliness(brief, plain_text, html_body)
                logger.info("brief cleanliness quality after content issue rewrite", **brief_quality)
                quick_reads_quality = evaluate_quick_reads(brief)
                logger.info("quick reads quality after content issue rewrite", **quick_reads_quality)
                duplication_quality = evaluate_duplication(brief)
                logger.info("duplication quality after content issue rewrite", **duplication_quality)
                expression_quality = evaluate_expression_quality(brief)
                logger.info("expression quality after content issue rewrite", **expression_quality)
                module_redundancy_quality = evaluate_module_redundancy(brief)
                logger.info("module redundancy quality after content issue rewrite", **module_redundancy_quality)
                content_risk_quality = evaluate_content_risks(brief, plain_text, html_body)
                logger.info("content risk quality after content issue rewrite", **content_risk_quality)
                content_quality = evaluate_content_quality(brief, plain_text, html_body, test_mode=test_invocation)
                logger.info("content quality after content issue rewrite", **content_quality)
                after_content_score = int(content_quality.get("score") or 0)
                if after_content_score + 2 < before_content_score:
                    logger.info(
                        "content issue rewrite rolled back",
                        before_score=before_content_score,
                        after_score=after_content_score,
                        changed_fields=content_issue_rewrite_result.get("changed_fields", []),
                    )
                    brief = before_content_issue_rewrite["brief"]
                    subject = before_content_issue_rewrite["subject"]
                    plain_text = before_content_issue_rewrite["plain_text"]
                    html_body = before_content_issue_rewrite["html_body"]
                    question_quality = before_content_issue_rewrite["question_quality"]
                    framework_quality = before_content_issue_rewrite["framework_quality"]
                    takeaway_quality = before_content_issue_rewrite["takeaway_quality"]
                    brief_quality = before_content_issue_rewrite["brief_quality"]
                    quick_reads_quality = before_content_issue_rewrite["quick_reads_quality"]
                    duplication_quality = before_content_issue_rewrite["duplication_quality"]
                    expression_quality = before_content_issue_rewrite["expression_quality"]
                    module_redundancy_quality = before_content_issue_rewrite["module_redundancy_quality"]
                    content_risk_quality = before_content_issue_rewrite["content_risk_quality"]
                    selection_quality = before_content_issue_rewrite["selection_quality"]
                    content_quality = before_content_issue_rewrite["content_quality"]
                    content_issue_rewrite_result["rolled_back"] = True
                    content_issue_rewrite_result["changed"] = False
                    content_issue_rewrite_result["rewritten_modules"] = []
                    content_issue_rewrite_result["changed_modules"] = []
                    content_issue_rewrite_result["changed_fields"] = []
                    content_issue_rewrite_result["rewrites"] = []
                    content_issue_rewrite_result["details"] = {
                        **dict(content_issue_rewrite_result.get("details") or {}),
                        "rolled_back": True,
                        "content_issue_rewrites": [],
                    }
        except Exception as exc:
            logger.info("content issue rewrite failed", error=str(exc))
            content_issue_rewrite_result = {"error": str(exc), "rewritten_modules": []}
    guarded, cleanliness_quality = pre_send_cleanliness_guard(
        {"brief": brief, "subject": str(subject), "plain_text": plain_text, "html_body": html_body, "quality": {}}
    )
    brief = guarded.get("brief") if isinstance(guarded.get("brief"), dict) else brief
    subject = str(guarded.get("subject") or subject)
    plain_text = str(guarded.get("plain_text") or plain_text)
    html_body = str(guarded.get("html_body") or html_body)
    logger.info(
        "pre-send cleanliness guard",
        status=cleanliness_quality.get("status"),
        score=cleanliness_quality.get("score"),
        fix_count=len(cleanliness_quality.get("fixes") or []),
        unresolved_count=len(cleanliness_quality.get("unresolved_issues") or []),
    )
    question_quality = evaluate_daily_question(brief)
    framework_quality = evaluate_framework_map(brief)
    takeaway_quality = evaluate_takeaway(brief)
    brief_quality = evaluate_brief_cleanliness(brief, plain_text, html_body)
    quick_reads_quality = evaluate_quick_reads(brief)
    duplication_quality = evaluate_duplication(brief)
    expression_quality = evaluate_expression_quality(brief)
    module_redundancy_quality = evaluate_module_redundancy(brief)
    content_risk_quality = evaluate_content_risks(brief, plain_text, html_body)
    content_quality = evaluate_content_quality(brief, plain_text, html_body, test_mode=test_invocation)
    logger.info("content quality after pre-send cleanliness guard", **content_quality)
    quality_gate = build_quality_gate(
        question_quality,
        framework_quality,
        takeaway_quality,
        brief_quality,
        quick_reads_quality,
        duplication_quality,
        expression_quality,
        module_redundancy_quality,
        content_risk_quality,
        selection_quality,
        content_quality,
        cleanliness_quality,
    )
    logger.info("quality gate", **quality_gate, blocked=(not test_invocation) and quality_gate.get("overall") == "fail")
    if settings.quality_rewrite_enabled and quality_gate.get("overall") == "fail":
        try:
            p0_issues = quality_gate.get("p0_issues") or []
            p0_modules = {str(issue.get("module") or "") for issue in p0_issues if isinstance(issue, dict)}
            force_all_content_modules = bool({"brief_cleanliness", "duplication", "expression_quality", "module_redundancy", "pre_send_cleanliness"} & p0_modules)
            p0_question_quality = _quality_for_p0_repair(question_quality, "daily_question", p0_issues, force=force_all_content_modules)
            p0_framework_quality = _quality_for_p0_repair(framework_quality, "framework_map", p0_issues, force=force_all_content_modules)
            p0_takeaway_quality = _quality_for_p0_repair(takeaway_quality, "today_takeaway", p0_issues, force=force_all_content_modules)
            p0_quick_reads_quality = _quality_for_p0_repair(quick_reads_quality, "quick_reads", p0_issues, force=force_all_content_modules)
            p0_repair_result = rewrite_failed_modules_once(
                brief,
                articles,
                p0_question_quality,
                p0_framework_quality,
                p0_takeaway_quality,
                p0_quick_reads_quality,
                test_mode=test_invocation,
            )
            logger.info(
                "p0 repair attempted",
                p0_modules=sorted(p0_modules),
                rewritten_modules=p0_repair_result.get("rewritten_modules", []),
                details=p0_repair_result.get("details", {}),
            )
            if p0_repair_result.get("rewritten_modules"):
                brief, p0_repair_warnings = ensure_brief_schema(p0_repair_result.get("brief") or brief, today)
                if p0_repair_warnings:
                    logger.info("p0 repair warnings", warnings=p0_repair_warnings)
                brief, url_checks = annotate_brief_urls(brief)
                logger.info("source url checks after p0 repair", checks=url_checks)
                final_selection = summarize_final_selection(brief)
                logger.info("final article roles after p0 repair", **final_selection)
                theme_changes = detect_theme_changes(articles, brief)
                logger.info("theme comparison after p0 repair", theme_changes=theme_changes)
                selection_quality = evaluate_selection_quality(brief)
                logger.info("selection quality after p0 repair", **selection_quality)
                subject = brief.get("email_subject") or f"公考晨读 {today}"
                if not str(subject).startswith(settings.subject_prefix):
                    subject = f"{settings.subject_prefix}{subject}"
                question_quality = evaluate_daily_question(brief)
                logger.info("today question quality after p0 repair", **question_quality)
                framework_quality = evaluate_framework_map(brief)
                logger.info("framework map quality after p0 repair", **framework_quality)
                takeaway_quality = evaluate_takeaway(brief)
                logger.info("today takeaway quality after p0 repair", **takeaway_quality)
                plain_text = render_plain_text(brief)
                html_body = render_email_html(brief)
                brief_quality = evaluate_brief_cleanliness(brief, plain_text, html_body)
                logger.info("brief cleanliness quality after p0 repair", **brief_quality)
                quick_reads_quality = evaluate_quick_reads(brief)
                logger.info("quick reads quality after p0 repair", **quick_reads_quality)
                duplication_quality = evaluate_duplication(brief)
                logger.info("duplication quality after p0 repair", **duplication_quality)
                expression_quality = evaluate_expression_quality(brief)
                logger.info("expression quality after p0 repair", **expression_quality)
                module_redundancy_quality = evaluate_module_redundancy(brief)
                logger.info("module redundancy quality after p0 repair", **module_redundancy_quality)
                content_risk_quality = evaluate_content_risks(brief, plain_text, html_body)
                logger.info("content risk quality after p0 repair", **content_risk_quality)
                content_quality = evaluate_content_quality(brief, plain_text, html_body, test_mode=test_invocation)
                logger.info("content quality after p0 repair", **content_quality)
                guarded, cleanliness_quality = pre_send_cleanliness_guard(
                    {"brief": brief, "subject": str(subject), "plain_text": plain_text, "html_body": html_body, "quality": {}}
                )
                brief = guarded.get("brief") if isinstance(guarded.get("brief"), dict) else brief
                subject = str(guarded.get("subject") or subject)
                plain_text = str(guarded.get("plain_text") or plain_text)
                html_body = str(guarded.get("html_body") or html_body)
                logger.info(
                    "pre-send cleanliness guard after p0 repair",
                    status=cleanliness_quality.get("status"),
                    score=cleanliness_quality.get("score"),
                    fix_count=len(cleanliness_quality.get("fixes") or []),
                    unresolved_count=len(cleanliness_quality.get("unresolved_issues") or []),
                )
                question_quality = evaluate_daily_question(brief)
                framework_quality = evaluate_framework_map(brief)
                takeaway_quality = evaluate_takeaway(brief)
                brief_quality = evaluate_brief_cleanliness(brief, plain_text, html_body)
                quick_reads_quality = evaluate_quick_reads(brief)
                duplication_quality = evaluate_duplication(brief)
                expression_quality = evaluate_expression_quality(brief)
                module_redundancy_quality = evaluate_module_redundancy(brief)
                content_risk_quality = evaluate_content_risks(brief, plain_text, html_body)
                content_quality = evaluate_content_quality(brief, plain_text, html_body, test_mode=test_invocation)
                logger.info("content quality after pre-send cleanliness guard after p0 repair", **content_quality)
                quality_gate = build_quality_gate(
                    question_quality,
                    framework_quality,
                    takeaway_quality,
                    brief_quality,
                    quick_reads_quality,
                    duplication_quality,
                    expression_quality,
                    module_redundancy_quality,
                    content_risk_quality,
                    selection_quality,
                    content_quality,
                    cleanliness_quality,
                )
                logger.info("quality gate after p0 repair", **quality_gate, blocked=(not test_invocation) and quality_gate.get("overall") == "fail")
        except Exception as exc:
            logger.info("p0 repair failed", error=str(exc))
            p0_repair_result = {"error": str(exc), "rewritten_modules": []}
    rewrite_result = merge_rewrite_results(rewrite_result, content_issue_rewrite_result)
    rewrite_result = merge_rewrite_results(rewrite_result, p0_repair_result)
    rewrite_result = merge_minor_fixes_into_rewrite(rewrite_result, minor_fix_result)
    quality_blocked = (not test_invocation) and quality_gate.get("overall") == "fail"
    llm_trace_summary = summarize_llm_trace(llm_trace_events)
    logger.info("llm trace summary", summary=llm_trace_summary)
    recipients, recipient_source = get_effective_recipients(test_mode=test_invocation)
    logger.info(
        "recipient stats",
        valid_recipient_count=len(recipients),
        recipient_source=recipient_source,
        send_mode=settings.send_mode,
    )

    save_json(settings.output_dir / "latest_articles.json", [a.to_log_dict() for a in articles])
    save_json(settings.output_dir / "latest_brief.json", brief)
    quality_payload = {
        "initial": {
            "daily_question": initial_question_quality,
            "framework_map": initial_framework_quality,
            "today_takeaway": initial_takeaway_quality,
            "quick_reads": initial_quick_reads_quality,
            "duplication": initial_duplication_quality,
            "expression_quality": initial_expression_quality,
            "module_redundancy": initial_module_redundancy_quality,
            "content_risk": initial_content_risk_quality,
            "selection": initial_selection_quality,
        },
        "final": {
            "daily_question": question_quality,
            "framework_map": framework_quality,
            "today_takeaway": takeaway_quality,
            "brief_cleanliness": brief_quality,
            "quick_reads": quick_reads_quality,
            "duplication": duplication_quality,
            "expression_quality": expression_quality,
            "module_redundancy": module_redundancy_quality,
            "content_risk": content_risk_quality,
            "selection": selection_quality,
            "content_quality": content_quality,
            "cleanliness": cleanliness_quality,
        },
        "rewrite": rewrite_result,
        "minor_auto_fix": minor_fix_result,
        "gate": quality_gate,
        "question_bank": question_bank_meta,
    }
    rewrite_comparison = build_rewrite_comparison(initial_brief, brief, quality_payload)
    quality_payload["rewrite_comparison"] = rewrite_comparison
    save_json(settings.output_dir / "latest_quality.json", quality_payload)
    save_json(settings.output_dir / "latest_content_quality.json", content_quality)
    save_json(settings.output_dir / "latest_content_risk.json", content_risk_quality)
    (settings.output_dir / "latest_email.html").write_text(html_body, encoding="utf-8")
    quality_card_markdown = build_quality_card_markdown({
        "delivery_date": today,
        "subject": subject,
        "quality": quality_payload,
        "quality_gate": quality_gate,
    })
    (settings.output_dir / "latest_quality_card.md").write_text(quality_card_markdown, encoding="utf-8")
    candidate_save_result: dict[str, Any] | None = None
    admin_report_result: dict[str, Any] | None = None
    blocked_archive_result: dict[str, Any] | None = None
    if candidate_invocation:
        candidate_payload = build_candidate_payload(
            delivery_date=today,
            subject=subject,
            brief=brief,
            plain_text=plain_text,
            html_body=html_body,
            quality=quality_payload,
            quality_gate=quality_gate,
            article_stats=compact_article_stats(article_stats),
            final_selection=final_selection,
        )
        candidate_payload["rewrite_comparison"] = rewrite_comparison
        candidate_payload["quality_card_markdown"] = quality_card_markdown
        candidate_payload["question_bank_used"] = bool(question_bank_meta.get("question_bank_refs"))
        candidate_payload["question_bank_source"] = question_bank_meta.get("question_bank_source")
        candidate_payload["question_bank_refs"] = question_bank_meta.get("question_bank_refs") or []
        candidate_payload["question_bank_warnings"] = question_bank_meta.get("question_bank_warnings") or []
        candidate_save_result = save_candidate(candidate_payload)
        logger.info("candidate saved", **candidate_save_result, quality_gate=quality_gate)
        if quality_gate.get("overall") == "fail":
            blocked_archive_result = save_blocked_run(
                delivery_date=today,
                articles=articles,
                initial_brief=initial_brief,
                final_brief=brief,
                quality_payload=quality_payload,
                html_body=html_body,
                plain_text=plain_text,
                subject=subject,
                final_selection=final_selection,
                candidate_save_result=candidate_save_result,
                rewrite_comparison=rewrite_comparison,
            )
            candidate_payload["blocked_archive"] = blocked_archive_result
            logger.info("blocked run archived", **blocked_archive_result)
            candidate_save_result = save_candidate(candidate_payload)
            logger.info("candidate saved with blocked archive", **candidate_save_result)
        try:
            admin_report_result = send_admin_quality_report(candidate_payload, candidate_save_result)
        except Exception as exc:
            admin_report_result = {"admin_report_sent": False, "admin_report_error": str(exc)}
        logger.info(
            "admin quality report",
            delivery_date=today,
            subject=subject,
            quality_gate_overall=quality_gate.get("overall"),
            llm_trace_summary=llm_trace_summary,
            **admin_report_result,
        )
    weekly_attachments: list[dict[str, Any]] = []
    weekly_attach_result: dict[str, Any] | None = None
    should_attach_weekly, weekly_attach_meta = should_attach_weekly_pdf_today(event, today, test_invocation=test_invocation)
    if should_attach_weekly and not quality_blocked and not candidate_invocation:
        try:
            weekly_event = normalize_event(event)
            weekly_event.setdefault("end_date", today)
            weekly_attach_result = build_weekly_assets(weekly_event)
            weekly_attachments.append(weekly_attach_result["attachment"])
            # 在晨读邮件顶部加一句附件提醒，避免用户看到附件但不知道用途。
            html_body = html_body.replace(
                "</body>",
                '<div style="max-width:760px;margin:12px auto 0;padding:12px 14px;background:#fff7ed;border:1px solid #fed7aa;border-radius:14px;font-size:13px;line-height:1.7;color:#9a3412;">📎 本周复盘 PDF 已随邮件附上，适合周末集中回看本周精读、今日一题和可积累表达。</div></body>'
            ) if "</body>" in html_body else (html_body + '<div style="margin-top:12px;font-size:13px;color:#9a3412;">📎 本周复盘 PDF 已随邮件附上。</div>')
            plain_text = plain_text + "\n\n📎 本周复盘 PDF 已随邮件附上，适合周末集中回看。"
        except Exception as exc:
            weekly_attach_result = {"status": "failed", "error": str(exc)}
    logger.info(
        "weekly pdf attachment status",
        **weekly_attach_meta,
        attachment_count=len(weekly_attachments),
        weekly_pdf_result=weekly_attach_result,
    )

    should_write_history, history_gate = is_official_morning_run()
    if candidate_invocation:
        history_result = {
            "history_read_ok": article_stats.get("history_read_ok"),
            "history_write_ok": False,
            "history_storage": settings.history_storage,
            "history_path": article_stats.get("history_path"),
            "history_appended": 0,
            "history_skip_reason": "nightly candidate mode; morning_send writes official history after successful send.",
            **{f"history_gate_{key}": value for key, value in history_gate.items()},
        }
    elif test_invocation:
        history_result = {
            "history_read_ok": article_stats.get("history_read_ok"),
            "history_write_ok": False,
            "history_storage": settings.history_storage,
            "history_path": article_stats.get("history_path"),
            "history_appended": 0,
            "history_skip_reason": "手动测试模式，本次不写入 OSS 历史记录，避免污染正式去重库。",
            **{f"history_gate_{key}": value for key, value in history_gate.items()},
        }
    elif quality_blocked:
        history_result = {
            "history_read_ok": article_stats.get("history_read_ok"),
            "history_write_ok": False,
            "history_storage": settings.history_storage,
            "history_path": article_stats.get("history_path"),
            "history_appended": 0,
            "history_skip_reason": "质量门禁 P0 阻断，本次不写入正式历史记录。",
            "quality_gate_p0_count": quality_gate.get("p0_count", 0),
            **{f"history_gate_{key}": value for key, value in history_gate.items()},
        }
    elif settings.history_write_official_only and not should_write_history:
        history_result = {
            "history_read_ok": article_stats.get("history_read_ok"),
            "history_write_ok": False,
            "history_storage": settings.history_storage,
            "history_path": article_stats.get("history_path"),
            "history_appended": 0,
            "history_skip_reason": "非正式晨发窗口，本次测试邮件不写入 OSS 历史记录。",
            **{f"history_gate_{key}": value for key, value in history_gate.items()},
        }
    else:
        history_result = append_records(settings.history_path, build_history_records(brief, today))
    logger.info("sent history updated", **history_result)

    send_result: dict[str, Any] | None = None
    if candidate_invocation:
        logger.info(
            "email skipped",
            reason="nightly_candidate_saved",
            valid_recipient_count=len(recipients),
            recipient_source=recipient_source,
            send_mode=settings.send_mode,
            candidate_saved=bool(candidate_save_result and candidate_save_result.get("candidate_saved")),
            quality_gate_p0_count=quality_gate.get("p0_count", 0),
        )
    elif settings.send_email and not quality_blocked:
        send_result = send_email(subject, plain_text, html_body, test_mode=test_invocation, attachments=weekly_attachments)
        logger.info("email send result", subject=subject, **send_result)
    else:
        skip_reason = "quality_gate_fail" if quality_blocked else "SEND_EMAIL=false"
        logger.info(
            "email skipped",
            reason=skip_reason,
            valid_recipient_count=len(recipients),
            recipient_source=recipient_source,
            send_mode=settings.send_mode,
            quality_gate_p0_count=quality_gate.get("p0_count", 0),
        )

    if candidate_invocation:
        archive_result = {
            "daily_archive_saved": False,
            "daily_archive_reason": "nightly candidate mode; morning_send archives after successful send.",
            "candidate_saved": bool(candidate_save_result and candidate_save_result.get("candidate_saved")),
        }
    elif test_invocation:
        archive_result = {
            "daily_archive_saved": False,
            "daily_archive_reason": "手动测试模式，本次不保存到周报素材库。",
            "test_invocation": True,
        }
    elif quality_blocked:
        archive_result = {
            "daily_archive_saved": False,
            "daily_archive_reason": "质量门禁 P0 阻断，本次不保存到周报素材库。",
            "quality_gate_p0_count": quality_gate.get("p0_count", 0),
        }
    else:
        archive_result = archive_daily_content(
            today,
            brief,
            html_body,
            plain_text,
            subject,
            send_success_count=int((send_result or {}).get("success_count", 0)),
        )
    logger.info("daily official archive", **archive_result)
    if candidate_invocation:
        try:
            metrics_result = append_nightly_metrics(
                delivery_date=today,
                test_invocation=test_invocation,
                article_stats=article_stats,
                quality_payload=quality_payload,
                rewrite_result=rewrite_result,
                candidate_save_result=candidate_save_result,
                admin_report_result=admin_report_result,
                blocked_archive_result=blocked_archive_result,
                history_result=history_result,
                archive_result=archive_result,
                final_selection=final_selection,
            )
            logger.info("harness metrics", **metrics_result)
        except Exception as exc:
            logger.info("harness metrics failed", error=str(exc))

    run_summary = build_run_summary(article_stats, final_selection, history_result, send_result)
    logger.info("run summary text", summary=run_summary)
    print(run_summary)

    log_path = logger.save("latest_run.log")
    logger.dump_to_stdout()
    clear_llm_trace_hook()
    return {
        "status": "ok",
        "run_mode": settings.run_mode,
        "mode": "nightly_candidate" if candidate_invocation else event_mode(event),
        "test_invocation": test_invocation,
        "candidate_invocation": candidate_invocation,
        "delivery_date": today,
        "article_count": len(articles),
        "article_stats": article_stats,
        "subject": subject,
        "candidate_saved": bool(candidate_save_result and candidate_save_result.get("candidate_saved")),
        "sent": bool(send_result and int(send_result.get("success_count", 0)) > 0),
        "output_dir": str(settings.output_dir),
        "log": str(log_path),
    }



def _http_query_params(event: Any) -> dict[str, str]:
    payload = normalize_event(event)
    params: dict[str, Any] = {}
    for key in ("queryParameters", "queryStringParameters", "queries", "query"):
        value = payload.get(key)
        if isinstance(value, dict):
            params.update(value)
    raw_query = payload.get("rawQueryString") or payload.get("queryString") or ""
    if raw_query:
        parsed = parse_qs(str(raw_query), keep_blank_values=True)
        params.update({key: values[-1] if values else "" for key, values in parsed.items()})
    # 兼容 FC 测试事件：直接把 task/mode 等放在 event 顶层。
    params.update({key: value for key, value in payload.items() if isinstance(value, (str, int, float, bool))})
    return {str(key): str(value) for key, value in params.items()}


def _http_path(event: Any) -> str:
    payload = normalize_event(event)
    http_info = payload.get("http") if isinstance(payload.get("http"), dict) else {}
    return str(
        payload.get("rawPath")
        or payload.get("path")
        or payload.get("requestPath")
        or http_info.get("path")
        or "/"
    )


def is_http_invocation(event: Any) -> bool:
    payload = normalize_event(event)
    if not isinstance(payload, dict):
        return False
    if payload.get("rawPath") or payload.get("path") or payload.get("requestPath"):
        return True
    if isinstance(payload.get("headers"), dict) or isinstance(payload.get("httpHeaders"), dict):
        return True
    if isinstance(payload.get("requestContext"), dict):
        return True
    if isinstance(payload.get("http"), dict):
        return True
    return False


def is_feedback_like_invocation(event: Any) -> bool:
    """识别反馈相关 HTTP 请求。比 feedback.py 里的判断更宽，避免 feedback_done 被误拦截。"""
    if is_feedback_invocation(event):
        return True
    params = _http_query_params(event)
    task = params.get("task", "").strip().lower()
    mode = params.get("mode", "").strip().lower()
    feedback_tasks = {"feedback", "feedback_done", "feedback_success", "unsubscribe", "unsubscribe_done"}
    return task in feedback_tasks or mode in feedback_tasks


def http_block_response(event: Any) -> dict[str, Any]:
    path = _http_path(event)
    if path == "/favicon.ico":
        return {
            "statusCode": 204,
            "headers": {"Cache-Control": "no-store"},
            "isBase64Encoded": False,
            "body": "",
        }
    return {
        "statusCode": 403,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Disposition": "inline",
            "Cache-Control": "no-store",
        },
        "isBase64Encoded": False,
        "body": "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>不可用</title></head><body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,Arial,sans-serif;padding:28px;line-height:1.7;'><h2>这个入口只用于反馈记录</h2><p>为防止误触发，HTTP 访问不会启动每日晨读发送。</p></body></html>",
    }


def is_weekly_pdf_invocation(event: Any) -> bool:
    payload = normalize_event(event)
    mode = str(payload.get("mode") or payload.get("run_mode") or "").strip().lower()
    task = str(payload.get("task") or payload.get("type") or "").strip().lower()
    return mode in {"weekly", "weekly_pdf", "week_pdf"} or task in {"weekly", "weekly_pdf", "week_pdf"}


def _legacy_handler_unused(event, context):
    payload = normalize_event(event)

    # 1. 反馈请求只能走反馈逻辑，绝不能触发每日晨读。
    if is_feedback_like_invocation(payload):
        return handle_feedback(payload)
    from weekly_pdf_tracking import handle_weekly_pdf_download, is_weekly_pdf_download_invocation

    if is_weekly_pdf_download_invocation(payload):
        return handle_weekly_pdf_download(payload)

    # 2. 所有其他 HTTP 请求一律拦截。
    #    包括 QQ 邮箱/浏览器自动请求的 /favicon.ico、预加载、探测请求等。
    #    这些请求不允许进入 run_daily_brief，避免误发邮件。
    if is_http_invocation(payload):
        return http_block_response(payload)

    # 3. 以下仅允许由非 HTTP 的测试事件/定时触发器调用。
    if is_feedback_test_email_invocation(payload):
        return send_feedback_test_email(payload)
    if is_weekly_pdf_candidate_invocation(payload):
        return generate_weekly_pdf_candidate(payload)
    if is_weekly_pdf_invocation(payload):
        from weekly_report import run_weekly_pdf

        return run_weekly_pdf(payload, test_mode=is_test_invocation(payload))
    return run_daily_brief(payload)


def handler(event, context):
    payload = normalize_event(event)
    try:
        if is_feedback_like_invocation(payload):
            return handle_feedback(payload)
        from weekly_pdf_tracking import handle_weekly_pdf_download, is_weekly_pdf_download_invocation

        if is_weekly_pdf_download_invocation(payload):
            return handle_weekly_pdf_download(payload)
        if is_http_invocation(payload):
            return http_block_response(payload)
        if is_feedback_test_email_invocation(payload):
            return send_feedback_test_email(payload)
        if is_weekly_pdf_candidate_invocation(payload):
            return generate_weekly_pdf_candidate(payload)
        if is_weekly_pdf_invocation(payload):
            from weekly_report import run_weekly_pdf

            return run_weekly_pdf(payload, test_mode=is_test_invocation(payload))
        return run_daily_brief(payload, context=context)
    finally:
        try:
            from llm_client import clear_llm_trace_hook

            clear_llm_trace_hook()
        except Exception:
            pass


if __name__ == "__main__":
    print(json.dumps(run_daily_brief({"mode": settings.run_mode}), ensure_ascii=False, indent=2))
