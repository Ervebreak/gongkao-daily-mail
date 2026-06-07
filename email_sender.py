from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import re
import smtplib
import ssl
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from pathlib import Path
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - local unit tests may not install network deps
    requests = None

from config import settings
try:
    from weekly_pdf_tracking import replace_weekly_pdf_tracking_placeholders
except ModuleNotFoundError:  # pragma: no cover - unit tests do not need tracking
    def replace_weekly_pdf_tracking_placeholders(text: str, recipient_email: str) -> str:
        return text

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
FEEDBACK_UID_PLACEHOLDER = "__FEEDBACK_UID__"
FEEDBACK_EMAIL_HASH_PLACEHOLDER = "__FEEDBACK_EMAIL_HASH__"
FULL_ACCESS_PLANS = {"paid_trial", "paid_monthly"}


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


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_status(value: Any) -> str:
    return _clean_text(value).lower() or "active"


def _normalize_plan(value: Any) -> str:
    return _clean_text(value).lower() or "free"


def _normalize_send_mode(value: Any) -> str:
    return _clean_text(value).lower() or "lite"


def _parse_date(value: Any) -> dt.date | None:
    raw = _clean_text(value)
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        return dt.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _resolve_delivery_date(delivery_date: str | dt.date | None) -> dt.date:
    if isinstance(delivery_date, dt.date):
        return delivery_date
    parsed = _parse_date(delivery_date)
    return parsed or dt.datetime.now(dt.timezone.utc).date()


def normalize_recipient_records(raw_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    recipients: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items:
        email = _clean_text(item.get("email"))
        if not email or not EMAIL_RE.match(email):
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        uid = _clean_text(item.get("uid") or item.get("id")) or _fallback_uid(email)
        recipients.append(
            {
                "email": email,
                "uid": uid,
                "email_hash": _clean_text(item.get("email_hash")) or _email_hash(email),
                "status": _normalize_status(item.get("status")),
                "plan": _normalize_plan(item.get("plan")),
                "paid_until": _clean_text(item.get("paid_until")),
                "send_mode": _normalize_send_mode(item.get("send_mode")),
                "note": _clean_text(item.get("note")),
            }
        )
    return recipients


def parse_subscribers_csv(csv_text: str) -> list[str]:
    return [item["email"] for item in parse_subscribers_csv_records(csv_text)]


def parse_subscribers_csv_records(csv_text: str) -> list[dict[str, str]]:
    recipients: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        recipients.append(
            {
                "email": row.get("email", ""),
                "uid": row.get("uid", ""),
                "email_hash": row.get("email_hash", ""),
                "status": row.get("status", ""),
                "plan": row.get("plan", ""),
                "paid_until": row.get("paid_until", ""),
                "send_mode": row.get("send_mode", ""),
                "note": row.get("note", ""),
            }
        )
    return normalize_recipient_records(recipients)


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
    if requests is None:
        return None
    from history import oss_config, oss_headers, oss_ready, oss_url

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


def load_subscribers_csv() -> tuple[list[str] | None, str]:
    records, source = get_effective_recipient_records()
    if not records:
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


def _records_from_email_list(emails: list[str], uid_prefix: str = "u") -> list[dict[str, str]]:
    return normalize_recipient_records(
        [{"email": email, "uid": _fallback_uid(email, prefix=uid_prefix), "status": "active", "plan": "free"} for email in emails]
    )


def classify_recipient_delivery(recipient: dict[str, Any], delivery_date: str | dt.date | None = None) -> str:
    status = _normalize_status(recipient.get("status"))
    if status != "active":
        return "skipped"
    plan = _normalize_plan(recipient.get("plan"))
    paid_until = _parse_date(recipient.get("paid_until"))
    today = _resolve_delivery_date(delivery_date)
    if plan in FULL_ACCESS_PLANS and paid_until and paid_until >= today:
        return "full"
    return "lite"


def build_recipient_delivery_plan(
    records: list[dict[str, Any]] | None,
    *,
    recipient_source: str,
    delivery_date: str | dt.date | None = None,
) -> dict[str, Any]:
    normalized = normalize_recipient_records(records or [])
    full_records: list[dict[str, str]] = []
    lite_records: list[dict[str, str]] = []
    skipped_records: list[dict[str, str]] = []
    for record in normalized:
        tier = classify_recipient_delivery(record, delivery_date=delivery_date)
        enriched = dict(record)
        enriched["delivery_tier"] = tier
        if tier == "full":
            full_records.append(enriched)
        elif tier == "lite":
            lite_records.append(enriched)
        else:
            skipped_records.append(enriched)
    return {
        "recipient_source": recipient_source,
        "full_records": full_records,
        "lite_records": lite_records,
        "skipped_records": skipped_records,
        "full_count": len(full_records),
        "lite_count": len(lite_records),
        "skipped_count": len(skipped_records),
        "full_emails": [item["email"] for item in full_records],
        "lite_emails": [item["email"] for item in lite_records],
        "skipped_emails": [item["email"] for item in skipped_records],
    }


def get_recipient_delivery_plan(test_mode: bool = False, delivery_date: str | dt.date | None = None) -> dict[str, Any]:
    if test_mode:
        test_recipients = normalize_recipients(settings.test_recipients)
        if test_recipients:
            return build_recipient_delivery_plan(
                _records_from_email_list(test_recipients, uid_prefix="test"),
                recipient_source="TEST_RECIPIENTS",
                delivery_date=delivery_date,
            )
        return build_recipient_delivery_plan([], recipient_source="TEST_RECIPIENTS_EMPTY", delivery_date=delivery_date)

    csv_recipients, csv_source = load_subscribers_csv_records()
    if csv_recipients:
        return build_recipient_delivery_plan(csv_recipients, recipient_source=csv_source, delivery_date=delivery_date)
    raw = settings.recipients_raw.replace(";", ",").split(",")
    return build_recipient_delivery_plan(
        _records_from_email_list(normalize_recipients(raw)),
        recipient_source="RECIPIENTS",
        delivery_date=delivery_date,
    )


def get_effective_recipients(test_mode: bool = False) -> tuple[list[str], str]:
    records, source = get_effective_recipient_records(test_mode=test_mode)
    return [item["email"] for item in records], source


def get_effective_recipient_records(test_mode: bool = False) -> tuple[list[dict[str, str]], str]:
    plan = get_recipient_delivery_plan(test_mode=test_mode)
    records = plan["full_records"] + plan["lite_records"]
    return records, str(plan.get("recipient_source") or "none")


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


def send_email(subject: str, plain_text: str, html_body: str, test_mode: bool = False, attachments: list[dict] | None = None) -> dict[str, object]:
    recipients, recipient_source = get_effective_recipient_records(test_mode=test_mode)
    if not recipients and test_mode:
        raise RuntimeError("TEST_RECIPIENTS is required in test mode to avoid sending to production subscribers.")
    if not recipients and not test_mode:
        raise RuntimeError("No valid recipients found in subscribers.csv, RECIPIENTS or MAIL_TO.")
    return send_email_to_recipient_records(
        subject,
        plain_text,
        html_body,
        recipients,
        recipient_source=recipient_source,
        test_mode=test_mode,
        attachments=attachments,
    )


def send_email_to_recipient_records(
    subject: str,
    plain_text: str,
    html_body: str,
    recipients: list[dict[str, Any]],
    *,
    recipient_source: str = "explicit",
    test_mode: bool = False,
    attachments: list[dict] | None = None,
) -> dict[str, object]:
    if not settings.smtp_user:
        raise RuntimeError("SMTP_USER is required.")
    if not settings.smtp_password:
        raise RuntimeError("SMTP_PASSWORD or SMTP_PASS is required.")
    recipients = normalize_recipient_records(recipients)
    send_mode = settings.send_mode if settings.send_mode in {"bcc", "individual"} else "bcc"
    if not recipients:
        return {
            "send_mode": send_mode,
            "recipient_source": recipient_source,
            "valid_recipient_count": 0,
            "is_test_mode": test_mode,
            "success_count": 0,
            "fail_count": 0,
            "recipient_status": [],
            "failures": [],
        }

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
