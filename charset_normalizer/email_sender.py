from __future__ import annotations

import csv
import hashlib
import io
import re
import smtplib
import ssl
from pathlib import Path
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr, parseaddr
from typing import Any

import requests

from config import settings
from history import oss_config, oss_headers, oss_ready, oss_url

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
FEEDBACK_UID_PLACEHOLDER = "__FEEDBACK_UID__"
FEEDBACK_EMAIL_HASH_PLACEHOLDER = "__FEEDBACK_EMAIL_HASH__"


def build_from_header() -> str:
    # QQ SMTP is strict: the From address must be a valid mailbox and should
    # match the authenticated SMTP account. Keep the display name optional.
    mail_from = settings.mail_from or settings.smtp_user
    _, parsed_addr = parseaddr(mail_from)
    from_addr = parsed_addr if parsed_addr and "@" in parsed_addr else settings.smtp_user
    if from_addr != settings.smtp_user:
        from_addr = settings.smtp_user
    return formataddr((str(Header("公考晨读", "utf-8")), from_addr))


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


def _fallback_uid(email: str, prefix: str = "u") -> str:
    return f"{prefix}_{_email_hash(email)}"


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


def normalize_recipient_records(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in records:
        email = str(row.get("email") or "").strip()
        if not email or not EMAIL_RE.match(email):
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        uid = str(row.get("uid") or row.get("id") or row.get("user_id") or "").strip()
        if not uid:
            uid = _fallback_uid(email)
        normalized.append(
            {
                "email": email,
                "uid": uid,
                "email_hash": _email_hash(email),
                "nickname": str(row.get("nickname") or row.get("name") or "").strip(),
                "source": str(row.get("source") or "").strip(),
                "plan": str(row.get("plan") or "").strip(),
            }
        )
    return normalized


def parse_subscribers_csv_records(csv_text: str) -> list[dict[str, str]]:
    records: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        if (row.get("status") or "").strip().lower() == "active":
            records.append(row)
    return normalize_recipient_records(records)


def parse_subscribers_csv(csv_text: str) -> list[str]:
    return [record["email"] for record in parse_subscribers_csv_records(csv_text)]


def load_subscribers_csv_local_records() -> list[dict[str, str]] | None:
    path = Path(__file__).with_name("subscribers.csv")
    if not path.exists():
        return None
    try:
        return parse_subscribers_csv_records(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def load_subscribers_csv_local() -> list[str] | None:
    records = load_subscribers_csv_local_records()
    if records is None:
        return None
    return [record["email"] for record in records]


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


def load_subscribers_csv_oss() -> list[str] | None:
    records = load_subscribers_csv_oss_records()
    if records is None:
        return None
    return [record["email"] for record in records]


def load_subscribers_csv_records() -> tuple[list[dict[str, str]] | None, str]:
    oss_records = load_subscribers_csv_oss_records()
    if oss_records:
        return oss_records, f"OSS:{settings.subscribers_oss_key}"
    local_records = load_subscribers_csv_local_records()
    if local_records:
        return local_records, "subscribers.csv"
    return None, "none"


def load_subscribers_csv() -> tuple[list[str] | None, str]:
    records, source = load_subscribers_csv_records()
    if records:
        return [record["email"] for record in records], source
    return None, source


def _records_from_email_list(emails: list[str], uid_prefix: str = "u") -> list[dict[str, str]]:
    return normalize_recipient_records([{"email": email, "uid": _fallback_uid(email, prefix=uid_prefix)} for email in emails])


def get_effective_recipient_records(test_mode: bool = False) -> tuple[list[dict[str, str]], str]:
    if test_mode:
        test_recipients = normalize_recipients(settings.test_recipients)
        if test_recipients:
            return _records_from_email_list(test_recipients, uid_prefix="test"), "TEST_RECIPIENTS"
        # 安全兜底：测试模式没有配置 TEST_RECIPIENTS 时，不读取正式用户表，避免误发。
        return [], "TEST_RECIPIENTS_EMPTY"

    csv_records, csv_source = load_subscribers_csv_records()
    if csv_records:
        return csv_records, csv_source
    raw = settings.recipients_raw.replace(";", ",").split(",")
    fallback_emails = normalize_recipients(raw)
    return _records_from_email_list(fallback_emails), "RECIPIENTS"


def get_effective_recipients(test_mode: bool = False) -> tuple[list[str], str]:
    records, source = get_effective_recipient_records(test_mode=test_mode)
    return [record["email"] for record in records], source


def personalize_html_for_recipient(html_body: str, recipient: dict[str, str]) -> str:
    """把邮件中的反馈链接占位符替换成该收件人的 uid。

    注意：SEND_MODE=individual 时才可以真正做到“每个用户一套链接”。
    BCC 模式下只能使用未个性化占位符，无法做用户级反馈统计。
    """
    uid = str(recipient.get("uid") or "").strip()
    email_hash = str(recipient.get("email_hash") or "").strip()
    if not uid:
        uid = _fallback_uid(str(recipient.get("email") or ""))
    if not email_hash:
        email_hash = _email_hash(str(recipient.get("email") or ""))
    return html_body.replace(FEEDBACK_UID_PLACEHOLDER, uid).replace(FEEDBACK_EMAIL_HASH_PLACEHOLDER, email_hash)


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
                    result["failures"].append({"email": email, "uid": recipient.get("uid", ""), "error": str(exc)})
        else:
            try:
                to_header = settings.mail_from or settings.smtp_user
                # BCC 是同一封 HTML 发给所有人，不能做用户级 uid。保留空 uid，避免误归属。
                shared_html = html_body.replace(FEEDBACK_UID_PLACEHOLDER, "bcc").replace(FEEDBACK_EMAIL_HASH_PLACEHOLDER, "")
                message = build_message(subject, plain_text, shared_html, to_header, attachments=attachments)
                server.sendmail(settings.smtp_user, [recipient["email"] for recipient in recipients], message.as_string())
                result["success_count"] = len(recipients)
                result["recipient_status"] = [
                    {"email": recipient["email"], "uid": recipient.get("uid", ""), "status": "sent_bcc"}
                    for recipient in recipients
                ]
            except Exception as exc:
                result["fail_count"] = len(recipients)
                result["recipient_status"] = [
                    {"email": recipient["email"], "uid": recipient.get("uid", ""), "status": "failed", "error": str(exc)}
                    for recipient in recipients
                ]
                result["failures"].append({"email": "bcc_batch", "error": str(exc)})
    return result
