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


def normalize_recipient_records(raw_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    recipients: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items:
        email = str(item.get("email") or "").strip()
        if not email or not EMAIL_RE.match(email):
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        uid = str(item.get("uid") or item.get("id") or "").strip() or _fallback_uid(email)
        recipients.append(
            {
                "email": email,
                "uid": uid,
                "email_hash": str(item.get("email_hash") or "").strip() or _email_hash(email),
                "status": str(item.get("status") or "active").strip().lower() or "active",
                "plan": str(item.get("plan") or "free").strip().lower() or "free",
                "paid_until": str(item.get("paid_until") or "").strip(),
                "send_mode": str(item.get("send_mode") or "").strip().lower(),
                "note": str(item.get("note") or "").strip(),
            }
        )
    return recipients


def parse_subscribers_csv(csv_text: str) -> list[str]:
    return [item["email"] for item in parse_subscribers_csv_records(csv_text)]


def parse_subscribers_csv_all_records(csv_text: str) -> list[dict[str, str]]:
    recipients: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or "email" not in reader.fieldnames:
        return []
    for row in reader:
        recipients.append(
            {
                "email": row.get("email", ""),
                "uid": row.get("uid", ""),
                "email_hash": row.get("email_hash", ""),
                "status": row.get("status") or "active",
                "plan": row.get("plan") or "free",
                "paid_until": row.get("paid_until", ""),
                "send_mode": row.get("send_mode", ""),
                "note": row.get("note", ""),
            }
        )
    return normalize_recipient_records(recipients)


def parse_subscribers_csv_records(csv_text: str) -> list[dict[str, str]]:
    return [item for item in parse_subscribers_csv_all_records(csv_text) if item.get("status") == "active"]


def load_subscribers_csv_local() -> list[str] | None:
    records = load_subscribers_csv_local_records()
    if records is None:
        return None
    return [item["email"] for item in records]


def load_subscribers_csv_local_records() -> list[dict[str, str]] | None:
    path = Path(__file__).with_name("subscribers.csv")
    if not path.exists():
        return None
    try:
        return parse_subscribers_csv_records(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def load_subscribers_csv_oss() -> list[str] | None:
    records = load_subscribers_csv_oss_records()
    if records is None:
        return None
    return [item["email"] for item in records]


def load_subscribers_csv_oss_records() -> list[dict[str, str]] | None:
    if settings.subscribers_storage != "oss":
        return None
    if not oss_ready():
        return None
    try:
        cfg = oss_config()
        cfg["object_key"] = settings.subscribers_oss_key
        response = requests.get(oss_url(cfg), headers=oss_headers("GET", cfg), timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return parse_subscribers_csv_records(response.text)
    except Exception:
        return None


def load_subscribers_csv_local_all_records() -> list[dict[str, str]] | None:
    path = Path(__file__).with_name("subscribers.csv")
    if not path.exists():
        return None
    try:
        return parse_subscribers_csv_all_records(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def load_subscribers_csv_oss_all_records() -> list[dict[str, str]] | None:
    if settings.subscribers_storage != "oss":
        return None
    if not oss_ready():
        return None
    try:
        cfg = oss_config()
        cfg["object_key"] = settings.subscribers_oss_key
        response = requests.get(oss_url(cfg), headers=oss_headers("GET", cfg), timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return parse_subscribers_csv_all_records(response.text)
    except Exception:
        return None


def load_subscribers_csv() -> tuple[list[str] | None, str]:
    records, source = load_subscribers_csv_records()
    if records is None:
        return None, source
    return [item["email"] for item in records], source


def load_subscribers_csv_records() -> tuple[list[dict[str, str]] | None, str]:
    oss_recipients = load_subscribers_csv_oss_records()
    if oss_recipients:
        return oss_recipients, f"OSS:{settings.subscribers_oss_key}"
    local_recipients = load_subscribers_csv_local_records()
    if local_recipients:
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
    if csv_recipients:
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
    if csv_recipients:
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
    if oss_recipients:
        return oss_recipients, f"OSS:{settings.subscribers_oss_key}"
    local_recipients = load_subscribers_csv_local_all_records()
    if local_recipients:
        return local_recipients, "subscribers.csv"
    raw = settings.recipients_raw.replace(";", ",").split(",")
    return normalize_recipient_records([{"email": email} for email in raw]), "RECIPIENTS"


def _parse_date(text: str) -> dt.date | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.strptime(text[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def recipient_delivery_tier(record: dict[str, str], today: str | dt.date | None = None) -> str:
    status = str(record.get("status") or "active").strip().lower() or "active"
    if status != "active":
        return "skipped"
    send_mode = str(record.get("send_mode") or "").strip().lower()
    if send_mode == "none":
        return "skipped"
    if send_mode == "full":
        return "full"
    if send_mode == "lite":
        return "lite"
    plan = str(record.get("plan") or "free").strip().lower() or "free"
    today_date = today if isinstance(today, dt.date) else _parse_date(str(today or ""))
    today_date = today_date or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    paid_until = _parse_date(str(record.get("paid_until") or ""))
    if plan in PAID_PLANS and paid_until and paid_until >= today_date:
        return "full"
    return "lite"


def split_recipient_records(records: list[dict[str, str]], today: str | dt.date | None = None) -> dict[str, list[dict[str, str]]]:
    segments = {"full": [], "lite": [], "skipped": []}
    for record in normalize_recipient_records(records):
        tier = recipient_delivery_tier(record, today=today)
        segments[tier].append(record)
    return segments


def split_effective_recipient_records(test_mode: bool = False, today: str | dt.date | None = None) -> tuple[dict[str, list[dict[str, str]]], str]:
    records, source = get_effective_recipient_records_for_segmentation(test_mode=test_mode)
    return split_recipient_records(records, today=today), source


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
) -> dict[str, object]:
    if not recipients:
        return {
            "send_mode": settings.send_mode if settings.send_mode in {"bcc", "individual"} else "bcc",
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
    send_mode = settings.send_mode if settings.send_mode in {"bcc", "individual"} else "bcc"
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
    return {
        "delivery_date": delivery_date,
        "recipient_source": recipient_source,
        "full_count": len(full),
        "lite_count": len(lite),
        "skipped_count": len(skipped),
        "full_emails": [item["email"] for item in full],
        "lite_emails": [item["email"] for item in lite],
        "skipped_emails": [item["email"] for item in skipped],
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
) -> dict[str, Any]:
    if segments is None:
        segments, recipient_source = split_effective_recipient_records(test_mode=test_mode, today=delivery_date)
    recipient_source = recipient_source or "unknown"
    audit = save_send_audit(delivery_date, segments, recipient_source)
    full_result = _send_email_to_records(
        subject,
        full_plain_text,
        full_html_body,
        segments.get("full") or [],
        recipient_source=f"{recipient_source}:full",
        attachments=attachments,
    )
    lite_result = _send_email_to_records(
        subject,
        lite_plain_text,
        lite_html_body,
        segments.get("lite") or [],
        recipient_source=f"{recipient_source}:lite",
        attachments=lite_attachments,
    )
    audit = update_send_audit_results(delivery_date, audit, full_result, lite_result)
    return {
        "send_mode": settings.send_mode if settings.send_mode in {"bcc", "individual"} else "bcc",
        "recipient_source": recipient_source,
        "valid_recipient_count": audit["full_count"] + audit["lite_count"],
        "full_count": audit["full_count"],
        "lite_count": audit["lite_count"],
        "skipped_count": audit["skipped_count"],
        "success_count": int(full_result.get("success_count", 0)) + int(lite_result.get("success_count", 0)),
        "fail_count": int(full_result.get("fail_count", 0)) + int(lite_result.get("fail_count", 0)),
        "full_result": full_result,
        "lite_result": lite_result,
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
