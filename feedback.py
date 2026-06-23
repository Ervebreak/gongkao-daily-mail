from __future__ import annotations

import datetime as dt
import csv
import hashlib
import io
import json
from pathlib import Path
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
    feedback_tasks = {"feedback", "feedback_done", "feedback_success", "unsubscribe", "unsubscribe_done"}
    return task in feedback_tasks or mode in feedback_tasks


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


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


def _fallback_uid(email: str) -> str:
    return f"u_{_email_hash(email)[:10]}"


def _subscriber_object_key() -> str:
    return settings.subscribers_oss_key.strip().lstrip("/") or "gongkao-morning-mailer/subscribers.csv"


def _read_subscribers_text() -> tuple[str, str]:
    if settings.subscribers_storage == "oss" and oss_ready():
        object_key = _subscriber_object_key()
        return _read_oss_text(object_key), f"OSS:{object_key}"

    path = settings.output_dir.parent / "subscribers.csv"
    package_path = Path(__file__).with_name("subscribers.csv")
    if package_path.exists():
        return package_path.read_text(encoding="utf-8-sig"), str(package_path)
    if path.exists():
        return path.read_text(encoding="utf-8-sig"), str(path)
    return "", str(package_path)


def _write_subscribers_text(text: str, source: str) -> dict[str, Any]:
    if source.startswith("OSS:"):
        object_key = source.split(":", 1)[1]
        if not oss_ready():
            return {"storage": "local", "object_key": object_key, "oss_write_ok": False}
        cfg = oss_config()
        response = requests.put(
            oss_url({**cfg, "object_key": object_key}),
            data=text.encode("utf-8-sig"),
            headers=oss_headers("PUT", {**cfg, "object_key": object_key}, "text/csv; charset=utf-8"),
            timeout=20,
        )
        response.raise_for_status()
        return {"storage": "oss", "object_key": object_key, "oss_write_ok": True}

    path = Path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig")
    return {"storage": "local", "path": str(path), "oss_write_ok": False}


def _unsubscribe_recipient(uid: str, email_hash: str) -> dict[str, Any]:
    uid = uid.strip()
    email_hash = email_hash.strip().lower()
    if not uid and not email_hash:
        return {"updated": False, "reason": "missing_identity"}
    if uid == "bcc":
        return {"updated": False, "reason": "bcc_no_identity"}

    csv_text, source = _read_subscribers_text()
    if not csv_text.strip():
        return {"updated": False, "reason": "subscribers_not_found", "source": source}

    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    fieldnames = list(reader.fieldnames or [])
    if "email" not in fieldnames:
        return {"updated": False, "reason": "missing_email_column", "source": source}
    if "status" not in fieldnames:
        fieldnames.append("status")
    if "uid" not in fieldnames:
        fieldnames.append("uid")
    if "email_hash" not in fieldnames:
        fieldnames.append("email_hash")

    matched = False
    matched_email = ""
    for row in rows:
        email = (row.get("email") or "").strip()
        row_uid = (row.get("uid") or "").strip() or (_fallback_uid(email) if email else "")
        row_hash = (row.get("email_hash") or "").strip().lower() or (_email_hash(email) if email else "")
        row["uid"] = row_uid
        row["email_hash"] = row_hash
        if (uid and row_uid == uid) or (email_hash and row_hash == email_hash):
            row["status"] = "inactive"
            matched = True
            matched_email = email

    if not matched:
        return {"updated": False, "reason": "not_matched", "source": source}

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_result = _write_subscribers_text(buffer.getvalue(), source)
    return {"updated": True, "source": source, "email": matched_email, **write_result}


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

    if task == "unsubscribe":
        uid = params.get("uid", "").strip()
        email_hash = params.get("email_hash", "").strip()
        try:
            unsubscribe_result = _unsubscribe_recipient(uid, email_hash)
        except Exception as exc:
            unsubscribe_result = {"updated": False, "reason": "error", "error": str(exc)}

        record = {
            "date": feedback_date,
            "choice": "unsubscribe",
            "choice_label": "退订",
            "mail_id": params.get("mail_id", "").strip() or feedback_date,
            "uid": uid,
            "email_hash": email_hash,
            "unsubscribe": unsubscribe_result,
            "ts": dt.datetime.now(TZ).isoformat(timespec="seconds"),
            "ua": _headers_from_event(event).get("user-agent", ""),
        }
        try:
            _append_feedback_record(record)
        except Exception:
            pass

        if unsubscribe_result.get("updated"):
            return _html_response("退订已生效")
        return _html_response("退订请求已收到")

    choice = params.get("choice", "").strip()

    if choice in FEEDBACK_CHOICES:
        record = {
            "date": feedback_date,
            "choice": choice,
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
