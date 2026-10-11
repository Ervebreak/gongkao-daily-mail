"""Validate an actual Skill audit without making an additional model request.

This is a provenance/binding contract, not proof that human/model judgments are true.
The Skill must write the judgments after reviewing the final sources and artifacts.
"""
from __future__ import annotations

import datetime as dt
import copy
import hashlib
import json
from typing import Any

from content_quality_reviewer import DIMENSION_LIMITS, _normalize_review
from email_renderer import render_email_html, render_plain_text
from fact_evidence import candidate_content_hash, candidate_fact_hash
from lite_email_renderer import render_lite_email

REQUIRED_SECTIONS = ("source_facts", "selection", "modules", "full", "lite", "cta")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def review_binding(brief: dict[str, Any]) -> dict[str, Any]:
    """Fingerprint final evidence, public brief and renderer outputs, not audit metadata."""
    lite = render_lite_email({"brief": copy.deepcopy(brief), "subject": str(brief.get("email_subject") or "")})
    return {
        "source_set_hash": (brief.get("_source_evidence") or {}).get("source_set_hash"),
        "candidate_fact_hash": candidate_fact_hash(brief),
        "candidate_content_hash": candidate_content_hash(brief),
        "plain_text_hash": _hash(render_plain_text(brief)),
        "full_html_hash": _hash(render_email_html(brief)),
        "lite_payload_hash": _hash(json.dumps(lite, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)),
    }


def _failure(message: str) -> dict[str, Any]:
    return {
        "ok": False, "status": "fail", "score": 0, "can_send": False,
        "risk_level": "high", "scores": {},
        "checks": {"review_origin": "skill", "additional_model_api_called": False},
        "issues": [{"severity": "high", "code": "content_quality_reviewer_error", "message": message}],
        "needs_manual_full_review": True,
    }


def evaluate_skill_content_review(brief: dict[str, Any], plain_text: str, html_body: str, review: Any) -> dict[str, Any]:
    """Fail closed for missing/stale/incomplete audits; recompute existing thresholds."""
    if not isinstance(review, dict) or review.get("schema_version") != 1 or review.get("review_origin") != "skill":
        return _failure("缺少有效技能审稿记录；不得以跳过审稿或预设 PASS 替代。")
    if review.get("delivery_date") != brief.get("date"):
        return _failure("技能审稿日期与候选日期不一致。")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict) or not all(isinstance(reviewer.get(k), str) and reviewer[k].strip() for k in ("name", "model")):
        return _failure("技能审稿缺少审核者或实际模型标识。")
    if reviewer["model"].strip().lower() in {"mock", "sample", "test"}:
        return _failure("模拟审稿不能建立生产 PASS。")
    try:
        reviewed_at = dt.datetime.fromisoformat(str(review.get("reviewed_at") or "").replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None:
            raise ValueError("timezone missing")
    except ValueError:
        return _failure("技能审稿缺少带时区的实际审核时间。")
    bundle = brief.get("_source_evidence") or {}
    items = bundle.get("items") if isinstance(bundle, dict) else None
    if not isinstance(items, dict) or not items or not all(isinstance(x, dict) and x.get("verification_status") == "verified" for x in items.values()):
        return _failure("技能审稿所依赖的原文证据未核验完成。")
    expected = review_binding(brief)
    if not expected["source_set_hash"] or review.get("binding") != expected:
        return _failure("技能审稿与当前证据、正文或 Full/Lite 成品绑定不一致，必须重新审核。")
    if plain_text != render_plain_text(brief) or html_body != render_email_html(brief):
        return _failure("候选保存的正文与最终 brief 渲染结果不一致。")
    dimensions = review.get("dimension_reviews")
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSION_LIMITS):
        return _failure("技能审稿八维评分不完整。")
    scores = {}
    for name, limit in DIMENSION_LIMITS.items():
        item = dimensions[name]
        if not isinstance(item, dict) or type(item.get("score")) is not int or not 0 <= item["score"] <= limit or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            return _failure(f"技能审稿维度 {name} 缺少有效评分和具体依据。")
        scores[name] = item["score"]
    sections = review.get("section_checks")
    if not isinstance(sections, dict) or set(sections) != set(REQUIRED_SECTIONS):
        return _failure("技能审稿未覆盖事实、选文、模块、Full、Lite、CTA。")
    issues = review.get("issues")
    if not isinstance(issues, list) or any(not isinstance(x, dict) or x.get("severity") not in {"high", "medium", "low"} or not x.get("code") or not x.get("message") for x in issues):
        return _failure("技能审稿问题清单格式无效。")
    issues = list(issues)
    for name in REQUIRED_SECTIONS:
        item = sections[name]
        if not isinstance(item, dict) or item.get("status") not in {"pass", "review", "block"} or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            return _failure(f"技能审稿模块 {name} 缺少结论和具体依据。")
        if item["status"] != "pass":
            issues.append({"severity": "high" if item["status"] == "block" else "medium", "code": "content_quality_p0" if item["status"] == "block" else "content_quality_review", "message": f"[{name}] {item['reason']}"})
    if review.get("overall_score") != sum(scores.values()):
        return _failure("技能审稿总分与八维明细不一致。")
    if review.get("risk_level") not in {"low", "medium", "high"} or not isinstance(review.get("one_sentence_judgment"), str) or not review["one_sentence_judgment"].strip():
        return _failure("技能审稿缺少风险等级或最终判断。")
    if review["risk_level"] == "high":
        issues.append({"severity": "high", "code": "content_quality_p0", "message": "技能审稿判定高风险，不能放行。"})
    # Arbitrary high-risk codes also remain blocking under the existing gate taxonomy.
    p0 = [{**x, "code": x["code"] if x["code"] in {"unsupported_claims", "low_source_alignment"} else "content_quality_p0"} for x in issues if x["severity"] == "high"]
    result = _normalize_review({
        "scores": scores, "overall_score": sum(scores.values()), "risk_level": review["risk_level"],
        "p0_issues": p0, "p1_issues": [x for x in issues if x["severity"] != "high"],
        "one_sentence_judgment": review["one_sentence_judgment"],
    }, model=reviewer["model"])
    if issues and result["status"] == "ok":
        result.update(status="review", can_send=False)
    result["checks"].update({
        "review_origin": "skill", "reviewer": reviewer, "reviewed_at": review["reviewed_at"],
        "additional_model_api_called": False, "reviewed_against_source_evidence": True,
        **expected,
    })
    result["skill_audit"] = review
    return result
