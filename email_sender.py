from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
import smtplib
import ssl
from pathlib import Path
from typing import Any
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr, parseaddr

import requests

from config import settings
from history import oss_config, oss_headers, oss_ready, oss_url
from weekly_pdf_tracking import replace_weekly_pdf_tracking_placeholders

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
FEEDBACK_UID_PLACEHOLDER = "__FEEDBACK_UID__"
FEEDBACK_EMAIL_HASH_PLACEHOLDER = "__FEEDBACK_EMAIL_HASH__"
PAID_PLANS = {"paid_trial", "paid_monthly"}
SUBSCRIBER_BASE_FIELDS = [
    "uid",
    "email",
    "status",
    "nickname",
    "source",
    "created_at",
    "remark",
    "plan",
    "paid_until",
    "send_mode",
    "note",
    "reminder_sent",
]
FULL_VARIANTS = {"full_normal", "full_trial_d3", "full_trial_d1", "full_trial_d0"}
LITE_VARIANTS = {"free_lite", "expired_lite"}
VARIANT_BUCKET = {
    "full_normal": "full",
    "full_trial_d3": "full",
    "full_trial_d1": "full",
    "full_trial_d0": "full",
    "free_lite": "lite",
    "expired_lite": "lite",
    "skip": "skipped",
}
TRIAL_REMINDER_COPY = {
    "full_trial_d3": "【内测提醒】你的完整版体验还有 3 天到期。续费后可以继续收到每日精读、今日一题参考答案、政策坐标和周 PDF 汇编。想继续使用的话，可以直接回复本邮件。",
    "full_trial_d1": "【内测提醒】你的完整版体验明天到期。续费后可以继续收到完整版晨读邮件；如果暂时不续费，后续将停止发送完整版内容。想继续使用的话，可以直接回复本邮件。",
    "full_trial_d0": "【内测提醒】你的完整版体验今天到期。今天之后，如未续费，将不再继续发送完整版内容。想继续使用的话，可以直接回复本邮件，我会帮你处理开通。",
}
TRIAL_REMINDER_KEYS = {
    "full_trial_d3": "d3",
    "full_trial_d1": "d1",
    "full_trial_d0": "d0",
}


def build_from_header() -> str:
    # QQ SMTP is strict: the From address must be a valid mailbox and should
    # match the authenticated SMTP account. Keep the display name optional.
    mail_from = settings.mail_from or settings.smtp_user
    _, parsed_addr = parseaddr(mail_from)
    from_addr = parsed_addr if parsed_addr and "@" in parsed_addr else settings.smtp_user
    if from_addr != settings.smtp_user:
        from_addr = settings.smtp_user
    return formataddr((str(Header("公考晨读", "utf-8")), from_addr))


def normalize_recipients(raw_items: list[str]) -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        email = item.strip()
        if not email or not EMAIL_RE.match(email):
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        recipients.append(email)
    return recipients


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


def _fallback_uid(email: str, prefix: str = "u") -> str:
    return f"{prefix}_{_email_hash(email)[:10]}"


def _subscriber_fieldnames(fieldnames: list[str] | None) -> list[str]:
    ordered: list[str] = []
    for name in fieldnames or []:
        value = str(name or "").strip()
        if value and value not in ordered:
            ordered.append(value)
    for name in SUBSCRIBER_BASE_FIELDS:
        if name not in ordered:
            ordered.append(name)
    return ordered


def _normalize_record_value(value: Any) -> str:
    return str(value or "").strip()


def normalize_recipient_record(item: dict[str, Any]) -> dict[str, str]:
    normalized = {str(key): _normalize_record_value(value) for key, value in (item or {}).items() if key is not None}
    email = normalized.get("email", "").strip()
    if not email or not EMAIL_RE.match(email):
        return {}
    normalized["email"] = email
    normalized["uid"] = normalized.get("uid") or normalized.get("id") or _fallback_uid(email)
    normalized["email_hash"] = normalized.get("email_hash") or _email_hash(email)
    normalized["status"] = (normalized.get("status") or "active").strip().lower() or "active"
    normalized["plan"] = (normalized.get("plan") or "free").strip().lower() or "free"
    normalized["paid_until"] = normalized.get("paid_until", "")
    normalized["send_mode"] = (normalized.get("send_mode") or "").strip().lower()
    normalized["note"] = normalized.get("note", "")
    normalized["reminder_sent"] = normalized.get("reminder_sent", "")
    return normalized


def normalize_recipient_records(raw_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    recipients: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = normalize_recipient_record(item)
        email = normalized.get("email", "")
        if not email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        recipients.append(normalized)
    return recipients


def parse_subscribers_csv(csv_text: str) -> list[str]:
    return [item["email"] for item in parse_subscribers_csv_records(csv_text)]


def parse_subscribers_csv_table(csv_text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    source_fieldnames = [str(name or "").strip() for name in (reader.fieldnames or []) if str(name or "").strip()]
    fieldnames = _subscriber_fieldnames(reader.fieldnames)
    if not reader.fieldnames or "email" not in fieldnames:
        return {"fieldnames": fieldnames, "source_fieldnames": source_fieldnames, "records": []}
    rows: list[dict[str, str]] = []
    for row_index, row in enumerate(reader):
        record = {name: row.get(name, "") for name in fieldnames}
        record["_row_index"] = str(row_index)
        rows.append(record)
    return {"fieldnames": fieldnames, "source_fieldnames": source_fieldnames, "records": normalize_recipient_records(rows)}


def parse_subscribers_csv_all_records(csv_text: str) -> list[dict[str, str]]:
    return parse_subscribers_csv_table(csv_text).get("records", [])


def parse_subscribers_csv_records(csv_text: str) -> list[dict[str, str]]:
    return [item for item in parse_subscribers_csv_all_records(csv_text) if item.get("status") == "active"]


def load_subscribers_csv_local() -> list[str] | None:
    records = load_subscribers_csv_local_records()
    if records is None:
        return None
    return [item["email"] for item in records]


def load_subscribers_csv_local_records() -> list[dict[str, str]] | None:
    table = load_subscribers_csv_local_table()
    if table is None:
        return None
    return [item for item in table.get("records", []) if item.get("status") == "active"]


def load_subscribers_csv_oss() -> list[str] | None:
    records = load_subscribers_csv_oss_records()
    if records is None:
        return None
    return [item["email"] for item in records]


def load_subscribers_csv_oss_records() -> list[dict[str, str]] | None:
    table = load_subscribers_csv_oss_table()
    if table is None:
        return None
    return [item for item in table.get("records", []) if item.get("status") == "active"]


def load_subscribers_csv_local_all_records() -> list[dict[str, str]] | None:
    table = load_subscribers_csv_local_table()
    if table is None:
        return None
    return table.get("records")


def load_subscribers_csv_oss_all_records() -> list[dict[str, str]] | None:
    table = load_subscribers_csv_oss_table()
    if table is None:
        return None
    return table.get("records")


def load_subscribers_csv_local_table() -> dict[str, Any] | None:
    path = Path(__file__).with_name("subscribers.csv")
    if not path.exists():
        return None
    try:
        raw_text = path.read_text(encoding="utf-8-sig")
        table = parse_subscribers_csv_table(raw_text)
        table["storage"] = "local"
        table["path"] = str(path)
        table["raw_text"] = raw_text
        return table
    except Exception:
        return None


def _subscribers_oss_config(object_key: str | None = None) -> dict[str, str]:
    if settings.subscribers_storage != "oss":
        return {}
    cfg = oss_config()
    cfg["object_key"] = (object_key or settings.subscribers_oss_key).strip().lstrip("/")
    return cfg


def load_subscribers_csv_oss_table() -> dict[str, Any] | None:
    if settings.subscribers_storage != "oss":
        return None
    if not oss_ready():
        return None
    try:
        cfg = _subscribers_oss_config()
        response = requests.get(oss_url(cfg), headers=oss_headers("GET", cfg), timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        table = parse_subscribers_csv_table(response.text)
        table["storage"] = "oss"
        table["path"] = f"oss://{settings.oss_bucket}/{cfg['object_key']}"
        table["object_key"] = cfg["object_key"]
        table["raw_text"] = response.text
        return table
    except Exception:
        return None


def load_subscribers_csv() -> tuple[list[str] | None, str]:
    records, source = load_subscribers_csv_records()
    if records is None:
        return None, source
    return [item["email"] for item in records], source


def load_subscribers_csv_records() -> tuple[list[dict[str, str]] | None, str]:
    oss_recipients = load_subscribers_csv_oss_records()
    if oss_recipients is not None:
        return oss_recipients, f"OSS:{settings.subscribers_oss_key}"
    local_recipients = load_subscribers_csv_local_records()
    if local_recipients is not None:
        return local_recipients, "subscribers.csv"
    return None, "none"


def get_effective_recipients(test_mode: bool = False) -> tuple[list[str], str]:
    if test_mode:
        test_recipients = normalize_recipients(settings.test_recipients)
        if test_recipients:
            return test_recipients, "TEST_RECIPIENTS"
        # 安全兜底：测试模式没有配置 TEST_RECIPIENTS 时，不读取正式用户表，避免误发。
        return [], "TEST_RECIPIENTS_EMPTY"

    csv_recipients, csv_source = load_subscribers_csv()
    if csv_recipients is not None:
        return csv_recipients, csv_source
    raw = settings.recipients_raw.replace(";", ",").split(",")
    return normalize_recipients(raw), "RECIPIENTS"


def get_effective_recipient_records(test_mode: bool = False) -> tuple[list[dict[str, str]], str]:
    if test_mode:
        test_recipients = normalize_recipients(settings.test_recipients)
        if test_recipients:
            return normalize_recipient_records([{"email": email} for email in test_recipients]), "TEST_RECIPIENTS"
        return [], "TEST_RECIPIENTS_EMPTY"

    csv_recipients, csv_source = load_subscribers_csv_records()
    if csv_recipients is not None:
        return csv_recipients, csv_source
    raw = settings.recipients_raw.replace(";", ",").split(",")
    return normalize_recipient_records([{"email": email} for email in raw]), "RECIPIENTS"


def get_effective_recipient_records_for_segmentation(test_mode: bool = False) -> tuple[list[dict[str, str]], str]:
    if test_mode:
        test_recipients = normalize_recipients(settings.test_recipients)
        if test_recipients:
            return normalize_recipient_records([{"email": email, "plan": "paid_trial", "paid_until": "2999-12-31"} for email in test_recipients]), "TEST_RECIPIENTS"
        return [], "TEST_RECIPIENTS_EMPTY"

    oss_recipients = load_subscribers_csv_oss_all_records()
    if oss_recipients is not None:
        return oss_recipients, f"OSS:{settings.subscribers_oss_key}"
    local_recipients = load_subscribers_csv_local_all_records()
    if local_recipients is not None:
        return local_recipients, "subscribers.csv"
    raw = settings.recipients_raw.replace(";", ",").split(",")
    return normalize_recipient_records([{"email": email} for email in raw]), "RECIPIENTS"


def load_subscriber_table_for_segmentation(test_mode: bool = False) -> tuple[dict[str, Any], str]:
    if test_mode:
        test_recipients = normalize_recipients(settings.test_recipients)
        if test_recipients:
            records = normalize_recipient_records(
                [{"email": email, "plan": "paid_trial", "paid_until": "2999-12-31", "status": "active"} for email in test_recipients]
            )
            return {"records": records, "fieldnames": _subscriber_fieldnames(["email", "plan", "paid_until", "status", "reminder_sent"]), "storage": "test"}, "TEST_RECIPIENTS"
        return {"records": [], "fieldnames": _subscriber_fieldnames(["email", "reminder_sent"]), "storage": "test"}, "TEST_RECIPIENTS_EMPTY"

    oss_table = load_subscribers_csv_oss_table()
    if oss_table and oss_table.get("records") is not None:
        return oss_table, f"OSS:{settings.subscribers_oss_key}"
    local_table = load_subscribers_csv_local_table()
    if local_table and local_table.get("records") is not None:
        return local_table, "subscribers.csv"
    records = normalize_recipient_records([{"email": email} for email in settings.recipients_raw.replace(";", ",").split(",")])
    return {"records": records, "fieldnames": _subscriber_fieldnames(["email", "reminder_sent"]), "storage": "fallback"}, "RECIPIENTS"


def _parse_date(text: str) -> dt.date | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.strptime(text[:10], "%Y-%m-%d").date()
    except Exception:
        try:
            return dt.datetime.strptime(text[:10], "%Y/%m/%d").date()
        except Exception:
            return None


def _today_date(today: str | dt.date | None = None) -> dt.date:
    resolved = today if isinstance(today, dt.date) else _parse_date(str(today or ""))
    return resolved or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()


def _reminder_tokens(value: str) -> set[str]:
    return {item.strip().lower() for item in str(value or "").split("|") if item.strip()}


def _append_reminder_token(value: str, token: str) -> str:
    tokens = []
    seen: set[str] = set()
    for item in str(value or "").split("|"):
        cleaned = item.strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            tokens.append(cleaned)
    cleaned_token = str(token or "").strip().lower()
    if cleaned_token and cleaned_token not in seen:
        tokens.append(cleaned_token)
    return "|".join(tokens)


def recipient_variant(record: dict[str, str], today: str | dt.date | None = None) -> str:
    status = str(record.get("status") or "active").strip().lower() or "active"
    if status != "active":
        return "skip"
    send_mode = str(record.get("send_mode") or "").strip().lower()
    if send_mode == "none":
        return "skip"
    if send_mode == "lite":
        return "free_lite"
    plan = str(record.get("plan") or "free").strip().lower() or "free"
    today_date = _today_date(today)
    paid_until = _parse_date(str(record.get("paid_until") or ""))
    reminder_sent = _reminder_tokens(record.get("reminder_sent", ""))
    if send_mode == "full":
        if plan == "paid_trial":
            if not paid_until:
                return "full_normal"
            remaining_days = (paid_until - today_date).days
            if remaining_days < 0:
                return "expired_lite"
            if remaining_days == 3 and "d3" not in reminder_sent:
                return "full_trial_d3"
            if remaining_days == 1 and "d1" not in reminder_sent:
                return "full_trial_d1"
            if remaining_days == 0 and "d0" not in reminder_sent:
                return "full_trial_d0"
            return "full_normal"
        if plan in PAID_PLANS and paid_until and paid_until < today_date:
            return "expired_lite"
        return "full_normal"
    if plan == "free":
        return "free_lite"
    if plan == "paid_trial" and not paid_until:
        return "full_normal"
    if plan in PAID_PLANS and paid_until:
        remaining_days = (paid_until - today_date).days
        if remaining_days < 0:
            return "expired_lite"
        if plan == "paid_trial" and remaining_days == 3 and "d3" not in reminder_sent:
            return "full_trial_d3"
        if plan == "paid_trial" and remaining_days == 1 and "d1" not in reminder_sent:
            return "full_trial_d1"
        if plan == "paid_trial" and remaining_days == 0 and "d0" not in reminder_sent:
            return "full_trial_d0"
        return "full_normal"
    return "free_lite"


def recipient_delivery_tier(record: dict[str, str], today: str | dt.date | None = None) -> str:
    return VARIANT_BUCKET.get(recipient_variant(record, today=today), "skipped")


def split_recipient_records(records: list[dict[str, str]], today: str | dt.date | None = None) -> dict[str, list[dict[str, str]]]:
    today_date = _today_date(today)
    segments: dict[str, Any] = {"full": [], "lite": [], "skipped": [], "variants": {}, "variant_assignments": [], "variant_counts": {}}
    for record in normalize_recipient_records(records):
        variant = recipient_variant(record, today=today_date)
        tier = VARIANT_BUCKET.get(variant, "skipped")
        enriched = dict(record)
        enriched["variant"] = variant
        paid_until = _parse_date(str(record.get("paid_until") or ""))
        remaining_days = (paid_until - today_date).days if paid_until else ""
        reminder_key = TRIAL_REMINDER_KEYS.get(variant, "")
        enriched["days_remaining"] = str(remaining_days) if remaining_days != "" else ""
        enriched["reminder_key"] = reminder_key
        enriched["reminder_already_sent"] = "1" if reminder_key and reminder_key in _reminder_tokens(record.get("reminder_sent", "")) else ""
        segments[tier].append(enriched)
        segments["variants"].setdefault(variant, []).append(enriched)
        segments["variant_assignments"].append(
            {
                "email": enriched.get("email", ""),
                "uid": enriched.get("uid", ""),
                "variant": variant,
                "tier": tier,
                "status": enriched.get("status", ""),
                "plan": enriched.get("plan", ""),
                "send_mode": enriched.get("send_mode", ""),
                "paid_until": enriched.get("paid_until", ""),
                "days_remaining": enriched.get("days_remaining", ""),
            }
        )
    segments["variant_counts"] = {variant: len(items) for variant, items in segments["variants"].items()}
    return segments


def split_effective_recipient_records(test_mode: bool = False, today: str | dt.date | None = None) -> tuple[dict[str, list[dict[str, str]]], str]:
    table, source = load_subscriber_table_for_segmentation(test_mode=test_mode)
    return split_recipient_records(table.get("records") or [], today=today), source


def _inject_html_banner(html_body: str, text: str) -> str:
    banner = (
        '<div style="max-width:680px;margin:0 auto;padding:14px 12px 0;">'
        '<div style="background:#fff7ed;border:1px solid #fdba74;border-radius:14px;'
        'padding:14px 16px;color:#9a3412;font-size:14px;line-height:1.75;font-weight:700;">'
        f"{text}</div></div>"
    )
    if "<body" in html_body:
        match = re.search(r"<body[^>]*>", html_body, flags=re.IGNORECASE)
        if match:
            return html_body[: match.end()] + banner + html_body[match.end() :]
    return banner + html_body


def _inject_plain_banner(plain_text: str, text: str) -> str:
    return f"{text}\n\n{plain_text}"


def render_variant_email_payloads(
    subject: str,
    full_plain_text: str,
    full_html_body: str,
    lite_plain_text: str,
    lite_html_body: str,
    variants: list[str],
    *,
    enable_trial_reminders: bool = False,
) -> dict[str, dict[str, str]]:
    payloads: dict[str, dict[str, str]] = {}
    for variant in variants:
        if variant in LITE_VARIANTS:
            payloads[variant] = {"subject": subject, "plain_text": lite_plain_text, "html_body": lite_html_body}
            continue
        plain_variant = full_plain_text
        html_variant = full_html_body
        if enable_trial_reminders and variant in TRIAL_REMINDER_COPY:
            reminder_text = TRIAL_REMINDER_COPY[variant]
            plain_variant = _inject_plain_banner(plain_variant, reminder_text)
            html_variant = _inject_html_banner(html_variant, reminder_text)
        payloads[variant] = {"subject": subject, "plain_text": plain_variant, "html_body": html_variant}
    return payloads


def _subscriber_backup_object_key(base_key: str, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    if base_key.lower().endswith(".csv"):
        return f"{base_key[:-4]}.backup_{timestamp}.csv"
    return f"{base_key}.backup_{timestamp}"


def serialize_subscribers_csv(records: list[dict[str, str]], fieldnames: list[str] | None = None) -> str:
    resolved_fieldnames = _subscriber_fieldnames(fieldnames)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=resolved_fieldnames, lineterminator="\n")
    writer.writeheader()
    for record in records:
        row = {}
        for name in resolved_fieldnames:
            row[name] = str(record.get(name, "") or "")
        writer.writerow(row)
    return buffer.getvalue()


def backup_and_save_subscribers_table_to_oss(table: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "subscribers_write_ok": False,
        "subscribers_backup_ok": False,
        "subscribers_storage": "oss",
        "subscribers_path": f"oss://{settings.oss_bucket}/{settings.subscribers_oss_key}",
    }
    if settings.subscribers_storage != "oss":
        meta["subscribers_error"] = "SUBSCRIBERS_STORAGE is not oss."
        return meta
    if not oss_ready():
        meta["subscribers_error"] = "OSS config is incomplete."
        return meta
    records = normalize_recipient_records(table.get("records") or [])
    fieldnames = _subscriber_fieldnames(table.get("fieldnames") or [])
    body_text = serialize_subscribers_csv(records, fieldnames)
    body = body_text.encode("utf-8")
    backup_body = str(table.get("raw_text") or body_text).encode("utf-8")
    object_key = str(table.get("object_key") or settings.subscribers_oss_key).strip().lstrip("/")
    backup_key = _subscriber_backup_object_key(object_key)
    source_cfg = _subscribers_oss_config(object_key)
    backup_cfg = _subscribers_oss_config(backup_key)
    backup_response = requests.put(
        oss_url(backup_cfg),
        headers=oss_headers("PUT", backup_cfg, "text/csv; charset=utf-8"),
        data=backup_body,
        timeout=15,
    )
    try:
        backup_response.raise_for_status()
        meta["subscribers_backup_ok"] = True
        meta["subscribers_backup_path"] = f"oss://{settings.oss_bucket}/{backup_key}"
    except Exception as exc:
        meta["subscribers_error"] = f"backup_failed: {exc}"
        return meta
    response = requests.put(
        oss_url(source_cfg),
        headers=oss_headers("PUT", source_cfg, "text/csv; charset=utf-8"),
        data=body,
        timeout=15,
    )
    try:
        response.raise_for_status()
    except Exception as exc:
        meta["subscribers_error"] = str(exc)
        return meta
    table["raw_text"] = body_text
    table["fieldnames"] = fieldnames
    meta["subscribers_write_ok"] = True
    meta["subscribers_record_count"] = len(records)
    meta["subscribers_fieldnames"] = fieldnames
    return meta


def subscribers_table_needs_reminder_field_backfill(table: dict[str, Any] | None) -> bool:
    if not isinstance(table, dict):
        return False
    source_fieldnames = [str(name or "").strip() for name in (table.get("source_fieldnames") or []) if str(name or "").strip()]
    return "reminder_sent" not in source_fieldnames


def apply_successful_reminder_updates(
    table: dict[str, Any],
    variant_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    records = table.get("records") if isinstance(table.get("records"), list) else []
    index_by_email = {str(item.get("email") or "").strip().lower(): item for item in records if isinstance(item, dict)}
    updated_emails: list[str] = []
    updated_variants: dict[str, int] = {}
    for variant, result in (variant_results or {}).items():
        reminder_key = TRIAL_REMINDER_KEYS.get(variant, "")
        if not reminder_key:
            continue
        for item in result.get("recipient_status") or []:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").strip().lower()
            if status not in {"sent", "sent_bcc"}:
                continue
            email = str(item.get("email") or "").strip().lower()
            target = index_by_email.get(email)
            if not target:
                continue
            current = str(target.get("reminder_sent") or "")
            updated = _append_reminder_token(current, reminder_key)
            if updated == current:
                continue
            target["reminder_sent"] = updated
            updated_emails.append(email)
            updated_variants[variant] = updated_variants.get(variant, 0) + 1
    return {
        "subscribers_reminder_updates": len(updated_emails),
        "subscribers_reminder_update_emails": updated_emails,
        "subscribers_reminder_update_variants": updated_variants,
    }


def personalize_html_for_recipient(html_body: str, recipient: dict[str, str]) -> str:
    email = recipient.get("email", "")
    return replace_weekly_pdf_tracking_placeholders(
        html_body.replace(FEEDBACK_UID_PLACEHOLDER, recipient.get("uid", ""))
        .replace(FEEDBACK_EMAIL_HASH_PLACEHOLDER, recipient.get("email_hash", "")),
        email,
    )


def personalize_html_for_bcc(html_body: str) -> str:
    return replace_weekly_pdf_tracking_placeholders(
        html_body.replace(FEEDBACK_UID_PLACEHOLDER, "bcc").replace(FEEDBACK_EMAIL_HASH_PLACEHOLDER, ""),
        "bcc",
    )


def build_message(subject: str, plain_text: str, html_body: str, to_header: str, attachments: list[dict] | None = None) -> MIMEMultipart:
    attachments = attachments or []
    if attachments:
        message = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(plain_text, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        message.attach(alt)
        for item in attachments:
            filename = str(item.get("filename") or "attachment.bin")
            content = item.get("content") or b""
            if isinstance(content, str):
                content = content.encode("utf-8")
            content_type = str(item.get("content_type") or "application/octet-stream")
            maintype, subtype = (content_type.split("/", 1) + ["octet-stream"])[:2] if "/" in content_type else ("application", "octet-stream")
            part = MIMEBase(maintype, subtype)
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", filename))
            message.attach(part)
    else:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(plain_text, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))
    message["From"] = build_from_header()
    message["To"] = to_header
    message["Subject"] = Header(subject, "utf-8")
    return message


def _send_email_to_records(
    subject: str,
    plain_text: str,
    html_body: str,
    recipients: list[dict[str, str]],
    *,
    recipient_source: str,
    attachments: list[dict] | None = None,
    send_mode_override: str | None = None,
) -> dict[str, object]:
    if not recipients:
        return {
            "send_mode": send_mode_override or (settings.send_mode if settings.send_mode in {"bcc", "individual"} else "bcc"),
            "recipient_source": recipient_source,
            "valid_recipient_count": 0,
            "success_count": 0,
            "fail_count": 0,
            "recipient_status": [],
            "failures": [],
        }
    if not settings.smtp_user:
        raise RuntimeError("SMTP_USER is required.")
    if not settings.smtp_password:
        raise RuntimeError("SMTP_PASSWORD or SMTP_PASS is required.")

    recipients = normalize_recipient_records(recipients)
    send_mode = send_mode_override if send_mode_override in {"bcc", "individual"} else (settings.send_mode if settings.send_mode in {"bcc", "individual"} else "bcc")
    result: dict[str, object] = {
        "send_mode": send_mode,
        "recipient_source": recipient_source,
        "valid_recipient_count": len(recipients),
        "success_count": 0,
        "fail_count": 0,
        "recipient_status": [],
        "failures": [],
    }
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as server:
        server.login(settings.smtp_user, settings.smtp_password)
        if send_mode == "individual":
            for recipient in recipients:
                email = recipient["email"]
                try:
                    personalized_html = personalize_html_for_recipient(html_body, recipient)
                    message = build_message(subject, plain_text, personalized_html, email, attachments=attachments)
                    server.sendmail(settings.smtp_user, [email], message.as_string())
                    result["success_count"] = int(result["success_count"]) + 1
                    result["recipient_status"].append({"email": email, "uid": recipient.get("uid", ""), "status": "sent"})
                except Exception as exc:
                    result["fail_count"] = int(result["fail_count"]) + 1
                    result["recipient_status"].append({"email": email, "uid": recipient.get("uid", ""), "status": "failed", "error": str(exc)})
                    result["failures"].append({"email": email, "error": str(exc)})
        else:
            try:
                to_header = settings.mail_from or settings.smtp_user
                shared_html = personalize_html_for_bcc(html_body)
                message = build_message(subject, plain_text, shared_html, to_header, attachments=attachments)
                server.sendmail(settings.smtp_user, [recipient["email"] for recipient in recipients], message.as_string())
                result["success_count"] = len(recipients)
                result["recipient_status"] = [{"email": recipient["email"], "status": "sent_bcc"} for recipient in recipients]
            except Exception as exc:
                result["fail_count"] = len(recipients)
                result["recipient_status"] = [{"email": recipient["email"], "status": "failed", "error": str(exc)} for recipient in recipients]
                result["failures"].append({"email": "bcc_batch", "error": str(exc)})
    return result


def build_send_audit(delivery_date: str, segments: dict[str, list[dict[str, str]]], recipient_source: str) -> dict[str, Any]:
    full = segments.get("full") or []
    lite = segments.get("lite") or []
    skipped = segments.get("skipped") or []
    variants = segments.get("variants") or {}
    return {
        "delivery_date": delivery_date,
        "recipient_source": recipient_source,
        "full_count": len(full),
        "lite_count": len(lite),
        "skipped_count": len(skipped),
        "full_emails": [item["email"] for item in full],
        "lite_emails": [item["email"] for item in lite],
        "skipped_emails": [item["email"] for item in skipped],
        "variant_counts": {variant: len(items) for variant, items in variants.items()},
        "variant_emails": {variant: [item["email"] for item in items] for variant, items in variants.items()},
        "variant_assignments": segments.get("variant_assignments") or [],
    }


def _send_audit_path(delivery_date: str) -> Path:
    return settings.output_dir / f"send_audit_{delivery_date}.json"


def save_send_audit(delivery_date: str, segments: dict[str, list[dict[str, str]]], recipient_source: str) -> dict[str, Any]:
    audit = build_send_audit(delivery_date, segments, recipient_source)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    path = _send_audit_path(delivery_date)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**audit, "audit_path": str(path)}


def update_send_audit_results(
    delivery_date: str,
    audit: dict[str, Any],
    full_result: dict[str, object],
    lite_result: dict[str, object],
    variant_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    updated = dict(audit)
    updated["full_result"] = {
        "success_count": int(full_result.get("success_count", 0)),
        "fail_count": int(full_result.get("fail_count", 0)),
        "recipient_status": full_result.get("recipient_status") or [],
        "failures": full_result.get("failures") or [],
    }
    updated["lite_result"] = {
        "success_count": int(lite_result.get("success_count", 0)),
        "fail_count": int(lite_result.get("fail_count", 0)),
        "recipient_status": lite_result.get("recipient_status") or [],
        "failures": lite_result.get("failures") or [],
    }
    if variant_results is not None:
        updated["variant_results"] = variant_results
    path = Path(str(updated.get("audit_path") or _send_audit_path(delivery_date)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({key: value for key, value in updated.items() if key != "audit_path"}, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated


def send_segmented_email(
    subject: str,
    full_plain_text: str,
    full_html_body: str,
    lite_plain_text: str,
    lite_html_body: str,
    *,
    delivery_date: str,
    test_mode: bool = False,
    attachments: list[dict] | None = None,
    lite_attachments: list[dict] | None = None,
    segments: dict[str, list[dict[str, str]]] | None = None,
    recipient_source: str | None = None,
    enable_trial_reminders: bool = False,
    subscribers_table: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if segments is None:
        segments, recipient_source = split_effective_recipient_records(test_mode=test_mode, today=delivery_date)
    recipient_source = recipient_source or "unknown"
    audit = save_send_audit(delivery_date, segments, recipient_source)
    variant_groups = segments.get("variants") or {}
    variant_payloads = render_variant_email_payloads(
        subject,
        full_plain_text,
        full_html_body,
        lite_plain_text,
        lite_html_body,
        list(variant_groups.keys()),
        enable_trial_reminders=enable_trial_reminders,
    )
    variant_results: dict[str, dict[str, Any]] = {}
    for variant, recipients in variant_groups.items():
        if variant == "skip":
            variant_results[variant] = {
                "send_mode": "skip",
                "recipient_source": f"{recipient_source}:{variant}",
                "valid_recipient_count": 0,
                "success_count": 0,
                "fail_count": 0,
                "skipped_count": len(recipients),
                "recipient_status": [{"email": item.get("email", ""), "uid": item.get("uid", ""), "status": "skipped"} for item in recipients],
                "failures": [],
            }
            continue
        payload = variant_payloads[variant]
        variant_results[variant] = _send_email_to_records(
            payload["subject"],
            payload["plain_text"],
            payload["html_body"],
            recipients,
            recipient_source=f"{recipient_source}:{variant}",
            attachments=attachments if variant in FULL_VARIANTS else lite_attachments,
            send_mode_override="individual",
        )
    full_result = {
        "success_count": sum(int((variant_results.get(name) or {}).get("success_count", 0)) for name in FULL_VARIANTS),
        "fail_count": sum(int((variant_results.get(name) or {}).get("fail_count", 0)) for name in FULL_VARIANTS),
        "recipient_status": [item for name in FULL_VARIANTS for item in ((variant_results.get(name) or {}).get("recipient_status") or [])],
        "failures": [item for name in FULL_VARIANTS for item in ((variant_results.get(name) or {}).get("failures") or [])],
    }
    lite_result = {
        "success_count": sum(int((variant_results.get(name) or {}).get("success_count", 0)) for name in LITE_VARIANTS),
        "fail_count": sum(int((variant_results.get(name) or {}).get("fail_count", 0)) for name in LITE_VARIANTS),
        "recipient_status": [item for name in LITE_VARIANTS for item in ((variant_results.get(name) or {}).get("recipient_status") or [])],
        "failures": [item for name in LITE_VARIANTS for item in ((variant_results.get(name) or {}).get("failures") or [])],
    }
    subscribers_write_meta: dict[str, Any] = {
        "subscribers_write_ok": False,
        "subscribers_backup_ok": False,
        "subscribers_write_skipped": True,
        "subscribers_write_skip_reason": "trial_reminders_disabled",
    }
    reminder_update_meta: dict[str, Any] = {
        "subscribers_reminder_updates": 0,
        "subscribers_reminder_update_emails": [],
        "subscribers_reminder_update_variants": {},
    }
    needs_reminder_field_backfill = subscribers_table_needs_reminder_field_backfill(subscribers_table)
    if enable_trial_reminders and subscribers_table and not test_mode and str(subscribers_table.get("storage") or "").lower() == "oss":
        reminder_update_meta = apply_successful_reminder_updates(subscribers_table, variant_results)
        if reminder_update_meta["subscribers_reminder_updates"] > 0 or needs_reminder_field_backfill:
            subscribers_write_meta = backup_and_save_subscribers_table_to_oss(subscribers_table)
            subscribers_write_meta["subscribers_write_skipped"] = False
            subscribers_write_meta["subscribers_write_skip_reason"] = ""
        else:
            subscribers_write_meta["subscribers_write_skip_reason"] = "no_subscriber_changes"
    elif subscribers_table and str(subscribers_table.get("storage") or "").lower() != "oss":
        subscribers_write_meta["subscribers_write_skip_reason"] = "subscribers_storage_not_oss"
    elif test_mode:
        subscribers_write_meta["subscribers_write_skip_reason"] = "test_mode"
    audit = update_send_audit_results(delivery_date, audit, full_result, lite_result, variant_results=variant_results)
    return {
        "send_mode": "individual",
        "recipient_source": recipient_source,
        "valid_recipient_count": audit["full_count"] + audit["lite_count"],
        "full_count": audit["full_count"],
        "lite_count": audit["lite_count"],
        "skipped_count": audit["skipped_count"],
        "success_count": int(full_result.get("success_count", 0)) + int(lite_result.get("success_count", 0)),
        "fail_count": int(full_result.get("fail_count", 0)) + int(lite_result.get("fail_count", 0)),
        "full_result": full_result,
        "lite_result": lite_result,
        "variant_results": variant_results,
        "variant_counts": audit.get("variant_counts") or {},
        **reminder_update_meta,
        **subscribers_write_meta,
        "send_audit": audit,
    }


def send_email(subject: str, plain_text: str, html_body: str, test_mode: bool = False, attachments: list[dict] | None = None) -> dict[str, object]:
    if not settings.smtp_user:
        raise RuntimeError("SMTP_USER is required.")
    if not settings.smtp_password:
        raise RuntimeError("SMTP_PASSWORD or SMTP_PASS is required.")
    recipients, recipient_source = get_effective_recipient_records(test_mode=test_mode)
    if not recipients:
        if test_mode:
            raise RuntimeError("TEST_RECIPIENTS is required in test mode to avoid sending to production subscribers.")
        raise RuntimeError("No valid recipients found in subscribers.csv, RECIPIENTS or MAIL_TO.")

    send_mode = settings.send_mode if settings.send_mode in {"bcc", "individual"} else "bcc"
    result: dict[str, object] = {
        "send_mode": send_mode,
        "recipient_source": recipient_source,
        "valid_recipient_count": len(recipients),
        "is_test_mode": test_mode,
        "success_count": 0,
        "fail_count": 0,
        "recipient_status": [],
        "failures": [],
    }

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as server:
        server.login(settings.smtp_user, settings.smtp_password)
        if send_mode == "individual":
            for recipient in recipients:
                email = recipient["email"]
                try:
                    personalized_html = personalize_html_for_recipient(html_body, recipient)
                    message = build_message(subject, plain_text, personalized_html, email, attachments=attachments)
                    server.sendmail(settings.smtp_user, [email], message.as_string())
                    result["success_count"] = int(result["success_count"]) + 1
                    result["recipient_status"].append({"email": email, "uid": recipient.get("uid", ""), "status": "sent"})
                except Exception as exc:
                    result["fail_count"] = int(result["fail_count"]) + 1
                    result["recipient_status"].append({"email": email, "uid": recipient.get("uid", ""), "status": "failed", "error": str(exc)})
                    result["failures"].append({"email": email, "error": str(exc)})
        else:
            try:
                to_header = settings.mail_from or settings.smtp_user
                shared_html = personalize_html_for_bcc(html_body)
                message = build_message(subject, plain_text, shared_html, to_header, attachments=attachments)
                server.sendmail(settings.smtp_user, [recipient["email"] for recipient in recipients], message.as_string())
                result["success_count"] = len(recipients)
                result["recipient_status"] = [{"email": recipient["email"], "status": "sent_bcc"} for recipient in recipients]
            except Exception as exc:
                result["fail_count"] = len(recipients)
                result["recipient_status"] = [{"email": recipient["email"], "status": "failed", "error": str(exc)} for recipient in recipients]
                result["failures"].append({"email": "bcc_batch", "error": str(exc)})
    return result


def send_email_to_recipients(
    subject: str,
    plain_text: str,
    html_body: str,
    recipients: list[str],
    *,
    recipient_source: str = "explicit",
    attachments: list[dict] | None = None,
) -> dict[str, object]:
    if not settings.smtp_user:
        raise RuntimeError("SMTP_USER is required.")
    if not settings.smtp_password:
        raise RuntimeError("SMTP_PASSWORD or SMTP_PASS is required.")
    recipients = normalize_recipients(recipients)
    if not recipients:
        return {
            "send_mode": "bcc",
            "recipient_source": recipient_source,
            "valid_recipient_count": 0,
            "success_count": 0,
            "fail_count": 0,
            "recipient_status": [],
            "failures": [{"email": "admin_report", "error": "No valid admin recipients."}],
        }

    result: dict[str, object] = {
        "send_mode": "bcc",
        "recipient_source": recipient_source,
        "valid_recipient_count": len(recipients),
        "success_count": 0,
        "fail_count": 0,
        "recipient_status": [],
        "failures": [],
    }
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as server:
        server.login(settings.smtp_user, settings.smtp_password)
        try:
            to_header = settings.mail_from or settings.smtp_user
            message = build_message(subject, plain_text, personalize_html_for_bcc(html_body), to_header, attachments=attachments)
            server.sendmail(settings.smtp_user, recipients, message.as_string())
            result["success_count"] = len(recipients)
            result["recipient_status"] = [{"email": recipient, "status": "sent_bcc"} for recipient in recipients]
        except Exception as exc:
            result["fail_count"] = len(recipients)
            result["recipient_status"] = [{"email": recipient, "status": "failed", "error": str(exc)} for recipient in recipients]
            result["failures"].append({"email": "admin_report_bcc", "error": str(exc)})
    return result
