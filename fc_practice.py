from __future__ import annotations

import base64
import datetime as dt
import json
import os
from typing import Any

import candidate_store
from config import settings
from practice_coach import evaluate_with_api
from practice_demo import DEFAULT_MAX_REVIEWS, MAX_REQUEST_BYTES, PracticeDemoApp, build_mock_feedback
from practice_links import PracticeLinkError, verify_token
from practice_store import OssAttemptStore, PracticeStorageError


class PracticeRequestError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


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
            value = json.loads(event)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def _request_method(event: dict[str, Any]) -> str:
    context = event.get("requestContext") if isinstance(event.get("requestContext"), dict) else {}
    http = context.get("http") if isinstance(context.get("http"), dict) else {}
    return str(http.get("method") or event.get("httpMethod") or event.get("method") or "GET").upper()


def _request_path(event: dict[str, Any]) -> str:
    context = event.get("requestContext") if isinstance(event.get("requestContext"), dict) else {}
    http = context.get("http") if isinstance(context.get("http"), dict) else {}
    path = str(event.get("rawPath") or event.get("path") or http.get("path") or "/")
    return path.split("?", 1)[0]


def _request_body(event: dict[str, Any]) -> bytes:
    raw = event.get("body") or ""
    if isinstance(raw, str):
        if event.get("isBase64Encoded") is True:
            try:
                body = base64.b64decode(raw, validate=True)
            except Exception as exc:
                raise PracticeRequestError("practice_body_invalid", "提交内容格式无效。") from exc
        else:
            body = raw.encode("utf-8")
    elif isinstance(raw, (bytes, bytearray)):
        body = bytes(raw)
    else:
        raise PracticeRequestError("practice_body_invalid", "提交内容格式无效。")
    if len(body) > MAX_REQUEST_BYTES:
        raise PracticeRequestError("practice_body_too_large", "提交内容过长。", status=413)
    return body


def _response(status: int, content_type: str, body: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": content_type,
            "Content-Disposition": "inline",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        },
        "isBase64Encoded": False,
        "body": body,
    }


def _json_response(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    return _response(status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False))


def _secret() -> bytes:
    value = os.environ.get("PRACTICE_LINK_SECRET", "")
    if len(value.encode("utf-8")) < 32:
        raise PracticeRequestError("practice_config_invalid", "训练服务配置不完整。", status=503)
    return value.encode("utf-8")


def _max_reviews() -> int:
    try:
        value = int(os.environ.get("PRACTICE_MAX_REVIEWS", str(DEFAULT_MAX_REVIEWS)))
    except ValueError as exc:
        raise PracticeRequestError("practice_config_invalid", "训练服务配置无效。", status=503) from exc
    if value < 1 or value > 3:
        raise PracticeRequestError("practice_config_invalid", "训练服务配置无效。", status=503)
    return value


def _load_candidate_for_token(token: str) -> dict[str, Any]:
    try:
        signed = verify_token(token, secret=_secret())
        delivery_date = str(signed.get("date") or "")
        parsed = dt.date.fromisoformat(delivery_date)
        if parsed.isoformat() != delivery_date:
            raise ValueError
    except (PracticeLinkError, ValueError) as exc:
        raise PracticeRequestError("practice_link_invalid", "专属链接格式无效。", status=403) from exc
    if settings.candidate_storage != "oss":
        raise PracticeRequestError("practice_candidate_storage_invalid", "训练服务暂时不可用。", status=503)
    candidate, meta = candidate_store.load_candidate(delivery_date)
    if not candidate or meta.get("candidate_storage") != "oss":
        raise PracticeRequestError("practice_candidate_unavailable", "当天题目暂时无法读取。", status=503)
    if str(candidate.get("delivery_date") or "") != delivery_date:
        raise PracticeRequestError("practice_candidate_invalid", "当天题目尚未通过发布审核。", status=403)
    try:
        return load_practice_candidate_from_value(candidate)
    except ValueError as exc:
        raise PracticeRequestError("practice_candidate_invalid", "当天题目尚未通过发布审核。", status=403) from exc


def load_practice_candidate_from_value(candidate: dict[str, Any]) -> dict[str, Any]:
    gate = candidate.get("quality_gate") if isinstance(candidate.get("quality_gate"), dict) else {}
    if gate.get("overall") != "ok" or int(gate.get("p0_count") or 0) != 0:
        raise ValueError("candidate gate blocked")
    brief = candidate.get("brief") if isinstance(candidate.get("brief"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    if not str(question.get("question") or "").strip():
        raise ValueError("daily question missing")
    return candidate


def _build_app(candidate: dict[str, Any]) -> PracticeDemoApp:
    mode = os.environ.get("PRACTICE_COACH_MODE", "api").strip().lower()
    if mode not in {"api", "mock"}:
        raise PracticeRequestError("practice_config_invalid", "训练服务配置无效。", status=503)
    if mode == "api":
        model = os.environ.get("PRACTICE_COACH_MODEL", "").strip()
        try:
            timeout = int(os.environ.get("PRACTICE_COACH_TIMEOUT", "60"))
        except ValueError as exc:
            raise PracticeRequestError("practice_config_invalid", "训练服务配置无效。", status=503) from exc
        if timeout < 1 or timeout > 120:
            raise PracticeRequestError("practice_config_invalid", "训练服务配置无效。", status=503)
        coach = lambda points, question: evaluate_with_api(points, question, model=model, timeout=timeout)
    else:
        coach = build_mock_feedback
    try:
        store = OssAttemptStore()
    except PracticeStorageError as exc:
        raise PracticeRequestError("practice_storage_unavailable", "训练记录存储暂时不可用。", status=503) from exc
    return PracticeDemoApp(
        candidate=candidate,
        secret=_secret(),
        store=store,
        coach=coach,
        coach_name=mode,
        max_reviews=_max_reviews(),
    )


def handler(event: Any, context: Any) -> dict[str, Any]:
    del context
    envelope = _event_object(event)
    method = _request_method(envelope)
    path = _request_path(envelope)
    if path == "/healthz" and method == "GET":
        return _json_response(200, {"status": "ok", "service": "gongkao-practice"})
    if method not in {"GET", "POST"} or not path.startswith("/t/"):
        return _json_response(404, {"status": "not_found"})
    token = path[len("/t/") :]
    try:
        candidate = _load_candidate_for_token(token)
        app = _build_app(candidate)
        body = _request_body(envelope) if method == "POST" else b""
        status, content_type, response_body = app.handle(method, path, body)
        return _response(status, content_type, response_body.decode("utf-8"))
    except PracticeRequestError as exc:
        return _json_response(exc.status, {"status": "error", "code": exc.code, "message": exc.message})
    except Exception:
        return _json_response(500, {"status": "error", "code": "practice_internal_error", "message": "训练服务暂时不可用。"})
