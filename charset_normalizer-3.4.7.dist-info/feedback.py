from __future__ import annotations

import datetime as dt
import json
from typing import Any
from urllib.parse import parse_qs

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
    params.update({key: value for key, value in payload.items() if isinstance(value, (str, int, float, bool))})
    return {str(key): str(value) for key, value in params.items()}


def is_feedback_invocation(event: Any) -> bool:
    params = _query_params(event)
    task = params.get("task", "").strip().lower()
    mode = params.get("mode", "").strip().lower()
    return task == "feedback" or mode == "feedback"


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


def _html_response(message: str = "反馈已收到，谢谢！") -> dict[str, Any]:
    """Return a real HTTP HTML response for FC HTTP trigger.

    Do NOT return a JSON string here. Returning a JSON-encoded response object
    can make mobile browsers treat the result as a downloadable .html file.
    """
    html = (
        "<!doctype html>"
        "<html lang=\"zh-CN\">"
        "<head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1\">"
        "<title>反馈已收到</title>"
        "</head>"
        "<body style=\"margin:0;background:#f8fafc;color:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;\">"
        "<main style=\"max-width:520px;margin:0 auto;padding:42px 22px;\">"
        "<section style=\"background:#fff;border:1px solid #e2e8f0;border-radius:18px;padding:26px 22px;box-shadow:0 8px 24px rgba(15,23,42,0.06);\">"
        "<div style=\"font-size:34px;line-height:1;margin-bottom:14px;\">✓</div>"
        f"<h1 style=\"font-size:22px;line-height:1.4;margin:0 0 12px;font-weight:800;\">{message}</h1>"
        "<p style=\"font-size:15px;line-height:1.8;color:#475569;margin:0;\">你可以关闭这个页面，或返回邮件继续阅读。若想反馈多个选项，可以返回邮件后再点其他按钮。</p>"
        "</section>"
        "</main>"
        "</body></html>"
    )
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "content-type": "text/html; charset=utf-8",
            "Content-Disposition": "inline; filename=feedback.html",
            "content-disposition": "inline; filename=feedback.html",
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
        "isBase64Encoded": False,
        "body": html,
    }


def handle_feedback(event: Any) -> str:
    params = _query_params(event)
    today = dt.datetime.now(TZ).strftime("%Y-%m-%d")
    feedback_date = params.get("date", "").strip() or today
    choice = params.get("choice", "").strip()
    if choice not in FEEDBACK_CHOICES:
        return _html_response()

    record = {
        "date": feedback_date,
        "choice": choice,
        "choice_label": FEEDBACK_CHOICES[choice],
        "mail_id": params.get("mail_id", "").strip() or feedback_date,
        "ts": dt.datetime.now(TZ).isoformat(timespec="seconds"),
    }
    try:
        _append_feedback_record(record)
    except Exception:
        # Do not expose storage errors to the user; the click should still land on
        # a normal HTML page instead of an error/download prompt. Check FC logs if needed.
        return _html_response("反馈已收到")
    return _html_response()
