from __future__ import annotations

import re
from typing import Any

import email_renderer as _email_renderer
from email_renderer import (
    as_list,
    ensure_dict,
    render_plain_unsubscribe_text,
    render_unsubscribe_button,
    strip_display_prefix,
)

LITE_FRAMEWORK_TITLE_OLD = "先想 3 个角度"
LITE_FRAMEWORK_TITLE_NEW = "先搭作答框架"


def _brief_from_latest_json(latest_json: dict[str, Any]) -> dict[str, Any]:
    brief = latest_json.get("brief") if isinstance(latest_json, dict) else None
    if isinstance(brief, dict):
        return brief
    return latest_json if isinstance(latest_json, dict) else {}


def _split_numbered_framework_text(value: str) -> list[str]:
    """Split a numbered answer-framework string without character-level truncation."""
    text = strip_display_prefix(value, "作答框架", "答题框架", "参考框架").strip()
    if not text:
        return []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?<!^)(?<!\n)\s+(?=\d{1,2}[\.、．]\s*)", "\n", text)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) <= 1:
        numbered = [part.strip() for part in re.split(r"(?:^|\s)(?=\d{1,2}[\.、．]\s*)", text) if part.strip()]
        if len(numbered) > 1:
            lines = numbered
    return lines


def _clean_answer_framework_item(item: Any) -> str:
    if isinstance(item, dict):
        label = str(item.get("label") or item.get("title") or item.get("name") or "").strip()
        content = str(item.get("content") or item.get("text") or item.get("desc") or item.get("summary") or "").strip()
        text = f"{label}：{content}" if label and content else (content or label)
    else:
        text = str(item or "").strip()
    text = strip_display_prefix(text, "作答框架", "答题框架", "参考框架").strip()
    text = re.sub(r"^\s*(?:\d{1,2}[\.、．]|[一二三四五六七八九十]+[、\.．])\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ，、")
    return text


def _patched_lite_answer_angles(brief: dict[str, Any]) -> list[str]:
    """Use the full-email answer framework for the lite email.

    免费简版不再二次压缩或截断作答框架，避免出现第 4 条半截句；
    仍只展示框架，不展示参考答案、30 秒表达等付费内容。
    """
    question = ensure_dict(brief.get("daily_question"))
    raw_value = question.get("answer_framework") or question.get("answer_frame")
    raw_items: list[Any]
    if isinstance(raw_value, str):
        raw_items = _split_numbered_framework_text(raw_value)
    else:
        raw_items = as_list(raw_value)

    angles: list[str] = []
    for item in raw_items:
        text = _clean_answer_framework_item(item)
        if text and text not in angles:
            angles.append(text)
        if len(angles) >= 4:
            break
    if angles:
        return angles

    hint_text = strip_display_prefix(
        question.get("breaking_hint") or question.get("breaking_direction") or question.get("exam_focus") or "",
        "作答主线",
        "审题关键",
    )
    fallback_angles: list[str] = []
    if hint_text:
        parts = [part.strip("，。； ") for part in re.split(r"[；。]", str(hint_text)) if part.strip("，。； ")]
        hint_labels = ("先稳矛盾", "再抓重点", "最后落地")
        for idx, part in enumerate(parts[:3]):
            fallback_angles.append(f"{hint_labels[idx]}：{part}")
    fallback_angles.extend(
        [
            "先摸诉求：先把群众顾虑和现实堵点找准。",
            "再定主线：把解决问题和推动协商结合起来。",
            "稳妥推进：依法沟通、逐步形成共识。",
        ]
    )
    for item in fallback_angles:
        text = _clean_answer_framework_item(item)
        if text and text not in angles:
            angles.append(text)
        if len(angles) >= 3:
            break
    return angles


def _install_lite_answer_framework_patch() -> None:
    _email_renderer._lite_answer_angles = _patched_lite_answer_angles


def _normalize_lite_framework_title(content: str) -> str:
    return content.replace(LITE_FRAMEWORK_TITLE_OLD, LITE_FRAMEWORK_TITLE_NEW)


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
    _install_lite_answer_framework_patch()
    brief = _brief_from_latest_json(latest_json)
    plain_text = _normalize_lite_framework_title(_email_renderer.render_lite_plain_text(latest_json))
    html_body = _normalize_lite_framework_title(_email_renderer.render_lite_email(latest_json))
    return {
        "plain_text": _append_unsubscribe_plain_text(plain_text, brief),
        "html_body": _append_unsubscribe_html(html_body, brief),
    }
