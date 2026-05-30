from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

from config import settings
from daily_archive import put_oss_object
from history import oss_config, oss_url


TZ = dt.timezone(dt.timedelta(hours=8))
WEEKLY_PDF_TRACKING_PLACEHOLDER_PREFIX = "__WEEKLY_PDF_TRACKING_URL__:"
WEEKLY_PDF_TRACKING_PLACEHOLDER_SUFFIX = ":__END_WEEKLY_PDF_TRACKING_URL__"


def _secret() -> str:
    return settings.download_tracking_secret.strip()


def _base_url() -> str:
    return (settings.download_tracking_base_url or settings.feedback_base_url).strip()


def _canonical_week(week_key: str) -> str:
    return "".join(ch for ch in str(week_key or "").strip() if ch.isdigit() or ch in {"-", "_", "t", "o"})[:64]


def _sign_payload(week: str, rid: str, pdf_key: str) -> str:
    secret = _secret()
    if not secret:
        return ""
    payload = f"weekly_pdf_download|{week}|{rid}|{pdf_key}"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _rid_for_email(recipient_email: str) -> str:
    secret = _secret()
    normalized = str(recipient_email or "").strip().lower()
    if not secret:
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return hmac.new(secret.encode("utf-8"), f"rid|{normalized}".encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _pdf_key_from_url(pdf_url: str) -> str:
    value = str(pdf_url or "").strip()
    if not value:
        return ""
    cfg = oss_config()
    bucket = cfg.get("bucket", "").strip()
    if value.startswith("oss://"):
        bucket_and_key = value[len("oss://"):]
        parsed_bucket, _, key = bucket_and_key.partition("/")
        if bucket and parsed_bucket and parsed_bucket != bucket:
            return ""
        return key.strip().lstrip("/")
    if "://" not in value:
        return value.strip().lstrip("/")
    parsed = urlparse(value)
    host = parsed.netloc.split("@")[-1].split(":")[0]
    endpoint = cfg.get("endpoint", "").replace("https://", "").replace("http://", "").strip().rstrip("/")
    allowed_hosts = {f"{bucket}.{endpoint}"} if bucket and endpoint else set()
    if bucket:
        allowed_hosts.add(f"{bucket}.oss-cn-hangzhou.aliyuncs.com")
    if allowed_hosts and host not in allowed_hosts:
        return ""
    return parsed.path.lstrip("/")


def _pdf_url_from_key(pdf_key: str) -> str:
    key = str(pdf_key or "").strip().lstrip("/")
    if not key:
        return ""
    cfg = oss_config()
    if not cfg.get("bucket") or not cfg.get("endpoint"):
        return ""
    cfg["object_key"] = key
    return oss_url(cfg)


def build_weekly_pdf_tracking_url(pdf_url: str, week_key: str, recipient_email: str) -> str:
    """Build a signed tracking URL for one weekly PDF recipient.

    The recipient email is never included in the URL. It is converted to an
    HMAC-based rid, and the redirect target is represented by a signed OSS key
    rather than an arbitrary URL.
    """
    base_url = _base_url()
    pdf_key = _pdf_key_from_url(pdf_url)
    week = _canonical_week(week_key)
    rid = _rid_for_email(recipient_email)
    sig = _sign_payload(week, rid, pdf_key)
    if not base_url or not pdf_key or not week or not rid or not sig:
        return str(pdf_url or "")
    separator = "&" if "?" in base_url else "?"
    query = urlencode(
        {
            "task": "weekly_pdf_download",
            "week": week,
            "rid": rid,
            "key": pdf_key,
            "sig": sig,
        },
        quote_via=quote,
    )
    return f"{base_url}{separator}{query}"


def build_weekly_pdf_tracking_placeholder(pdf_url: str, week_key: str) -> str:
    payload = json.dumps({"pdf_url": str(pdf_url or ""), "week": _canonical_week(week_key)}, ensure_ascii=False, separators=(",", ":"))
    return f"{WEEKLY_PDF_TRACKING_PLACEHOLDER_PREFIX}{quote(payload, safe='')}{WEEKLY_PDF_TRACKING_PLACEHOLDER_SUFFIX}"


def replace_weekly_pdf_tracking_placeholders(text: str, recipient_email: str) -> str:
    value = str(text or "")
    prefix = WEEKLY_PDF_TRACKING_PLACEHOLDER_PREFIX
    suffix = WEEKLY_PDF_TRACKING_PLACEHOLDER_SUFFIX
    while prefix in value:
        start = value.find(prefix)
        end = value.find(suffix, start + len(prefix))
        if end < 0:
            break
        token = value[start + len(prefix):end]
        replacement = ""
        try:
            from urllib.parse import unquote

            payload = json.loads(unquote(token))
            if isinstance(payload, dict):
                replacement = build_weekly_pdf_tracking_url(
                    str(payload.get("pdf_url") or ""),
                    str(payload.get("week") or ""),
                    recipient_email,
                )
        except Exception:
            replacement = ""
        value = value[:start] + replacement + value[end + len(suffix):]
    return value


def _query_params(event: Any) -> dict[str, str]:
    payload = event if isinstance(event, dict) else {}
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


def is_weekly_pdf_download_invocation(event: Any) -> bool:
    params = _query_params(event)
    task = params.get("task", "").strip().lower()
    mode = params.get("mode", "").strip().lower()
    return task == "weekly_pdf_download" or mode == "weekly_pdf_download"


def _header_value(event: Any, *names: str) -> str:
    payload = event if isinstance(event, dict) else {}
    headers = {}
    for key in ("headers", "httpHeaders"):
        if isinstance(payload.get(key), dict):
            headers.update(payload[key])
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return ""


def _write_click_log(row: dict[str, Any]) -> None:
    today = dt.datetime.now(TZ).date().isoformat()
    week = _canonical_week(str(row.get("week") or "")) or "unknown-week"
    rid = str(row.get("rid") or "unknown-rid")[:32]
    stamp = dt.datetime.now(TZ).strftime("%H%M%S%f")
    object_key = f"{settings.download_tracking_prefix}/{today}/{week}-{rid}-{stamp}-{secrets.token_hex(4)}.json"
    body = json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    result = put_oss_object(object_key, body, "application/json; charset=utf-8")
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error") or "OSS click log write failed"))


def handle_weekly_pdf_download(event: Any) -> dict[str, Any]:
    params = _query_params(event)
    week = _canonical_week(params.get("week", ""))
    rid = str(params.get("rid") or "").strip()
    pdf_key = _pdf_key_from_url(params.get("key", ""))
    sig = str(params.get("sig") or "").strip()
    expected = _sign_payload(week, rid, pdf_key)
    if not week or not rid or not pdf_key or not expected or not hmac.compare_digest(sig, expected):
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"},
            "isBase64Encoded": False,
            "body": "Invalid weekly PDF download link.",
        }

    pdf_url = _pdf_url_from_key(pdf_key)
    if not pdf_url:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"},
            "isBase64Encoded": False,
            "body": "Weekly PDF not found.",
        }

    row = {
        "ts": dt.datetime.now(TZ).isoformat(),
        "week": week,
        "rid": rid,
        "pdf_key": pdf_key,
        "pdf_url": pdf_url,
        "user_agent": _header_value(event, "user-agent"),
    }
    try:
        _write_click_log(row)
    except Exception:
        pass
    return {
        "statusCode": 302,
        "headers": {
            "Location": pdf_url,
            "Cache-Control": "no-store",
        },
        "isBase64Encoded": False,
        "body": "",
    }
