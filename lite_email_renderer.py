from __future__ import annotations

from typing import Any

from email_renderer import (
    render_lite_email as render_lite_html_shared,
    render_lite_plain_text as render_lite_plain_text_shared,
    render_plain_unsubscribe_text,
    render_unsubscribe_button,
)


def _brief_from_latest_json(latest_json: dict[str, Any]) -> dict[str, Any]:
    brief = latest_json.get("brief") if isinstance(latest_json, dict) else None
    if isinstance(brief, dict):
        return brief
    return latest_json if isinstance(latest_json, dict) else {}


def _append_unsubscribe_plain_text(plain_text: str, brief: dict[str, Any]) -> str:
    unsubscribe_text = render_plain_unsubscribe_text(brief)
    if not unsubscribe_text or unsubscribe_text in plain_text:
        return plain_text
    return f"{plain_text}\n\n{unsubscribe_text}"


def _append_unsubscribe_html(html_body: str, brief: dict[str, Any]) -> str:
    unsubscribe_button = render_unsubscribe_button(brief)
    if not unsubscribe_button or unsubscribe_button in html_body:
        return html_body
    if "</body>" in html_body:
        return html_body.replace("</body>", f"{unsubscribe_button}\n</body>", 1)
    return html_body + unsubscribe_button


def render_lite_email(latest_json: dict[str, Any]) -> dict[str, str]:
    brief = _brief_from_latest_json(latest_json)
    plain_text = render_lite_plain_text_shared(latest_json)
    html_body = render_lite_html_shared(latest_json)
    return {
        "plain_text": _append_unsubscribe_plain_text(plain_text, brief),
        "html_body": _append_unsubscribe_html(html_body, brief),
    }
