from __future__ import annotations

from pathlib import Path
from typing import Any


VISIBLE_TRUNCATION_GATE_CODES = {"text_truncation", "truncated_takeaway", "expression_truncated"}

MODULE_LABELS = {
    "daily_question": "今日一题",
    "framework_map": "文章框架图",
    "today_takeaway": "今日可带走",
    "brief_cleanliness": "整体清洁度",
    "quick_reads": "今日速读",
    "duplication": "重复表达",
    "expression_quality": "表达质量",
    "module_redundancy": "模块冗余",
    "content_risk": "内容风险",
    "selection": "选题质量",
    "content_quality": "正文内容质量",
    "cleanliness": "PreSend 清洁度",
    "pre_send_cleanliness": "PreSend 清洁度",
    "policy_coordinate": "政策坐标",
    "subject_quality": "主题质量",
    "reading_guide": "阅读导语",
    "lite_email": "简版邮件",
    "weekly_pdf": "周 PDF",
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

LITE_EMAIL_P0_CODES = {
    "lite_cta_truncated",
    "lite_internal_marker_leaked",
}

WEEKLY_PDF_P0_CODES = {
    "weekly_pdf_missing_oss_path",
    "weekly_pdf_lite_preview_missing_oss_path",
    "weekly_pdf_full_path_wrong_variant",
    "weekly_pdf_lite_path_wrong_variant",
    "weekly_pdf_date_range_mismatch",
    "weekly_pdf_invalid_date_range",
    "weekly_pdf_internal_marker_leaked",
}


def _quality_issue_signature(issue: Any) -> tuple[str, str, str]:
    if not isinstance(issue, dict):
        return ("", "", "")
    return (
        str(issue.get("module") or ""),
        str(issue.get("code") or ""),
        str(issue.get("message") or ""),
    )


def _compact_visible_text(value: Any) -> str:
    return "".join(str(value or "").split())


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
        issues.append(
            {
                "severity": "high",
                "code": "weak_featured_selection",
                "message": f"主线文章选题分过低：{total_score}，应重新选题或进入人工复核。",
            }
        )
    sensitive_surface = _selection_sensitive_surface(brief, featured, article)
    sensitive_hits = [term for term in SENSITIVE_TOPIC_TERMS if term in sensitive_surface]
    if sensitive_hits and total_score >= 0 and total_score < 85:
        issues.append(
            {
                "severity": "high",
                "code": "sensitive_topic_needs_review",
                "message": f"敏感主题选题分低于 85（{total_score}），命中：{'、'.join(sensitive_hits[:5])}，需人工复核或重选。",
            }
        )
    body_text = _stringify_for_quality(brief)
    expression_hits = [term for term in GENDER_SENSITIVE_EXPRESSIONS if term in body_text]
    if expression_hits:
        issues.append(
            {
                "severity": "high",
                "code": "gender_sensitive_expression",
                "message": f"正文含性别/婚育敏感表达：{'、'.join(expression_hits[:5])}，需改写为中性治理表达。",
            }
        )
    if featured.get("risk_note"):
        issues.append(
            {
                "severity": "medium",
                "code": "selection_risk_note",
                "message": str(featured.get("risk_note")),
            }
        )
    high_count = sum(1 for issue in issues if issue.get("severity") == "high")
    return {
        "ok": high_count == 0,
        "status": "fail" if high_count else ("review" if issues else "ok"),
        "score": 100 if not issues else (60 if high_count else 82),
        "checks": {"featured_total_score": total_score, "featured_title": featured.get("title") or article.get("title")},
        "issues": issues,
    }


def _collect_visible_truncation_gate_issues(
    quality_map: dict[str, Any],
    plain_text: str = "",
    html_body: str = "",
) -> list[dict[str, str]]:
    haystack = _compact_visible_text(f"{plain_text}\n{html_body}")
    if not haystack:
        return []
    seen: set[tuple[str, str, str]] = set()
    p0_issues: list[dict[str, str]] = []
    for module, quality in quality_map.items():
        if not isinstance(quality, dict):
            continue
        for issue in quality.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "")
            severity = str(issue.get("severity") or "").lower()
            bad_text = str(issue.get("bad_text") or "").strip()
            if severity != "high" or code not in VISIBLE_TRUNCATION_GATE_CODES or not bad_text:
                continue
            if _compact_visible_text(bad_text) not in haystack:
                continue
            candidate = {
                "module": str(issue.get("module_override") or module),
                "code": code,
                "message": str(issue.get("message") or code),
            }
            signature = _quality_issue_signature(candidate)
            if signature in seen:
                continue
            seen.add(signature)
            p0_issues.append(candidate)
    return p0_issues


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
    policy_coordinate_quality: dict[str, Any] | None = None,
    subject_quality: dict[str, Any] | None = None,
    reading_guide_quality: dict[str, Any] | None = None,
    lite_email_quality: dict[str, Any] | None = None,
    weekly_pdf_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    content_quality_p0_codes = {
        "missing_required_module",
        "wrong_article_understanding",
        "fabricated_policy",
    }
    p0_codes = {
        "missing_question",
        "missing_task",
        "too_broad",
        "missing_candidate_answer",
        "isolated_number",
        "grassroots_authority_overreach",
        "incomplete_label",
        "exam_migration_step",
        "missing_main_line",
        "too_few_steps",
        "empty_golden_sentence",
        "label_leaked_in_golden_sentence",
        "email_too_short",
        "missing_html",
        "dev_marker_leaked",
        "python_list_leaked",
        "quick_read_dev_marker",
        "empty_quick_read",
        "missing_quick_read_one_sentence",
        "quick_read_url_not_valid",
        "quick_reads_all_news_summary",
        "weak_featured_selection",
        "sensitive_topic_needs_review",
        "dev_marker_repeated",
        "abnormal_copy_duplication",
        "repeated_expression_across_modules",
        "module_role_overlap",
        "expression_dev_marker",
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
        *LITE_EMAIL_P0_CODES,
        *WEEKLY_PDF_P0_CODES,
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
        ("cleanliness", cleanliness_quality or {}),
        ("policy_coordinate", policy_coordinate_quality or {}),
        ("subject_quality", subject_quality or {}),
        ("reading_guide", reading_guide_quality or {}),
        ("lite_email", lite_email_quality or {}),
        ("weekly_pdf", weekly_pdf_quality or {}),
    )
    for module, quality in modules:
        for issue in quality.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "")
            severity = str(issue.get("severity") or "").lower()
            if severity == "high" and code in p0_codes:
                p0_issues.append(
                    {
                        "module": str(issue.get("module_override") or module),
                        "code": code,
                        "message": str(issue.get("message") or code),
                    }
                )
    content_quality_payload = content_quality or {}
    content_quality_failed = str(content_quality_payload.get("status") or "").lower() == "fail" or content_quality_payload.get("can_send") is False
    if content_quality_failed:
        for issue in content_quality_payload.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "")
            severity = str(issue.get("severity") or "").lower()
            if severity != "high" or code not in content_quality_p0_codes:
                continue
            candidate_issue = {
                "module": str(issue.get("module_override") or "content_quality"),
                "code": code,
                "message": str(issue.get("message") or code),
            }
            if candidate_issue not in p0_issues:
                p0_issues.append(candidate_issue)
    return {
        "overall": "fail" if p0_issues else "ok",
        "p0_count": len(p0_issues),
        "p0_issues": p0_issues[:8],
    }


def evaluate_all_quality(
    brief: dict[str, Any],
    plain_text: str,
    html_body: str,
    *,
    test_invocation: bool,
    selection_quality: dict[str, Any] | None = None,
    cleanliness_quality: dict[str, Any] | None = None,
    latest_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from brief_quality import evaluate_brief_cleanliness
    from content_quality_reviewer import evaluate_content_quality
    from content_risk_quality import evaluate_content_risks
    from duplication_quality import evaluate_duplication
    from expression_quality import evaluate_expression_quality
    from framework_quality import evaluate_framework_map
    from lite_email_quality import evaluate_lite_email_quality
    from lite_email_renderer import render_lite_email
    from module_redundancy_quality import evaluate_module_redundancy
    from policy_coordinate_quality import evaluate_policy_coordinate_quality
    from question_quality import evaluate_daily_question
    from quick_reads_quality import evaluate_quick_reads
    from reading_guide_quality import evaluate_reading_guide_quality
    from subject_quality import evaluate_subject_quality
    from takeaway_quality import evaluate_takeaway

    if selection_quality is None:
        selection_quality = {}
    if cleanliness_quality is None:
        cleanliness_quality = {}
    lite_payload = latest_json if isinstance(latest_json, dict) else {"brief": brief}
    lite_rendered = render_lite_email(lite_payload)
    return {
        "daily_question": evaluate_daily_question(brief),
        "framework_map": evaluate_framework_map(brief),
        "today_takeaway": evaluate_takeaway(brief),
        "brief_cleanliness": evaluate_brief_cleanliness(brief, plain_text, html_body),
        "quick_reads": evaluate_quick_reads(brief),
        "duplication": evaluate_duplication(brief),
        "expression_quality": evaluate_expression_quality(brief),
        "module_redundancy": evaluate_module_redundancy(brief),
        "content_risk": evaluate_content_risks(brief, plain_text, html_body),
        "selection": selection_quality,
        "content_quality": evaluate_content_quality(brief, plain_text, html_body, test_mode=test_invocation),
        "cleanliness": cleanliness_quality,
        "policy_coordinate": evaluate_policy_coordinate_quality(brief, plain_text, html_body),
        "subject_quality": evaluate_subject_quality(brief),
        "reading_guide": evaluate_reading_guide_quality(brief),
        "lite_email": evaluate_lite_email_quality(lite_payload, plain_text=lite_rendered["plain_text"], html_body=lite_rendered["html_body"]),
    }


def build_gate_from_quality_map(quality: dict[str, Any], plain_text: str = "", html_body: str = "") -> dict[str, Any]:
    gate = build_quality_gate(
        quality.get("daily_question", {}),
        quality.get("framework_map", {}),
        quality.get("today_takeaway", {}),
        quality.get("brief_cleanliness", {}),
        quality.get("quick_reads", {}),
        quality.get("duplication", {}),
        quality.get("expression_quality", {}),
        quality.get("module_redundancy", {}),
        quality.get("content_risk", {}),
        quality.get("selection", {}),
        quality.get("content_quality", {}),
        quality.get("cleanliness", {}),
        quality.get("policy_coordinate", {}),
        quality.get("subject_quality", {}),
        quality.get("reading_guide", {}),
        quality.get("lite_email", {}),
        quality.get("weekly_pdf", {}),
    )
    for issue in _collect_visible_truncation_gate_issues(quality, plain_text=plain_text, html_body=html_body):
        if issue not in gate["p0_issues"]:
            gate["p0_issues"].append(issue)
    gate["p0_count"] = len(gate["p0_issues"])
    gate["p0_issues"] = gate["p0_issues"][:8]
    gate["overall"] = "fail" if gate["p0_issues"] else "ok"
    return gate


def evaluate_weekly_pdf_quality(candidate_or_weekly_pdf: dict[str, Any], *, delivery_date: str = "") -> dict[str, Any]:
    from weekly_pdf_quality import evaluate_weekly_pdf_quality as _evaluate_weekly_pdf_quality

    return _evaluate_weekly_pdf_quality(candidate_or_weekly_pdf, delivery_date=delivery_date)


def looks_like_gate_drift(stored_gate: dict[str, Any] | None, current_gate: dict[str, Any] | None) -> bool:
    stored = stored_gate if isinstance(stored_gate, dict) else {}
    current = current_gate if isinstance(current_gate, dict) else {}
    return str(stored.get("overall") or "") == "ok" and str(current.get("overall") or "") == "fail"


def read_text_if_exists(path_value: Any, *, limit: int = 40000) -> str:
    path_text = str(path_value or "").strip()
    if not path_text:
        return ""
    path = Path(path_text)
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except Exception:
        return ""
