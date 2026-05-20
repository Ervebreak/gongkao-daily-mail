from __future__ import annotations

import datetime as dt
import json
from typing import Any
from urllib.parse import parse_qs, urlencode

import requests

from config import settings
from history import oss_config, oss_headers, oss_ready, oss_url


TZ = dt.timezone(dt.timedelta(hours=8))

FEEDBACK_CHOICES = {
    "useful": "有用",
    "too_long": "太长",
    "question_good": "今日一题不错",
    "framework_good": "框架图不错",
    "sentence_good": "金句表达有用",
    "no_time": "没时间看",
}


def _normalize_event(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    if isinstance(event, (bytes, bytearray)):
        try:
            return json.loads(event.decode("utf-8"))
        except Exception:
            return {}
    if isinstance(event, str):
        try:
            return json.loads(event)
        except Exception:
            return {}
    return {}


def _query_params(event: Any) -> dict[str, str]:
    payload = _normalize_event(event)
    params: dict[str, Any] = {}

    for key in ("queryParameters", "queryStringParameters", "queries", "query"):
        value = payload.get(key)
        if isinstance(value, dict):
            params.update(value)

    raw_query = payload.get("rawQueryString") or payload.get("queryString") or ""
    if raw_query:
        parsed = parse_qs(str(raw_query), keep_blank_values=True)
        params.update({key: values[-1] if values else "" for key, values in parsed.items()})

    # 兼容 FC 测试事件：直接把 query 参数放在 event 顶层。
    params.update({key: value for key, value in payload.items() if isinstance(value, (str, int, float, bool))})
    return {str(key): str(value) for key, value in params.items()}


def _headers_from_event(event: Any) -> dict[str, str]:
    payload = _normalize_event(event)
    headers: dict[str, str] = {}
    for key in ("headers", "httpHeaders"):
        value = payload.get(key)
        if isinstance(value, dict):
            headers.update({str(k).lower(): str(v) for k, v in value.items()})
    return headers


def _request_base_url(event: Any) -> str:
    """尽量从 HTTP 事件中还原当前函数公网地址，用于跳转成功页。"""
    payload = _normalize_event(event)
    headers = _headers_from_event(event)

    proto = headers.get("x-forwarded-proto") or headers.get("x-forwarded-protocol") or "https"
    host = headers.get("host") or headers.get("x-forwarded-host") or ""

    # 一些 FC 事件可能把 path 放在不同字段里。
    path = (
        payload.get("path")
        or payload.get("rawPath")
        or payload.get("requestPath")
        or payload.get("http", {}).get("path") if isinstance(payload.get("http"), dict) else None
    )
    if not path:
        path = "/"

    if host:
        return f"{proto}://{host}{path}"

    # 兜底：用配置的反馈入口作为成功页入口。
    base = getattr(settings, "feedback_base_url", "").strip()
    if base:
        return base.split("?")[0]

    return ""


def is_feedback_invocation(event: Any) -> bool:
    params = _query_params(event)
    task = params.get("task", "").strip().lower()
    mode = params.get("mode", "").strip().lower()
    return task in {"feedback", "feedback_done", "feedback_success"} or mode in {"feedback", "feedback_done", "feedback_success"}


def _feedback_object_key(feedback_date: str) -> str:
    prefix = settings.feedback_prefix.strip().strip("/") or "gongkao-morning-mailer/feedback"
    return f"{prefix}/{feedback_date}.jsonl"


def _read_oss_text(object_key: str) -> str:
    if not oss_ready():
        return ""
    cfg = oss_config()
    response = requests.get(
        oss_url({**cfg, "object_key": object_key}),
        headers=oss_headers("GET", {**cfg, "object_key": object_key}),
        timeout=20,
    )
    if response.status_code == 404:
        return ""
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def _write_oss_text(object_key: str, text: str) -> dict[str, Any]:
    if not oss_ready():
        return {"storage": "local", "object_key": object_key, "oss_write_ok": False}
    cfg = oss_config()
    response = requests.put(
        oss_url({**cfg, "object_key": object_key}),
        data=text.encode("utf-8"),
        headers=oss_headers("PUT", {**cfg, "object_key": object_key}, "application/jsonl; charset=utf-8"),
        timeout=20,
    )
    response.raise_for_status()
    return {"storage": "oss", "object_key": object_key, "oss_write_ok": True}


def _append_feedback_record(record: dict[str, Any]) -> dict[str, Any]:
    object_key = _feedback_object_key(record["date"])
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"

    if oss_ready():
        existing = _read_oss_text(object_key)
        return _write_oss_text(object_key, existing + line)

    local_path = settings.output_dir / "feedback" / f"{record['date']}.jsonl"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("a", encoding="utf-8") as file:
        file.write(line)
    return {"storage": "local", "path": str(local_path), "oss_write_ok": False}


def _success_html(message: str = "反馈已收到，谢谢！") -> str:
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>反馈已收到</title></head>"
        "<body style=\"margin:0;background:#f7f9fc;color:#111;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;\">"
        "<div style=\"max-width:520px;margin:56px auto;padding:28px 22px;background:#fff;"
        "border:1px solid #e5eaf2;border-radius:18px;text-align:center;line-height:1.7;"
        "box-shadow:0 8px 28px rgba(15,35,70,.06);\">"
        "<div style=\"font-size:40px;margin-bottom:10px;\">✅</div>"
        f"<h2 style=\"font-size:22px;margin:0 0 12px;color:#1f4fd8;\">{message}</h2>"
        "<p style=\"font-size:15px;margin:0;color:#5d6b82;\">你可以关闭这个页面，或返回邮件继续阅读。</p>"
        "</div></body></html>"
    )


def _html_response(message: str = "反馈已收到，谢谢！") -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {
            "Cache-Control": "no-store",
            "Content-Type": "text/html; charset=utf-8",
            "Content-Disposition": "inline",
        },
        "isBase64Encoded": False,
        "body": _success_html(message),
    }


def _redirect_response(location: str) -> dict[str, Any]:
    return {
        "statusCode": 302,
        "headers": {
            "Location": location,
            "Cache-Control": "no-store",
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Disposition": "inline",
        },
        "isBase64Encoded": False,
        "body": "",
    }


def _success_url(event: Any) -> str:
    # 可选：如果你以后配置 FEEDBACK_SUCCESS_URL，则优先跳转到该静态成功页。
    configured = getattr(settings, "feedback_success_url", "").strip() if hasattr(settings, "feedback_success_url") else ""
    if configured:
        return configured

    base_url = _request_base_url(event)
    if base_url:
        query = urlencode({"task": "feedback_done"})
        return f"{base_url}?{query}"

    # 极端兜底：如果无法还原 host，就直接返回 HTML。
    return ""


def handle_feedback(event: Any) -> dict[str, Any]:
    params = _query_params(event)
    task = params.get("task", "").strip().lower()

    # 成功页：只展示页面，不再记录反馈，避免重定向后重复写入。
    if task in {"feedback_done", "feedback_success"} or params.get("mode", "").strip().lower() in {"feedback_done", "feedback_success"}:
        return _html_response()

    today = dt.datetime.now(TZ).strftime("%Y-%m-%d")
    feedback_date = params.get("date", "").strip() or today
    choice = params.get("choice", "").strip()

    if choice in FEEDBACK_CHOICES:
        record = {
            "date": feedback_date,
            "choice": choice,
            "uid": params.get("uid", "").strip(),
            "email_hash": params.get("email_hash", "").strip(),
            "choice_label": FEEDBACK_CHOICES[choice],
            "mail_id": params.get("mail_id", "").strip() or feedback_date,
            "ts": dt.datetime.now(TZ).isoformat(timespec="seconds"),
            "ua": _headers_from_event(event).get("user-agent", ""),
        }
        try:
            _append_feedback_record(record)
        except Exception:
            # 不让用户因为 OSS 写入失败看到错误页；后台日志可另行排查。
            pass

    location = _success_url(event)
    if location:
        return _redirect_response(location)

    return _html_response()
