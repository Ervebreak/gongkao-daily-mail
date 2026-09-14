from __future__ import annotations

import base64
import datetime as dt
import hmac
import json
import os
from typing import Any

import candidate_store
from config import settings
from email_renderer import render_email_html, render_plain_text
from fact_evidence import fact_review_binding_is_current


EXPECTED_REQUEST_KEYS = frozenset({"candidate"})
EXPECTED_SCORE_DETAIL = {
    "exam_conversion": 30,
    "problem_awareness": 20,
    "scenario_specificity": 15,
    "contradiction_tension": 15,
    "material_value": 10,
    "authority_timeliness": 10,
}


class DailyPublishError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _json_response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
        },
        "isBase64Encoded": False,
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _blocked_response(error: DailyPublishError) -> dict[str, Any]:
    return _json_response(
        error.http_status,
        {
            "status": "blocked",
            "issue_code": error.code,
            "message": error.message,
        },
    )


def _headers(event: Any) -> dict[str, str]:
    if not isinstance(event, dict) or not isinstance(event.get("headers"), dict):
        return {}
    return {str(key).lower(): str(value) for key, value in event["headers"].items()}


def _event_object(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    if isinstance(event, (bytes, bytearray)):
        try:
            event = event.decode("utf-8")
        except UnicodeDecodeError:
            return {}
    if isinstance(event, str):
        try:
            parsed = json.loads(event)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _authorized(event: Any) -> bool:
    expected = os.environ.get("DAILY_PUBLISH_TOKEN", "")
    if not expected:
        return False
    authorization = _headers(event).get("authorization", "")
    scheme, separator, supplied = authorization.partition(" ")
    return bool(
        separator
        and scheme.lower() == "bearer"
        and supplied
        and hmac.compare_digest(supplied, expected)
    )


def _request_payload(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise DailyPublishError("daily_candidate_input_invalid", "Request event must be an object.")
    raw: Any = event.get("body", event)
    if event.get("isBase64Encoded") is True:
        if not isinstance(raw, str):
            raise DailyPublishError("daily_candidate_input_invalid", "Base64 request body must be a string.")
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except Exception as exc:
            raise DailyPublishError("daily_candidate_input_invalid", "Request body is not valid base64 UTF-8.") from exc
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DailyPublishError("daily_candidate_input_invalid", "Request body must be UTF-8.") from exc
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DailyPublishError("daily_candidate_input_invalid", "Request body is not valid JSON.") from exc
    if not isinstance(raw, dict):
        raise DailyPublishError("daily_candidate_input_invalid", "Request body must be a JSON object.")
    missing = sorted(EXPECTED_REQUEST_KEYS - raw.keys())
    unknown = sorted(raw.keys() - EXPECTED_REQUEST_KEYS)
    if missing or unknown:
        detail: list[str] = []
        if missing:
            detail.append(f"missing keys: {', '.join(missing)}")
        if unknown:
            detail.append(f"unknown keys: {', '.join(unknown)}")
        raise DailyPublishError("daily_candidate_input_invalid", "; ".join(detail))
    return raw


def _iso_date(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 10:
        raise DailyPublishError("daily_candidate_date_invalid", f"{label} must use YYYY-MM-DD.")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise DailyPublishError("daily_candidate_date_invalid", f"{label} must be a valid date.") from exc
    if parsed.isoformat() != value:
        raise DailyPublishError("daily_candidate_date_invalid", f"{label} must use YYYY-MM-DD.")
    return parsed.isoformat()


def _require_object(container: dict[str, Any], key: str) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        raise DailyPublishError("daily_candidate_input_invalid", f"candidate.{key} must be a JSON object.")
    return value


def _validate_quality_state(candidate: dict[str, Any]) -> dict[str, Any]:
    quality = _require_object(candidate, "quality")
    top_gate = _require_object(candidate, "quality_gate")
    nested_gate = quality.get("gate")
    if not isinstance(nested_gate, dict):
        raise DailyPublishError(
            "daily_candidate_quality_state_drift",
            "candidate.quality.gate is missing or invalid.",
        )
    if top_gate != nested_gate:
        raise DailyPublishError(
            "daily_candidate_quality_state_drift",
            "candidate.quality_gate does not match candidate.quality.gate.",
        )
    normalized = candidate_store.normalize_candidate_quality_state(candidate)
    gate = normalized.get("quality_gate") if isinstance(normalized.get("quality_gate"), dict) else {}
    if gate.get("overall") != "ok" or int(gate.get("p0_count") or 0) != 0:
        raise DailyPublishError(
            "daily_candidate_quality_blocked",
            "Candidate quality gate is not publishable.",
        )
    consistency = normalized.get("quality_state_consistency")
    if not isinstance(consistency, dict) or consistency.get("quality_gate_synced") is not True:
        raise DailyPublishError(
            "daily_candidate_quality_state_drift",
            "Candidate quality gate state is not synchronized.",
        )
    return normalized


def _validate_source_evidence(candidate: dict[str, Any], brief: dict[str, Any]) -> None:
    top = candidate.get("source_evidence")
    embedded = brief.get("_source_evidence")
    if not isinstance(top, dict) or not isinstance(embedded, dict) or not top or not embedded:
        raise DailyPublishError(
            "daily_candidate_source_evidence_invalid",
            "Verified source evidence is required.",
        )
    if top != embedded:
        raise DailyPublishError(
            "daily_candidate_source_evidence_invalid",
            "Top-level source_evidence does not match brief._source_evidence.",
        )
    items = top.get("items")
    if not isinstance(items, dict) or not items:
        raise DailyPublishError(
            "daily_candidate_source_evidence_invalid",
            "Source evidence contains no verified articles.",
        )
    if top.get("all_verified") is not True:
        raise DailyPublishError(
            "daily_candidate_source_evidence_invalid",
            "Source evidence is not fully verified.",
        )
    if any(not isinstance(item, dict) or item.get("verification_status") != "verified" for item in items.values()):
        raise DailyPublishError(
            "daily_candidate_source_evidence_invalid",
            "Every source evidence item must be verified.",
        )


def _validate_fact_review(candidate: dict[str, Any], brief: dict[str, Any]) -> None:
    top = candidate.get("fact_review")
    embedded = brief.get("_fact_review")
    if not isinstance(top, dict) or not isinstance(embedded, dict) or not top or not embedded:
        raise DailyPublishError(
            "daily_candidate_fact_review_invalid",
            "A completed fact review is required.",
        )
    if top != embedded:
        raise DailyPublishError(
            "daily_candidate_fact_review_stale",
            "Top-level fact_review does not match brief._fact_review.",
        )
    if top.get("ok") is not True or top.get("status") != "ok":
        raise DailyPublishError(
            "daily_candidate_fact_review_invalid",
            "Fact review is not in final ok state.",
        )
    if not fact_review_binding_is_current(brief, top):
        raise DailyPublishError(
            "daily_candidate_fact_review_stale",
            "Fact review binding does not match the submitted candidate.",
        )


def _authoritative_selection_featured(brief: dict[str, Any]) -> dict[str, Any]:
    two_stage = brief.get("_llm_two_stage") if isinstance(brief.get("_llm_two_stage"), dict) else {}
    selection = two_stage.get("selection") if isinstance(two_stage.get("selection"), dict) else {}
    featured = selection.get("featured") if isinstance(selection.get("featured"), dict) else {}
    if not featured:
        raise DailyPublishError(
            "daily_candidate_selection_score_invalid",
            "Authoritative featured selection metadata is missing.",
        )
    return featured


def _score_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise DailyPublishError("daily_candidate_selection_score_invalid", f"{label} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DailyPublishError("daily_candidate_selection_score_invalid", f"{label} must be an integer.") from exc
    return parsed


def _validate_selection_score(brief: dict[str, Any]) -> None:
    featured = _authoritative_selection_featured(brief)
    detail = featured.get("score_detail")
    if not isinstance(detail, dict):
        raise DailyPublishError(
            "daily_candidate_selection_score_invalid",
            "Featured selection score_detail is missing.",
        )
    computed = 0
    for key, maximum in EXPECTED_SCORE_DETAIL.items():
        if key not in detail:
            raise DailyPublishError(
                "daily_candidate_selection_score_invalid",
                f"Featured selection score_detail is missing {key}.",
            )
        value = _score_int(detail.get(key), f"score_detail.{key}")
        if value < 0 or value > maximum:
            raise DailyPublishError(
                "daily_candidate_selection_score_invalid",
                f"score_detail.{key} is outside the allowed range.",
            )
        computed += value
    total = _score_int(featured.get("total_score"), "total_score")
    if total != computed:
        raise DailyPublishError(
            "daily_candidate_selection_score_invalid",
            "Featured selection total_score does not equal the six score dimensions.",
        )
    if total < 75:
        raise DailyPublishError(
            "daily_candidate_selection_score_invalid",
            "Featured selection total_score is below the publish threshold.",
        )


def _validate_render_snapshots(candidate: dict[str, Any], brief: dict[str, Any]) -> None:
    stored_plain = candidate.get("plain_text")
    stored_html = candidate.get("html_body")
    if not isinstance(stored_plain, str) or not isinstance(stored_html, str):
        raise DailyPublishError(
            "daily_candidate_render_drift",
            "Stored Full render snapshots are missing.",
        )
    try:
        expected_plain = render_plain_text(brief)
        expected_html = render_email_html(brief)
    except Exception as exc:
        raise DailyPublishError(
            "daily_candidate_render_drift",
            "Final brief could not be deterministically rendered.",
        ) from exc
    if stored_plain != expected_plain or stored_html != expected_html:
        raise DailyPublishError(
            "daily_candidate_render_drift",
            "Stored Full render snapshots do not match the final brief.",
        )


def _validate_candidate(candidate: Any) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise DailyPublishError("daily_candidate_input_invalid", "candidate must be a JSON object.")
    for key in ("schema_version", "delivery_date", "subject", "brief", "plain_text", "html_body", "quality", "quality_gate", "source_evidence", "fact_review"):
        if key not in candidate:
            raise DailyPublishError("daily_candidate_input_invalid", f"candidate.{key} is required.")
    if candidate.get("schema_version") != 1:
        raise DailyPublishError("daily_candidate_input_invalid", "Unsupported candidate schema_version.")
    if not isinstance(candidate.get("subject"), str) or not str(candidate.get("subject") or "").strip():
        raise DailyPublishError("daily_candidate_input_invalid", "candidate.subject is required.")
    delivery_date = _iso_date(candidate.get("delivery_date"), "candidate.delivery_date")
    brief = _require_object(candidate, "brief")
    brief_date = _iso_date(brief.get("date"), "candidate.brief.date")
    if delivery_date != brief_date:
        raise DailyPublishError(
            "daily_candidate_date_mismatch",
            "candidate.delivery_date does not match candidate.brief.date.",
        )
    normalized = _validate_quality_state(candidate)
    brief = normalized.get("brief") if isinstance(normalized.get("brief"), dict) else brief
    _validate_source_evidence(normalized, brief)
    _validate_fact_review(normalized, brief)
    _validate_selection_score(brief)
    _validate_render_snapshots(normalized, brief)
    return normalized


def _validate_not_stale(candidate: dict[str, Any]) -> None:
    incoming = _iso_date(candidate.get("delivery_date"), "candidate.delivery_date")
    try:
        latest, _meta = candidate_store.load_candidate()
    except Exception as exc:
        raise DailyPublishError(
            "daily_candidate_stale_check_failed",
            "Current latest candidate could not be checked safely.",
            http_status=503,
        ) from exc
    if not latest:
        return
    latest_date = latest.get("delivery_date") if isinstance(latest, dict) else None
    if latest_date in (None, ""):
        raise DailyPublishError(
            "daily_candidate_stale_check_failed",
            "Current latest candidate has no delivery_date.",
            http_status=503,
        )
    current = _iso_date(latest_date, "latest.delivery_date")
    if incoming < current:
        raise DailyPublishError(
            "daily_candidate_stale_publish_rejected",
            "An older candidate cannot replace the current latest candidate.",
            http_status=409,
        )


def _publish(candidate: dict[str, Any]) -> dict[str, Any]:
    if settings.candidate_storage != "oss":
        raise DailyPublishError(
            "daily_candidate_storage_invalid",
            "CANDIDATE_STORAGE must be set to oss for this publisher.",
            http_status=503,
        )
    try:
        result = candidate_store.save_candidate(candidate)
    except Exception as exc:
        raise DailyPublishError(
            "daily_candidate_save_failed",
            "Candidate could not be saved.",
            http_status=502,
        ) from exc
    if result.get("candidate_saved") is not True:
        raise DailyPublishError(
            "daily_candidate_save_failed",
            "Candidate save did not complete.",
            http_status=502,
        )
    if result.get("candidate_oss_write_ok") is not True:
        raise DailyPublishError(
            "daily_candidate_oss_write_failed",
            "Daily candidate OSS write failed.",
            http_status=502,
        )
    if result.get("candidate_oss_latest_write_ok") is not True:
        raise DailyPublishError(
            "daily_candidate_latest_write_failed",
            "Latest candidate OSS write failed.",
            http_status=502,
        )
    delivery_date = str(candidate.get("delivery_date") or "")
    return {
        "status": "published",
        "delivery_date": delivery_date,
        "candidate_saved": True,
        "candidate_storage": "oss",
        "daily_write_ok": True,
        "latest_write_ok": True,
        "daily_path": str(result.get("candidate_oss_path") or f"oss://{settings.oss_bucket}/{candidate_store.candidate_object_key(delivery_date)}"),
        "latest_path": f"oss://{settings.oss_bucket}/{candidate_store.latest_object_key()}",
    }


def handler(event: Any, context: Any) -> dict[str, Any]:
    del context
    envelope = _event_object(event)
    if not _authorized(envelope):
        return _blocked_response(
            DailyPublishError(
                "daily_publish_auth_failed",
                "Unauthorized.",
                http_status=401,
            )
        )
    try:
        payload = _request_payload(envelope)
        candidate = _validate_candidate(payload["candidate"])
        _validate_not_stale(candidate)
        published = _publish(candidate)
        return _json_response(200, published)
    except DailyPublishError as exc:
        return _blocked_response(exc)
    except Exception:
        return _blocked_response(
            DailyPublishError(
                "daily_candidate_publish_failed",
                "Candidate publish failed.",
                http_status=500,
            )
        )
