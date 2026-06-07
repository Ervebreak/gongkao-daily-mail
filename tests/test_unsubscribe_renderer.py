from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from config import settings
from email_renderer import render_unsubscribe_button
from lite_email_renderer import render_lite_email
from unsubscribe_renderer import render_unsubscribe_url


def _set_setting(name: str, value: object):
    old = getattr(settings, name)
    object.__setattr__(settings, name, value)
    return old


def test_default_unsubscribe_url_uses_mailto() -> None:
    old_mode = _set_setting("unsubscribe_mode", "mailto")
    old_email = _set_setting("unsubscribe_email_raw", "admin@example.com")
    old_admin = _set_setting("admin_report_emails_raw", "")
    old_smtp = _set_setting("smtp_user", "smtp@example.com")
    try:
        url = render_unsubscribe_url({"date": "2026-06-07"})
    finally:
        object.__setattr__(settings, "unsubscribe_mode", old_mode)
        object.__setattr__(settings, "unsubscribe_email_raw", old_email)
        object.__setattr__(settings, "admin_report_emails_raw", old_admin)
        object.__setattr__(settings, "smtp_user", old_smtp)

    assert url.startswith("mailto:admin@example.com?")


def test_mailto_unsubscribe_contains_subject_and_body() -> None:
    old_mode = _set_setting("unsubscribe_mode", "mailto")
    old_email = _set_setting("unsubscribe_email_raw", "admin@example.com")
    try:
        url = render_unsubscribe_url({})
    finally:
        object.__setattr__(settings, "unsubscribe_mode", old_mode)
        object.__setattr__(settings, "unsubscribe_email_raw", old_email)

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "mailto"
    assert unquote(query["subject"][0]) == "退订公考晨读邮件"
    assert "我想退订/暂停接收公考晨读邮件" in unquote(query["body"][0])


def test_lite_email_contains_unsubscribe_entry() -> None:
    old_mode = _set_setting("unsubscribe_mode", "mailto")
    old_email = _set_setting("unsubscribe_email_raw", "admin@example.com")
    try:
        lite = render_lite_email(
            {
                "brief": {
                    "today_theme": "基层治理",
                    "today_takeaway": {"golden_sentences": [{"sentence": "把问题解决在基层一线。"}]},
                    "daily_question": {"question": "请谈谈如何做好基层治理。"},
                }
            }
        )
    finally:
        object.__setattr__(settings, "unsubscribe_mode", old_mode)
        object.__setattr__(settings, "unsubscribe_email_raw", old_email)

    body = lite["plain_text"] + lite["html_body"]

    assert "mailto:admin@example.com" in body
    assert "发送退订邮件" in body


def test_full_email_contains_unsubscribe_entry() -> None:
    old_mode = _set_setting("unsubscribe_mode", "mailto")
    old_email = _set_setting("unsubscribe_email_raw", "admin@example.com")
    try:
        html = render_unsubscribe_button({"date": "2026-06-07"})
    finally:
        object.__setattr__(settings, "unsubscribe_mode", old_mode)
        object.__setattr__(settings, "unsubscribe_email_raw", old_email)

    assert "mailto:admin@example.com" in html
    assert "发送退订邮件" in html


def test_auto_unsubscribe_mode_uses_feedback_url() -> None:
    old_mode = _set_setting("unsubscribe_mode", "auto")
    old_feedback = _set_setting("feedback_base_url", "https://example.com/fc")
    try:
        url = render_unsubscribe_url({"date": "2026-06-07", "mail_id": "m1"})
    finally:
        object.__setattr__(settings, "unsubscribe_mode", old_mode)
        object.__setattr__(settings, "feedback_base_url", old_feedback)

    assert url.startswith("https://example.com/fc?")
    assert "task=unsubscribe" in url
    assert "uid=__FEEDBACK_UID__" in url
