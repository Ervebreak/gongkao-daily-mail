from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote, urlencode

from config import settings


FEEDBACK_UID_PLACEHOLDER = "__FEEDBACK_UID__"
FEEDBACK_EMAIL_HASH_PLACEHOLDER = "__FEEDBACK_EMAIL_HASH__"
UNSUBSCRIBE_SUBJECT = "退订公考晨读邮件"
UNSUBSCRIBE_BODY = "你好，我想退订/暂停接收公考晨读邮件。请将我当前接收这封邮件的邮箱从发送名单中移除，谢谢。"
UNSUBSCRIBE_TEXT = "如果你暂时不想继续接收，可以点击这里发送退订邮件，我会手动处理。"


def _append_query(url: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


def render_unsubscribe_url(brief: dict[str, Any] | None = None) -> str:
    brief = brief or {}
    mode = (settings.unsubscribe_mode or "mailto").strip().lower()
    base_url = settings.feedback_base_url.strip()
    if mode == "auto" and base_url:
        mail_id = str(brief.get("mail_id") or brief.get("date") or "").strip()
        params = {
            "task": "unsubscribe",
            "date": str(brief.get("date") or "").strip(),
            "mail_id": mail_id,
            "uid": FEEDBACK_UID_PLACEHOLDER,
            "email_hash": FEEDBACK_EMAIL_HASH_PLACEHOLDER,
        }
        return _append_query(base_url, params)
    email = settings.unsubscribe_email.strip()
    if not email:
        return ""
    return f"mailto:{email}?subject={quote(UNSUBSCRIBE_SUBJECT)}&body={quote(UNSUBSCRIBE_BODY)}"


def render_unsubscribe_button(brief: dict[str, Any] | None = None) -> str:
    url = render_unsubscribe_url(brief)
    if not url:
        return ""
    return f"""
    <div style="text-align:center;padding:8px 12px 18px;">
      <a href="{html.escape(url, quote=True)}" target="_blank"
         style="display:inline-block;color:#64748b;text-decoration:none;border:1px solid #cbd5e1;
                border-radius:999px;padding:7px 14px;font-size:12px;font-weight:700;line-height:1.7;">
        {html.escape(UNSUBSCRIBE_TEXT)}
      </a>
    </div>
    """


def render_plain_unsubscribe_text(brief: dict[str, Any] | None = None) -> str:
    url = render_unsubscribe_url(brief)
    if not url:
        return ""
    return f"{UNSUBSCRIBE_TEXT}\n{url}"
