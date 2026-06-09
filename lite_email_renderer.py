from __future__ import annotations

import html
from typing import Any

from config import settings
from email_renderer import render_plain_unsubscribe_text, render_unsubscribe_button


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "；".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        return "；".join(_text(item) for item in value.values() if _text(item))
    return str(value).strip()


def _html(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def render_lite_email(latest_json: dict[str, Any]) -> dict[str, str]:
    brief = latest_json.get("brief") if isinstance(latest_json.get("brief"), dict) else latest_json
    takeaway = brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    three_things = brief.get("today_three_things") if isinstance(brief.get("today_three_things"), dict) else {}

    expressions = takeaway.get("golden_sentences") if isinstance(takeaway.get("golden_sentences"), list) else []
    expression = ""
    for item in expressions:
        if isinstance(item, dict):
            expression = _first_text(item.get("sentence"), item.get("text"))
        else:
            expression = _text(item)
        if expression:
            break
    expression = expression or _first_text(featured.get("rewritable_expression"), takeaway.get("framework"))
    theme = _first_text(brief.get("today_theme"), three_things.get("theme"), featured.get("theme"), latest_json.get("subject"))
    question_text = _first_text(question.get("question"), question.get("title"))
    tip = _first_text(
        (brief.get("reading_guide") or {}).get("takeaway") if isinstance(brief.get("reading_guide"), dict) else "",
        "今天先抓主题和题干，尝试自己列出 3 个作答角度；完整版会提供答案框架、金句拆解和素材迁移。",
    )
    entry_url = settings.paid_trial_entry_url or settings.feedback_base_url or "#"

    plain_text = "\n".join(
        [
            "公考晨读免费简版",
            f"今日主题：{theme}",
            f"一句表达：{expression}",
            f"今日一题：{question_text}",
            f"学习提示：{tip}",
            f"付费内测入口：{entry_url}",
        ]
    )
    html_body = f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f6f8fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;color:#0f172a;">
  <div style="max-width:620px;margin:0 auto;padding:18px 12px;">
    <div style="background:#174a7e;color:#fff;border-radius:16px;padding:18px 18px;margin-bottom:12px;">
      <div style="font-size:12px;letter-spacing:1.2px;opacity:.86;">DAILY BRIEFING 免费简版</div>
      <div style="font-size:23px;font-weight:900;line-height:1.35;margin-top:8px;">{_html(theme)}</div>
    </div>
    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:14px;padding:14px 15px;margin-bottom:12px;">
      <div style="font-size:13px;color:#165dff;font-weight:900;margin-bottom:6px;">一句表达</div>
      <div style="font-size:15px;line-height:1.75;color:#334155;">{_html(expression)}</div>
    </div>
    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:14px;padding:14px 15px;margin-bottom:12px;">
      <div style="font-size:13px;color:#b45309;font-weight:900;margin-bottom:6px;">今日一题</div>
      <div style="font-size:15px;line-height:1.75;color:#334155;font-weight:800;">{_html(question_text)}</div>
    </div>
    <div style="background:#eef6ff;border-left:4px solid #165dff;border-radius:12px;padding:12px 13px;margin-bottom:12px;">
      <div style="font-size:13px;color:#165dff;font-weight:900;margin-bottom:5px;">简短学习提示</div>
      <div style="font-size:14px;line-height:1.7;color:#334155;">{_html(tip)}</div>
    </div>
    <div style="background:#fff8e8;border:1px solid #fed7aa;border-radius:14px;padding:14px 15px;">
      <div style="font-size:15px;font-weight:900;color:#92400e;margin-bottom:7px;">付费内测</div>
      <div style="font-size:14px;line-height:1.75;color:#78350f;margin-bottom:10px;">付费内测版包含更多作答参考、表达拆解、素材迁移和周末复盘资料包。</div>
      <a href="{_html(entry_url)}" style="display:inline-block;background:#f59e0b;color:#fff;text-decoration:none;border-radius:999px;padding:9px 15px;font-size:14px;font-weight:900;">了解付费内测</a>
    </div>
  </div>
</body>
</html>"""
    unsubscribe_text = render_plain_unsubscribe_text(brief)
    if unsubscribe_text:
        plain_text = f"{plain_text}\n\n{unsubscribe_text}"
    unsubscribe_button = render_unsubscribe_button(brief)
    if unsubscribe_button:
        if "</body>" in html_body:
            html_body = html_body.replace("</body>", f"{unsubscribe_button}\n</body>", 1)
        else:
            html_body = html_body + unsubscribe_button
    return {"plain_text": plain_text, "html_body": html_body}
