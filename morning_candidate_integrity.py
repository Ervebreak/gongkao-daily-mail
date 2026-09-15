from __future__ import annotations

import copy
from typing import Any

from fact_evidence import candidate_content_hash, current_fact_review_binding


SEND_SNAPSHOT_KEY = "_morning_send_snapshot"
_BINDING_KEYS = ("source_set_hash", "candidate_fact_hash", "candidate_content_hash")
_REQUIRED_SCORE_KEYS = (
    "topic_fit",
    "user_safety",
    "exam_value",
    "source_alignment",
    "information_gain",
    "naturalness",
    "module_coherence",
    "cleanliness",
)


def attach_candidate_send_snapshot(candidate: dict[str, Any]) -> dict[str, Any]:
    """Attach an in-memory snapshot of the already-audited rendered candidate.

    The snapshot is added only when a candidate is loaded for morning send. It is
    never part of the persisted candidate payload. The public brief hash binds the
    stored plain/html artifacts to the exact reader-facing brief they were audited
    against.
    """
    if not isinstance(candidate, dict):
        return candidate
    brief = candidate.get("brief") if isinstance(candidate.get("brief"), dict) else {}
    plain_text = str(candidate.get("plain_text") or "")
    html_body = str(candidate.get("html_body") or "")
    if not brief or not plain_text or not html_body:
        return candidate

    quality = dict(candidate.get("quality") or {}) if isinstance(candidate.get("quality"), dict) else {}
    quality[SEND_SNAPSHOT_KEY] = {
        "candidate_content_hash": candidate_content_hash(brief),
        "subject": str(candidate.get("subject") or ""),
        "plain_text": plain_text,
        "html_body": html_body,
    }
    candidate["quality"] = quality
    return candidate


def restore_bound_render_snapshot(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Restore stored rendered artifacts only while the reader-facing brief is unchanged."""
    fixed = copy.deepcopy(data)
    brief = fixed.get("brief") if isinstance(fixed.get("brief"), dict) else {}
    quality = fixed.get("quality") if isinstance(fixed.get("quality"), dict) else {}
    snapshot = quality.get(SEND_SNAPSHOT_KEY) if isinstance(quality.get(SEND_SNAPSHOT_KEY), dict) else {}
    if not brief or not snapshot:
        return fixed, False

    expected_hash = str(snapshot.get("candidate_content_hash") or "")
    if not expected_hash or candidate_content_hash(brief) != expected_hash:
        return fixed, False

    plain_text = str(snapshot.get("plain_text") or "")
    html_body = str(snapshot.get("html_body") or "")
    if not plain_text or not html_body:
        return fixed, False

    fixed["plain_text"] = plain_text
    fixed["html_body"] = html_body
    if str(snapshot.get("subject") or ""):
        fixed["subject"] = str(snapshot.get("subject") or "")
    return fixed, True


def _stored_content_quality(latest_json: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(latest_json, dict):
        return {}
    quality = latest_json.get("quality") if isinstance(latest_json.get("quality"), dict) else {}
    final = quality.get("final") if isinstance(quality.get("final"), dict) else {}
    review = final.get("content_quality") if isinstance(final.get("content_quality"), dict) else {}
    if not review and isinstance(quality.get("content_quality"), dict):
        review = quality.get("content_quality")
    return review if isinstance(review, dict) else {}


def content_quality_review_binding_is_current(brief: dict[str, Any], review: dict[str, Any] | None) -> bool:
    if not isinstance(brief, dict) or not isinstance(review, dict):
        return False
    checks = review.get("checks") if isinstance(review.get("checks"), dict) else {}
    current = current_fact_review_binding(brief)
    for key in _BINDING_KEYS:
        stored_value = str(checks.get(key) or "")
        current_value = str(current.get(key) or "")
        if not stored_value or stored_value != current_value:
            return False
    scores = review.get("scores") if isinstance(review.get("scores"), dict) else {}
    if not all(key in scores for key in _REQUIRED_SCORE_KEYS):
        return False
    return True


def get_bound_stored_content_quality(
    latest_json: dict[str, Any] | None,
    brief: dict[str, Any],
) -> dict[str, Any] | None:
    review = _stored_content_quality(latest_json)
    if not content_quality_review_binding_is_current(brief, review):
        return None
    reused = copy.deepcopy(review)
    checks = dict(reused.get("checks") or {}) if isinstance(reused.get("checks"), dict) else {}
    checks["morning_review_reused"] = True
    checks["morning_review_reuse_reason"] = "stored_content_quality_binding_current"
    reused["checks"] = checks
    return reused


def validate_live_content_quality_review(review: dict[str, Any]) -> dict[str, Any]:
    """Turn malformed reviewer JSON into an infrastructure error, not fake zero scores."""
    if not isinstance(review, dict):
        return _reviewer_error("内容质量审稿返回了非对象结果。")
    if any(str(issue.get("code") or "") == "content_quality_reviewer_error" for issue in review.get("issues") or [] if isinstance(issue, dict)):
        return review

    raw = review.get("raw_review")
    if not isinstance(raw, dict):
        # Mock/disabled paths intentionally have no raw review and already carry a
        # complete normalized contract.
        scores = review.get("scores") if isinstance(review.get("scores"), dict) else {}
        if all(key in scores for key in _REQUIRED_SCORE_KEYS) or str(review.get("status") or "") == "skipped":
            return review
        return _reviewer_error("内容质量审稿缺少原始审核结果或完整 scores。")

    raw_scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
    missing = [key for key in _REQUIRED_SCORE_KEYS if key not in raw_scores]
    if missing:
        return _reviewer_error("内容质量审稿返回的 scores 不完整，缺少：" + "、".join(missing))
    return review


def _reviewer_error(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "fail",
        "score": 0,
        "risk_level": "high",
        "can_send": False,
        "scores": {},
        "checks": {"malformed_review": True},
        "issues": [
            {
                "severity": "high",
                "code": "content_quality_reviewer_error",
                "message": message,
            }
        ],
        "rewrite_suggestions": [],
        "rewrite_targets": [],
        "needs_manual_full_review": True,
        "one_sentence_judgment": "内容质量审稿返回结构异常，不能据此判断内容质量。",
    }
