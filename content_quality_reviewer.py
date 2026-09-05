from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import settings
from llm_client import chat_completion
from fact_evidence import candidate_fact_hash, evidence_prompt_payload


DIMENSION_LIMITS = {
    "topic_fit": 20,
    "user_safety": 15,
    "exam_value": 20,
    "source_alignment": 15,
    "information_gain": 10,
    "naturalness": 10,
    "module_coherence": 5,
    "cleanliness": 5,
}

P0_CODES = {
    "content_quality_p0",
    "low_content_quality",
    "low_user_safety",
    "low_exam_value",
    "low_source_alignment",
    "unsafe_sensitive_framing",
    "unsupported_claims",
    "mainline_incoherent",
}

REWRITE_TARGET_FIELDS = {
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
    "brief.featured_article.original_reading_focus",
    "brief.featured_article.usable_for_exam",
    "brief.featured_article.rewritable_expression",
    "brief.featured_article.article_framework_map.main_thread",
    "brief.featured_article.article_framework_map.steps",
    "brief.today_takeaway.common_knowledge_points",
    "brief.today_takeaway.golden_sentences",
    "brief.today_takeaway.framework",
    "brief.quick_reads[0].one_sentence",
    "brief.quick_reads[1].one_sentence",
}


def _clip_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _clamp_int(value: Any, default: int = 0, low: int = 0, high: int = 100) -> int:
    try:
        num = int(round(float(value)))
    except Exception:
        num = default
    return max(low, min(high, num))


def _load_prompt_template() -> str:
    path = Path(__file__).with_name("content_harness") / "content_quality_review_prompt.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "你是公考/考编每日晨读邮件的内容质量审核员。请严格按给定维度输出 JSON。"


def _model_candidates(test_mode: bool) -> list[str]:
    if test_mode:
        candidates = [
            settings.test_content_quality_llm_model,
            settings.test_content_quality_llm_fallback_model,
            settings.test_writing_llm_model,
            settings.test_llm_model,
            settings.content_quality_llm_model,
            settings.content_quality_llm_fallback_model,
            settings.writing_llm_model,
            settings.llm_model,
            settings.llm_fallback_model,
        ]
    else:
        candidates = [
            settings.content_quality_llm_model,
            settings.content_quality_llm_fallback_model,
            settings.writing_llm_model,
            settings.writing_llm_fallback_model,
            settings.llm_model,
            settings.llm_fallback_model,
        ]
    seen: set[str] = set()
    result: list[str] = []
    for model in candidates:
        model = str(model or "").strip()
        if model and model not in seen:
            seen.add(model)
            result.append(model)
    return result


def get_content_quality_model_plan(test_mode: bool = False) -> list[str]:
    return _model_candidates(test_mode)


def _mock_content_quality() -> dict[str, Any]:
    scores = {
        "topic_fit": 17,
        "user_safety": 13,
        "exam_value": 17,
        "source_alignment": 13,
        "information_gain": 8,
        "naturalness": 8,
        "module_coherence": 4,
        "cleanliness": 5,
    }
    return {
        "ok": True,
        "status": "ok",
        "score": sum(scores.values()),
        "risk_level": "low",
        "can_send": True,
        "scores": scores,
        "checks": {
            "model": "mock",
            "thresholds": {
                "overall_score_min": 75,
                "user_safety_min": 10,
                "exam_value_min": 14,
                "source_alignment_min": 10,
            },
        },
        "issues": [],
        "rewrite_suggestions": [],
        "rewrite_targets": [],
        "needs_manual_full_review": False,
        "one_sentence_judgment": "离线 mock 内容质检通过。",
    }


def _issue_from_raw(raw: Any, *, severity: str, fallback_code: str) -> dict[str, str]:
    if isinstance(raw, dict):
        code = str(raw.get("code") or fallback_code).strip() or fallback_code
        message = str(raw.get("message") or raw.get("reason") or raw.get("detail") or code).strip()
        raw_severity = str(raw.get("severity") or severity).strip().lower()
        issue = {"severity": raw_severity or severity, "code": code, "message": message or code}
        if raw.get("bad_text"):
            issue["bad_text"] = str(raw.get("bad_text")).strip()
        if raw.get("field"):
            issue["field"] = str(raw.get("field")).strip()
        for key in ("candidate_claim", "source_locator", "judgment", "repair_target"):
            if raw.get(key):
                issue[key] = str(raw.get(key)).strip()
        return issue
    text = str(raw or "").strip()
    return {"severity": severity, "code": fallback_code, "message": text or fallback_code}


def _normalize_rewrite_target(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    field = str(raw.get("field") or "").strip()
    if field and not field.startswith("brief."):
        field = f"brief.{field}"
    if field not in REWRITE_TARGET_FIELDS:
        return None
    issue_code = str(raw.get("issue_code") or raw.get("code") or "").strip() or "content_quality_review"
    reason = str(raw.get("reason") or raw.get("message") or "").strip()
    action = str(raw.get("action") or raw.get("suggestion") or "").strip()
    severity = str(raw.get("severity") or "medium").strip().lower()
    if severity not in {"low", "medium", "high"}:
        severity = "medium"
    module = str(raw.get("module") or "").strip()
    if not module:
        module = field.split(".")[1] if "." in field else "brief"
    return {
        "field": field,
        "module": module,
        "issue_code": issue_code,
        "reason": reason or issue_code,
        "action": action or "Rewrite this field locally while preserving facts and source meaning.",
        "severity": severity,
        "auto_fixable": bool(raw.get("auto_fixable", True)),
        **({"bad_text": str(raw.get("bad_text")).strip()} if raw.get("bad_text") else {}),
        **({"suggestion": str(raw.get("suggestion")).strip()} if raw.get("suggestion") else {}),
    }


def _issue_to_rewrite_target(issue: dict[str, Any]) -> dict[str, Any] | None:
    code = str(issue.get("code") or "").strip()
    message = str(issue.get("message") or "").strip()
    if code == "weak_student_voice":
        return {
            "field": "brief.daily_question.candidate_answer",
            "module": "daily_question",
            "issue_code": code,
            "reason": message or "The answer sounds too formal and is hard for a candidate to repeat.",
            "action": "Rewrite as a natural high-scoring candidate answer; keep the steps and facts unchanged.",
            "severity": "medium",
            "auto_fixable": True,
        }
    if code == "near_duplicate_viewpoint":
        return {
            "field": "brief.featured_article.rewritable_expression",
            "module": "featured_article",
            "issue_code": code,
            "reason": message or "Cross-module viewpoint is repetitive.",
            "action": "Rewrite as a distinct exam-entry angle and avoid repeating the top judgment or golden sentences.",
            "severity": str(issue.get("severity") or "medium").lower(),
            "auto_fixable": True,
        }
    if code in {"expression_rigidity", "policy_tone_too_heavy"}:
        return {
            "field": "brief.featured_article.article_framework_map.steps",
            "module": "featured_article",
            "issue_code": code,
            "reason": message or "The framework expression is too abstract or rigid.",
            "action": "Rewrite the affected framework wording into concrete exam-facing language without changing the structure.",
            "severity": str(issue.get("severity") or "medium").lower(),
            "auto_fixable": True,
        }
    if code in {"legal_overstatement", "authority_overclaim"} and issue.get("field"):
        return {
            "field": str(issue.get("field")),
            "module": str(issue.get("module") or "brief"),
            "issue_code": code,
            "reason": message or code,
            "action": "Soften the unsupported legal or authority claim while preserving the intended meaning.",
            "severity": str(issue.get("severity") or "medium").lower(),
            "auto_fixable": True,
            **({"bad_text": str(issue.get("bad_text")).strip()} if issue.get("bad_text") else {}),
            **({"suggestion": str(issue.get("suggestion")).strip()} if issue.get("suggestion") else {}),
        }
    return None


def _semantic_truncation_targets(raw: dict[str, Any], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "").strip()
        if code == "truncation_error":
            message = str(issue.get("message") or "") + " " + str((raw.get("raw_review") or {}).get("notes") if isinstance(raw.get("raw_review"), dict) else "")
            inferred = {
                "original_reading_focus": "brief.featured_article.original_reading_focus",
                "quick_reads[0]": "brief.quick_reads[0].one_sentence",
                "quick_reads[1]": "brief.quick_reads[1].one_sentence",
                "today_takeaway.framework": "brief.today_takeaway.framework",
            }
            for marker, inferred_field in inferred.items():
                if marker not in message:
                    continue
                targets.append({
                    "field": inferred_field,
                    "module": inferred_field.split(".")[1],
                    "issue_code": code,
                    "reason": str(issue.get("message") or code).strip() or code,
                    "action": "Rewrite this exact field into a complete sentence without adding source facts, then rerender and recheck every output variant.",
                    "severity": "high",
                    "auto_fixable": True,
                })
            continue
        if code not in {"text_truncation", "truncated_takeaway", "expression_truncated"}:
            continue
        field = str(issue.get("field") or "").strip()
        if field and not field.startswith("brief."):
            field = f"brief.{field}"
        if field not in REWRITE_TARGET_FIELDS:
            continue
        targets.append(
            {
                "field": field,
                "module": field.split(".")[1] if "." in field else "brief",
                "issue_code": code,
                "reason": str(issue.get("message") or code).strip() or code,
                "action": "Rewrite this field into a complete, natural sentence and remove any truncated tail while preserving the original meaning.",
                "severity": "high",
                "auto_fixable": True,
                **({"bad_text": str(issue.get("bad_text")).strip()} if issue.get("bad_text") else {}),
            }
        )
    return targets
def _normalize_rewrite_targets(raw: dict[str, Any], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    seen_fields: set[str] = set()
    for item in raw.get("rewrite_targets") or []:
        target = _normalize_rewrite_target(item)
        if not target:
            continue
        key = (target["field"], target["issue_code"])
        if key in seen:
            continue
        seen.add(key)
        seen_fields.add(target["field"])
        targets.append(target)
    for issue in issues:
        target = _normalize_rewrite_target(_issue_to_rewrite_target(issue))
        if not target:
            continue
        key = (target["field"], target["issue_code"])
        if key in seen:
            continue
        seen.add(key)
        seen_fields.add(target["field"])
        targets.append(target)
    for target in _semantic_truncation_targets(raw, issues):
        if target["field"] in seen_fields:
            continue
        key = (target["field"], target["issue_code"])
        if key in seen:
            continue
        seen.add(key)
        seen_fields.add(target["field"])
        targets.append(target)
    return targets[:8]


def _normalize_review(raw: dict[str, Any], *, model: str) -> dict[str, Any]:
    raw_scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
    scores = {
        key: _clamp_int(raw_scores.get(key), 0, 0, max_score)
        for key, max_score in DIMENSION_LIMITS.items()
    }
    score = _clamp_int(raw.get("overall_score", raw.get("score", sum(scores.values()))), sum(scores.values()))
    risk_level = str(raw.get("risk_level") or "medium").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "medium"

    issues: list[dict[str, str]] = []
    for item in raw.get("p0_issues") or []:
        issues.append(_issue_from_raw(item, severity="high", fallback_code="content_quality_p0"))
    for item in raw.get("p1_issues") or raw.get("issues") or []:
        issues.append(_issue_from_raw(item, severity="medium", fallback_code="content_quality_review"))

    if score < 75:
        issues.append({
            "severity": "high",
            "code": "low_content_quality",
            "message": f"内容质量总分低于75：{score}",
        })
    if scores["user_safety"] < 10:
        issues.append({
            "severity": "high",
            "code": "low_user_safety",
            "message": f"用户安全感低于10/15：{scores['user_safety']}",
        })
    if scores["exam_value"] < 14:
        issues.append({
            "severity": "high",
            "code": "low_exam_value",
            "message": f"考场转化价值低于14/20：{scores['exam_value']}",
        })
    if scores["source_alignment"] < 10:
        issues.append({
            "severity": "high",
            "code": "low_source_alignment",
            "message": f"原文贴合度低于10/15：{scores['source_alignment']}",
        })

    # Deduplicate while preserving order; explicit P0 codes stay high.
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        code = str(issue.get("code") or "")
        message = str(issue.get("message") or "")
        key = (code, message)
        if key in seen:
            continue
        seen.add(key)
        if code in P0_CODES:
            issue = {**issue, "severity": "high"}
        deduped.append(issue)

    high_count = sum(1 for item in deduped if str(item.get("severity") or "").lower() == "high")
    ok = high_count == 0 and score >= 75
    status = "ok" if ok and score >= 80 else ("fail" if high_count else "review")
    rewrite_targets = _normalize_rewrite_targets(raw, deduped)
    return {
        "ok": ok,
        "status": status,
        "score": score,
        "risk_level": risk_level,
        "can_send": bool(raw.get("can_send", ok)) and ok,
        "scores": scores,
        "checks": {
            "model": model,
            "thresholds": {
                "overall_score_min": 75,
                "user_safety_min": 10,
                "exam_value_min": 14,
                "source_alignment_min": 10,
            },
        },
        "issues": deduped,
        "rewrite_suggestions": raw.get("rewrite_suggestions") if isinstance(raw.get("rewrite_suggestions"), list) else [],
        "rewrite_targets": rewrite_targets,
        "needs_manual_full_review": bool(score < 75 and not rewrite_targets),
        "one_sentence_judgment": str(raw.get("one_sentence_judgment") or "").strip(),
        "raw_review": raw,
    }


def _build_review_prompt(brief: dict[str, Any], plain_text: str, html_body: str) -> str:
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    takeaway = brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}
    payload = {
        "source_evidence": evidence_prompt_payload(
            brief.get("_source_evidence") if isinstance(brief.get("_source_evidence"), dict) else {}
        ),
        "review_binding": {
            "source_set_hash": (brief.get("_source_evidence") or {}).get("source_set_hash") if isinstance(brief.get("_source_evidence"), dict) else None,
            "candidate_fact_hash": candidate_fact_hash(brief),
        },
        "email_subject": brief.get("email_subject"),
        "today_theme": brief.get("today_theme"),
        "today_focus": brief.get("today_focus"),
        "today_three_things": brief.get("today_three_things"),
        "featured_article": {
            "title": featured.get("title"),
            "source": featured.get("source"),
            "published_at": featured.get("published_at"),
            "theme": featured.get("theme"),
            "one_sentence": featured.get("one_sentence"),
            "core_viewpoint": featured.get("core_viewpoint"),
            "article_framework_map": featured.get("article_framework_map"),
            "exam_use": featured.get("exam_use") or featured.get("usable_for_exam"),
            "url_status": featured.get("url_status"),
        },
        "daily_question": question,
        "today_takeaway": takeaway,
        "quick_reads": brief.get("quick_reads"),
        "plain_text": _clip_text(plain_text, 12000),
        "html_excerpt_first_6000": _clip_text(html_body, 6000),
        "html_tail_2000": html_body[-2000:] if html_body else "",
        "html_complete": bool(html_body and html_body.rstrip().lower().endswith("</html>")),
    }
    return (
        _load_prompt_template()
        + "\n\n请将 source_evidence 中的带段落编号原文与候选逐项对照，只输出合法 JSON。不得仅相信候选自行生成的摘要。重点检查主体、时间、数字对象及单位、范围、确定性、因果和新增事件；特别阻止‘可能→已经’、‘部分→普遍’、‘问题仍存在→治理后复发’。合法且明确标注的模拟题可以保留，但模拟情节不得进入原文概括或结构图。每个事实报警写明 field、candidate_claim、source_locator、judgment、repair_target。不确定项也必须标为待核验。html_excerpt_first_6000 是邮件头部截取片段，不能仅因该字段末尾不闭合就判定实际 HTML 截断；如需判断完整性，请结合 html_tail_2000 和 html_complete：\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def evaluate_content_quality(brief: dict[str, Any], plain_text: str, html_body: str, test_mode: bool = False) -> dict[str, Any]:
    if not settings.content_quality_enabled:
        return {
            "ok": True,
            "status": "skipped",
            "score": 100,
            "risk_level": "low",
            "can_send": True,
            "scores": {},
            "checks": {"enabled": False},
            "issues": [],
            "rewrite_suggestions": [],
            "rewrite_targets": [],
            "needs_manual_full_review": False,
            "one_sentence_judgment": "CONTENT_QUALITY_ENABLED=false，已跳过内容质量审稿。",
        }

    models = _model_candidates(test_mode)
    if test_mode and any(model.lower() == "mock" for model in models):
        result = _mock_content_quality()
        result["checks"] = {
            **dict(result.get("checks") or {}),
            "source_set_hash": (brief.get("_source_evidence") or {}).get("source_set_hash") if isinstance(brief.get("_source_evidence"), dict) else None,
            "candidate_fact_hash": candidate_fact_hash(brief),
            "mock_proves_contract_only": True,
        }
        return result
    prompt = _build_review_prompt(brief, plain_text, html_body)
    errors: list[str] = []
    for attempt, model in enumerate(models, start=1):
        try:
            raw = chat_completion(
                model,
                prompt,
                timeout=settings.content_quality_timeout,
                trace={
                    "stage": "content_quality",
                    "attempt": attempt,
                    "candidate_count": len(models),
                    "fallback_used": attempt > 1,
                    "test_mode": test_mode,
                    "contract": False,
                },
            )
            result = _normalize_review(raw, model=model)
            result["checks"] = {
                **dict(result.get("checks") or {}),
                "source_set_hash": (brief.get("_source_evidence") or {}).get("source_set_hash") if isinstance(brief.get("_source_evidence"), dict) else None,
                "candidate_fact_hash": candidate_fact_hash(brief),
                "reviewed_against_source_evidence": True,
            }
            return result
        except Exception as exc:
            errors.append(f"{model}: {exc}")

    message = "内容质量审稿模型调用失败：" + " | ".join(errors)
    return {
        "ok": False,
        "status": "fail",
        "score": 0,
        "risk_level": "high",
        "can_send": False,
        "scores": {},
        "checks": {"models": models, "error_count": len(errors)},
        "issues": [{"severity": "high", "code": "content_quality_reviewer_error", "message": message}],
        "rewrite_suggestions": [],
        "rewrite_targets": [],
        "needs_manual_full_review": True,
        "one_sentence_judgment": "内容质量审稿失败，不建议自动发送。",
    }
