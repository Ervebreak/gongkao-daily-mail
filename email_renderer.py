from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlencode

from config import settings


def h(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def h_with_highlight(value: Any) -> str:
    """Escape text and render 【具体关键词】 as light-blue highlight tags.

    空标签如【重点词】【易考词】【关键词】不做高亮并会被清理掉，避免把提示词标签展示给用户。
    """
    raw = str(value or "").strip()
    banned = {"重点词", "易考词", "关键词", "重点", "易错点", "易考点"}
    parts: list[str] = []
    pos = 0
    for match in re.finditer(r"【([^】]{1,18})】", raw):
        parts.append(html.escape(raw[pos:match.start()], quote=True))
        term = match.group(1).strip()
        if term in banned:
            # 不展示空标签，仅移除标签文本本身。
            parts.append("")
        else:
            parts.append(
                '<span style="display:inline-block;background:#eaf2ff;color:#165dff;'
                'border-radius:999px;padding:1px 7px;margin:0 2px;font-weight:900;'
                'white-space:nowrap;">'
                + html.escape(term, quote=True)
                + '</span>'
            )
        pos = match.end()
    parts.append(html.escape(raw[pos:], quote=True))
    return "".join(parts)


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def clip_text(value: Any, limit: int) -> str:
    """Clip display text without ellipsis; prefer sentence-safe trimming."""
    text = str(value or "").strip().replace("……", "").replace("...", "").replace("…", "")
    if limit <= 0 or len(text) <= limit:
        return text
    head = text[:limit].rstrip("，、：:；; ")
    cut = max(head.rfind(mark) for mark in "。；;！!？?")
    if cut >= max(12, int(limit * 0.55)):
        return head[: cut + 1].strip()
    return head.rstrip("，、：:；;和与及并但由于通过")


def clip_no_ellipsis(value: Any, limit: int) -> str:
    """用于文章框架图等卡片：不输出省略号，尽量在句号/分号处截断，避免半句话。"""
    text = str(value or "").strip().replace("……", "").replace("...", "").replace("…", "")
    if limit <= 0 or len(text) <= limit:
        return text
    head = text[:limit]
    # 优先在较靠后的标点处截断，避免出现“但是/并且/通过”等半句。
    cut_positions = [head.rfind(mark) for mark in "。；;！!？?" ]
    cut = max(cut_positions)
    if cut >= max(12, int(limit * 0.55)):
        return head[: cut + 1].strip()
    return head.rstrip("，、 ：:；;但和与及并通过")


def strip_exam_use_prefix(value: Any) -> str:
    text = str(value or "").strip()
    for prefix in ["换成考场话：", "换成考场话:", "考场话：", "考场话:"]:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def is_exam_use_display_item(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and not text.startswith(("可用表达", "可复用表达", "万能表达", "表达积累"))


def is_framework_migration_step(item: Any) -> bool:
    if isinstance(item, dict):
        label = str(item.get("label") or item.get("title") or item.get("name") or "").strip()
        content = str(item.get("content") or item.get("text") or item.get("desc") or item.get("summary") or "").strip()
    else:
        text = str(item or "").strip()
        if "：" in text:
            label, content = text.split("：", 1)
        elif ":" in text:
            label, content = text.split(":", 1)
        else:
            label, content = text, ""
    merged = f"{label} {content}".strip()
    return label.startswith("考场迁移") or "这类题怎么用" in label or "考场迁移" in merged


def normalize_framework_steps(raw_steps: list[Any], limit: int = 5) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    for idx, item in enumerate(raw_steps, start=1):
        if is_framework_migration_step(item):
            continue
        if isinstance(item, dict):
            label = item.get("label") or f"节点{idx}"
            content = item.get("content") or item.get("text") or item.get("desc") or ""
        else:
            text = str(item)
            if "：" in text:
                label, content = text.split("：", 1)
            elif ":" in text:
                label, content = text.split(":", 1)
            else:
                label, content = f"节点{idx}", text
        if str(content).strip():
            steps.append({"label": str(label).strip(), "content": str(content).strip()})
        if len(steps) >= limit:
            break
    return steps


def normalize_output_prompt(value: Any) -> str:
    """30秒输出的任务提示：避免展示“复述框架/重点练习”等教研指令。"""
    text = str(value or "").strip()
    bad_markers = ["复述本题", "口头复述", "核心对策框架", "重点练习", "逻辑串联", "训练你的表达", "请用30秒口头复述"]
    if not text or any(marker in text for marker in bad_markers):
        return "请用一句话写出这道题的开头表态。"
    return text


def normalize_reference_sentence(question: dict[str, Any]) -> str:
    text = str(question.get('output_sentence_template') or question.get('thirty_second_answer') or '').strip().replace('……', '').replace('...', '').replace('…', '')
    bad_markers = ["复述本题", "口头复述", "核心对策框架", "重点练习", "逻辑串联", "训练你的表达", "请用30秒口头复述"]
    if not text or any(marker in text for marker in bad_markers):
        return "我认为，解决这类问题，关键是把材料中的判断转成具体场景里的执行办法，让政策要求真正落到群众可感、基层可做的工作中。"
    return text


def list_items(items: list[Any], limit: int | None = None) -> str:
    values = [item for item in items if str(item).strip()]
    if limit is not None:
        values = values[:limit]
    return "".join(f'<li style="margin:0 0 7px;">{h(item)}</li>' for item in values)


def numbered_items(items: list[Any], limit: int | None = None) -> str:
    values = [item for item in items if str(item).strip()]
    if limit is not None:
        values = values[:limit]
    return "".join(f'<li style="margin:0 0 8px;">{h(item)}</li>' for item in values)


def inline_tags(items: list[Any], limit: int | None = None) -> str:
    values = [item for item in items if str(item).strip()]
    if limit is not None:
        values = values[:limit]
    return "".join(
        '<span style="display:inline-block;background:#eef6ff;color:#165dff;'
        f'border-radius:999px;padding:4px 9px;margin:3px 5px 3px 0;font-size:12px;font-weight:800;">{h(item)}</span>'
        for item in values
    )


def render_golden_sentences(items: list[Any], limit: int = 2) -> str:
    rows = []
    for item in items[:limit]:
        if isinstance(item, dict):
            sentence = clip_text(item.get("sentence") or item.get("text") or item.get("content") or "", 60)
            scenario = clip_text(item.get("scenario") or item.get("scene") or item.get("适用场景") or "", 60)
        else:
            sentence = clip_text(item, 60)
            scenario = "申论 / 面试 / 公基热点表达"
        if str(sentence).strip():
            rows.append(
                '<li style="margin:0 0 9px;">'
                f'<div style="font-weight:900;color:#312e81;line-height:1.65;">{h(sentence)}</div>'
                f'<div style="font-size:12px;color:#6d28d9;margin-top:3px;">适用场景：{h(scenario or "申论 / 面试 / 公基热点表达")}</div>'
                "</li>"
            )
    return "".join(rows)


def button(url: str, label: str = "点击阅读原文") -> str:
    if not url:
        return ""
    return (
        f'<a href="{h(url)}" style="display:inline-block;background:#165dff;color:#fff;'
        'text-decoration:none;padding:8px 13px;border-radius:9px;font-size:13px;font-weight:900;">'
        f"{h(label)}</a>"
    )


def fallback_search_text(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").strip()
    source = str(item.get("source") or "").strip()
    if title and source:
        return f"{title} {source}"
    return title or source or "文章标题 来源"


def render_source_link_block(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    status = str(item.get("url_status") or ("valid" if url else "missing")).lower()
    search = fallback_search_text(item)
    if not url or status in {"invalid", "missing"}:
        return (
            '<div style="margin-top:10px;background:#f8fafc;border:1px solid #e6eaf0;'
            'border-radius:12px;padding:9px 10px;font-size:12px;line-height:1.7;color:#64748b;">'
            f"原文链接暂不可用，可搜索【{h(search)}】查看。"
            "</div>"
        )
    if status == "warning":
        return (
            '<div style="margin-top:10px;">'
            f'{button(url)}'
            '<div style="font-size:12px;line-height:1.65;color:#94a3b8;margin-top:6px;">'
            f"如打不开，可搜索【{h(search)}】。"
            "</div></div>"
        )
    return f'<div style="margin-top:10px;">{button(url)}</div>'


def source_line(item: dict[str, Any]) -> str:
    source = item.get("source") or "权威媒体"
    published_at = item.get("published_at") or item.get("date") or "日期待识别"
    theme = item.get("theme")
    if theme:
        return f"来源：{source}　发布时间：{published_at}　主题：{theme}"
    return f"来源：{source}　发布时间：{published_at}"


def today_question_text(brief: dict[str, Any]) -> str:
    three = ensure_dict(brief.get("today_three_things"))
    featured = ensure_dict(brief.get("featured_article"))
    question = ensure_dict(brief.get("daily_question"))
    value = three.get("daily_question") or featured.get("daily_question") or question.get("question")
    if value:
        return str(value)
    theme = brief.get("today_theme") or "今日主题"
    return f"请结合【{theme}】写一句开头表态。"


def render_framework_map(framework_map: dict[str, Any] | list[Any], limit: int = 5) -> str:
    if isinstance(framework_map, dict):
        article_type = framework_map.get("type") or framework_map.get("article_type") or "文章类型待识别"
        main_thread = framework_map.get("main_thread") or ""
        exam_tags = as_list(framework_map.get("exam_tags"))
        raw_steps = as_list(framework_map.get("steps"))
    else:
        article_type = "文章类型待识别"
        main_thread = ""
        exam_tags = []
        raw_steps = as_list(framework_map)
    steps = normalize_framework_steps(raw_steps, limit)
    if not steps:
        steps = [
            {"label": "文章主线", "content": main_thread or "围绕今日主题提炼现实问题和作答主线。"},
            {"label": "现实矛盾", "content": "从具体事实中找到治理堵点和表达素材。"},
            {"label": "总结落点", "content": "把文章判断转化为可复述、可作答的短表达。"},
        ]
    rows = []
    for idx, step in enumerate(steps, start=1):
        # 数字从左侧大圆点改为标题内的小徽标，减少手机端横向占位。
        rows.append(
            '<div style="background:#eef6ff;border-left:3px solid #165dff;border-radius:10px;padding:8px 10px;margin:0 0 7px;">'
            '<div style="font-size:13px;font-weight:900;color:#165dff;margin-bottom:4px;line-height:1.35;overflow-wrap:anywhere;">'
            f'<span style="display:inline-block;min-width:24px;text-align:center;background:#165dff;color:#fff;border-radius:999px;padding:1px 6px;margin-right:7px;font-size:11px;line-height:17px;vertical-align:1px;">{idx:02d}</span>'
            f'{h(clip_no_ellipsis(step["label"], 0))}</div>'
            f'<div style="font-size:14px;line-height:1.62;color:#1e293b;">{h(clip_no_ellipsis(step["content"], 96))}</div>'
            "</div>"
        )
    header = (
        '<div style="font-size:12px;color:#64748b;line-height:1.65;margin-bottom:8px;">'
        f"文章类型：{h(article_type)}"
        + (f"　主线：{h(clip_no_ellipsis(main_thread, 90))}" if main_thread else "")
        + "</div>"
    )
    return header + "".join(rows)


def render_question_frame(question: dict[str, Any]) -> str:
    return numbered_items((as_list(question.get("answer_framework")) or as_list(question.get("answer_frame")))[:4], 4)


def render_quick_reads(brief: dict[str, Any]) -> str:
    quick_cards = ""
    for item in as_list(brief.get("quick_reads"))[:2]:
        row = ensure_dict(item)
        one_sentence = clip_text(row.get("one_sentence") or "", 60)
        exam_value = clip_text(row.get("exam_value") or "可作为申论热点素材补充。", 80)
        quick_cards += f"""
        <div style="border:1px solid #e6eaf0;border-radius:14px;padding:13px 14px;margin:10px 0;background:#fff;">
          <div style="font-size:17px;font-weight:900;color:#0f172a;line-height:1.45;margin-bottom:5px;">{h(row.get('title'))}</div>
          <div style="font-size:12px;color:#64748b;margin-bottom:8px;">{h(source_line(row))}</div>
          <div style="font-size:14px;line-height:1.7;color:#334155;"><b>一句话概括：</b>{h(one_sentence)}</div>
          <div style="font-size:14px;line-height:1.7;color:#334155;margin-top:4px;"><b>考试价值：</b>{h(exam_value)}</div>
          {render_source_link_block(row)}
        </div>
        """
    return quick_cards


FEEDBACK_FORM_URL = "https://wj.qq.com/s2/26569188/8ddc/"
FEEDBACK_UID_PLACEHOLDER = "__FEEDBACK_UID__"
FEEDBACK_EMAIL_HASH_PLACEHOLDER = "__FEEDBACK_EMAIL_HASH__"


def _append_query(url: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


def render_unsubscribe_url(brief: dict[str, Any]) -> str:
    base_url = settings.feedback_base_url.strip()
    if not base_url:
        return ""
    mail_id = str(brief.get("mail_id") or brief.get("date") or "").strip()
    params = {
        "task": "unsubscribe",
        "date": str(brief.get("date") or "").strip(),
        "mail_id": mail_id,
        "uid": FEEDBACK_UID_PLACEHOLDER,
        "email_hash": FEEDBACK_EMAIL_HASH_PLACEHOLDER,
    }
    return _append_query(base_url, params)


def render_unsubscribe_button(brief: dict[str, Any]) -> str:
    url = render_unsubscribe_url(brief)
    if not url:
        return ""
    return f"""
    <div style="text-align:center;padding:8px 12px 18px;">
      <a href="{h(url)}" target="_blank"
         style="display:inline-block;color:#64748b;text-decoration:none;border:1px solid #cbd5e1;
                border-radius:999px;padding:7px 14px;font-size:12px;font-weight:700;">
        不想继续接收，点击退订
      </a>
    </div>
    """


def render_plain_unsubscribe_text(brief: dict[str, Any]) -> str:
    url = render_unsubscribe_url(brief)
    if not url:
        return ""
    return f"退订：{url}"


def render_feedback_buttons(brief: dict[str, Any]) -> str:
    """Render a stable third-party questionnaire entry.

    We intentionally do not use the old FC feedback buttons here.
    The previous direct feedback endpoint caused mailbox/browser jump issues
    and once shared the same function entry with the daily mailer.
    For the current internal-test stage, a third-party form is safer.
    """
    form_url = FEEDBACK_FORM_URL
    return f"""
      <div style="font-size:13px;line-height:1.75;color:#334155;margin-bottom:10px;">
        如果方便，可以用 30 秒反馈一下今天这封：哪些模块有用、哪里需要精简。
      </div>
      <div style="margin:10px 0 12px;">
        <a href="{h(form_url)}" target="_blank"
           style="display:inline-block;background:#165dff;color:#fff;text-decoration:none;
                  border-radius:999px;padding:9px 16px;font-size:14px;font-weight:900;">
          点这里填写反馈
        </a>
      </div>
      <div style="font-size:13px;line-height:1.75;color:#64748b;">
        也可以直接回复邮件告诉我：有用 / 太长 / 今日一题不错 / 框架图不错 / 金句表达有用。
      </div>
    """


def render_plain_text(brief: dict[str, Any]) -> str:
    featured = brief["featured_article"]
    question = brief["daily_question"]
    takeaway = brief["today_takeaway"]
    framework_map = ensure_dict(featured.get("article_framework_map"))
    steps = normalize_framework_steps(as_list(framework_map.get("steps") or featured.get("article_framework") or []), 5)
    golden = as_list(takeaway.get("golden_sentences"))[:2]
    lines = [
        str(brief["email_subject"]),
        f"日期：{brief['date']}",
        f"今日主题：{brief['today_theme']}",
        "",
        "今日精读｜面试表达与申论素材储备",
        f"{featured.get('title')}（{source_line(featured)}）",
        f"链接：{featured.get('url') or '原文链接暂不可用'}",
        f"备用搜索：{fallback_search_text(featured)}",
        ("如果点原文，重点看：" + str(featured.get("original_reading_focus", ""))) if featured.get("original_reading_focus") else "",
        "一句话看懂：" + str(featured.get("one_sentence", "")),
        "记住3个点：",
        *[f"- {clip_text(item, 90)}" for item in as_list(featured.get("three_useful_points"))[:3]],
        "换成考场话：",
        *[
            f"- {clip_text(strip_exam_use_prefix(item), 120)}"
            for item in as_list(featured.get("exam_use") or featured.get("usable_for_exam"))
            if is_exam_use_display_item(item)
        ][:2],
        "可用表达：" + clip_text(featured.get("rewritable_expression", ""), 80),
        "",
        "文章框架图｜一眼看懂文章怎么展开",
        f"文章类型：{framework_map.get('type') or framework_map.get('article_type', '')}",
        f"文章主线：{framework_map.get('main_thread', '')}",
        *[
            f"{idx}. {step.get('label', '')}：{step.get('content', '')}"
            for idx, step in enumerate(steps, start=1)
        ],
        "",
        "今日一题｜考场转化训练",
        "题型：" + str(question.get("question_type", "")),
        "题目：" + str(question.get("question", today_question_text(brief))),
        "审题关键：" + str(question.get("exam_focus") or question.get("breaking_direction", "")),
        "作答框架：" + "；".join(clip_text(item, 95) for item in (as_list(question.get("answer_framework")) or as_list(question.get("answer_frame")))[:4]),
        "考生版参考答案：" + clip_text(question.get("candidate_answer") or "", 450),
        "30秒输出任务：" + clip_text(question.get("output_prompt") or "请用一句话写出这道题的开头表态。", 80),
        "我的一句话：________________",
        "参考句式：" + clip_text(question.get("output_sentence_template") or question.get("thirty_second_answer") or "", 120),
        "",
        "今日可带走｜1个常识 + 2句必备金句 + 1个框架",
        "关键词：" + "、".join(str(item) for item in as_list(takeaway.get("keywords"))[:5]),
        "时政常识：" + "；".join(str(item) for item in as_list(takeaway.get("common_knowledge_points"))[:1]),
        "必备金句：" + "；".join(
            (item.get("sentence") if isinstance(item, dict) else str(item)) for item in golden
        ),
        "可迁移框架：" + clip_text(takeaway.get("framework", ""), 50),
        "",
        "今日速读｜申论素材补充",
        *[
            f"- {item.get('title')}（{source_line(item)}）：{item.get('exam_value') or item.get('one_sentence') or ''} 链接：{item.get('url') or '原文链接暂不可用'}"
            for item in as_list(brief.get("quick_reads"))[:2]
            if isinstance(item, dict)
        ],
    ]
    unsubscribe_text = render_plain_unsubscribe_text(brief)
    if unsubscribe_text:
        lines.extend(["", unsubscribe_text])
    return "\n".join(lines)


def render_email_html(brief: dict[str, Any]) -> str:
    featured = brief["featured_article"]
    question = brief["daily_question"]
    takeaway = brief["today_takeaway"]
    three = ensure_dict(brief["today_three_things"])
    three_theme = three.get("theme") or brief.get("today_theme") or "今日主题"
    three_sentence = three.get("must_remember_sentence") or featured.get("core_viewpoint") or brief.get("today_focus")
    three_question = today_question_text(brief)
    framework_map = ensure_dict(featured.get("article_framework_map"))
    original_overview = as_list(featured.get("original_overview"))[:2]
    useful_points = [clip_text(item, 90) for item in as_list(featured.get("three_useful_points"))[:3]]
    exam_use_source = as_list(featured.get("exam_use") or featured.get("usable_for_exam"))
    exam_use = [clip_text(strip_exam_use_prefix(item), 120) for item in exam_use_source if is_exam_use_display_item(item)][:2]
    quick_cards = render_quick_reads(brief)
    takeaway_gold = as_list(takeaway.get("golden_sentences"))[:2]
    common_points = as_list(takeaway.get("common_knowledge_points"))[:1]
    original_focus = featured.get("original_reading_focus") or "点开原文时，重点看作者如何从具体事实推导出治理判断，以及哪些表述可以改写进申论或面试。"
    breaking_hint = question.get("breaking_hint") or question.get("breaking_direction") or question.get("review_key") or ""

    return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f6f8fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;color:#0f172a;">
  <div style="max-width:620px;margin:0 auto;padding:16px 12px;">
    <div style="background:linear-gradient(135deg,#174a7e,#1f78bd);color:#fff;border-radius:16px;padding:18px 18px;margin-bottom:12px;">
      <div style="font-size:12px;letter-spacing:1.4px;opacity:.86;">DAILY BRIEFING 每日晨读</div>
      <div style="font-size:24px;font-weight:900;line-height:1.32;margin-top:7px;">{h(brief['email_subject'])}</div>
      <div style="font-size:14px;line-height:1.65;margin-top:9px;opacity:.94;">{h(brief['today_focus'])}</div>
    </div>

    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:15px;padding:13px 14px;margin-bottom:15px;">
      <div style="font-size:13px;color:#165dff;font-weight:900;margin-bottom:8px;">今日 3 件事</div>
      <div style="background:#eef6ff;border-left:4px solid #165dff;border-radius:10px;padding:8px 10px;line-height:1.6;font-size:14px;margin-bottom:7px;"><b>【今日主题】</b>{h(three_theme)}</div>
      <div style="background:#eef6ff;border-left:4px solid #165dff;border-radius:10px;padding:8px 10px;line-height:1.6;font-size:14px;margin-bottom:7px;"><b>【核心判断】</b>{h(three_sentence)}</div>
      <div style="background:#fff8e8;border-left:4px solid #f59e0b;border-radius:10px;padding:8px 10px;line-height:1.6;font-size:14px;"><b>【今日一题】</b>{h(three_question)}</div>
    </div>

    <h2 style="font-size:21px;margin:20px 0 8px;">今日精读｜面试表达与申论素材储备</h2>
    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:16px;padding:16px;margin-bottom:15px;">
      <div style="font-size:12px;color:#64748b;margin-bottom:6px;">{h(source_line(featured))}</div>
      <div style="font-size:21px;font-weight:900;line-height:1.42;margin-bottom:10px;">{h(featured['title'])}</div>
      {render_source_link_block(featured)}

      <div style="margin-top:10px;background:#eef6ff;border-left:4px solid #165dff;border-radius:12px;padding:10px 11px;">
        <div style="font-size:14px;font-weight:900;color:#165dff;margin-bottom:6px;">如果点原文，重点看</div>
        <div style="font-size:14px;line-height:1.72;color:#334155;">{h(clip_text(original_focus, 120))}</div>
      </div>

      <div style="background:#f8fafc;border-radius:12px;padding:11px;margin-top:10px;">
        <div style="font-size:14px;font-weight:900;color:#165dff;margin-bottom:6px;">一句话看懂</div>
        <div style="font-size:14px;line-height:1.72;color:#334155;">{h(featured.get('one_sentence') or featured.get('core_viewpoint'))}</div>
      </div>

      <div style="margin-top:12px;background:#fff;border:1px solid #dbeafe;border-radius:14px;padding:12px;">
        <div style="font-size:14px;font-weight:900;color:#165dff;margin-bottom:8px;">文章框架图｜一眼看懂文章怎么展开</div>
        {render_framework_map(framework_map, 5)}
      </div>

      <div style="margin-top:12px;background:#eef6ff;border-left:4px solid #165dff;border-radius:10px;padding:11px;">
        <div style="font-size:14px;font-weight:900;color:#165dff;margin-bottom:6px;">记住3个点</div>
        <ol style="padding-left:21px;line-height:1.72;font-size:14px;margin:0;">{numbered_items(useful_points, 3)}</ol>
      </div>

      <div style="margin-top:12px;background:#fffdf6;border:1px solid #fde7b7;border-radius:12px;padding:11px;">
        <div style="font-size:14px;font-weight:900;color:#b45309;margin-bottom:6px;">换成考场话</div>
        <ul style="padding-left:19px;line-height:1.72;font-size:14px;margin:0;">{list_items(exam_use, 2)}</ul>
      </div>

      <div style="margin-top:12px;background:#f8fafc;border-radius:12px;padding:10px 11px;">
        <div style="font-size:14px;font-weight:900;color:#0f172a;margin-bottom:6px;">可用表达</div>
        <div style="font-size:14px;line-height:1.72;color:#334155;">{h(clip_text(featured.get('rewritable_expression'), 80))}</div>
      </div>

    </div>


    <h2 style="font-size:21px;margin:20px 0 10px;">今日一题｜考场转化训练</h2>
    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:16px;padding:16px;margin-bottom:15px;">
      <div style="display:inline-block;background:#fff8e8;color:#b45309;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:900;margin-bottom:8px;">题型：{h(question.get('question_type'))}</div>
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:4px 0 5px;">题目</div>
      <div style="font-size:16px;font-weight:900;line-height:1.65;margin-bottom:10px;">{h(question.get('question') or three_question)}</div>
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:8px 0 5px;">审题关键</div>
      <div style="font-size:14px;line-height:1.7;color:#334155;background:#fff8e8;border-left:4px solid #f59e0b;border-radius:10px;padding:9px 10px;">{h(question.get('exam_focus') or question.get('review_key') or question.get('breaking_direction'))}</div>
      {f'<div style="font-size:14px;color:#b45309;font-weight:900;margin:11px 0 5px;">破题提示</div><div style="font-size:14px;line-height:1.7;color:#334155;background:#fff8e8;border-left:4px solid #f59e0b;border-radius:10px;padding:9px 10px;">{h(clip_text(breaking_hint, 140))}</div>' if breaking_hint else ''}
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:11px 0 5px;">作答框架</div>
      <ol style="padding-left:21px;line-height:1.72;font-size:14px;margin:0;">{render_question_frame(question)}</ol>
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:11px 0 5px;">考生版参考答案</div>
      <div style="font-size:14px;line-height:1.78;color:#334155;background:#f8fafc;border-radius:10px;padding:10px 11px;">
        {h(clip_text(question.get('candidate_answer') or '我认为，解决这类问题，关键是把文章中的判断转成具体场景里的执行办法。', 450))}
      </div>
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:11px 0 5px;">30秒输出</div>
      <div style="font-size:14px;line-height:1.72;color:#334155;background:#fff8e8;border-radius:10px;padding:10px 11px;">
        <div style="font-weight:900;color:#3f3f46;margin-bottom:6px;">{h(normalize_output_prompt(question.get('output_prompt')))}</div>
        <div style="color:#64748b;margin:3px 0 7px;">我的一句话：________________</div>
        <div><span style="font-weight:900;color:#92400e;">参考句式：</span>{h(clip_text(normalize_reference_sentence(question), 120))}</div>
      </div>
    </div>

    <h2 style="font-size:21px;margin:20px 0 10px;">今日可带走｜1个常识 + 2句必备金句 + 1个框架</h2>
    <div style="background:#fff;border:1px solid #dbeafe;border-radius:16px;padding:15px;margin-bottom:15px;">
      <div style="font-size:14px;font-weight:900;color:#165dff;margin-bottom:6px;">今日关键词</div>
      <div style="margin-bottom:11px;">{inline_tags(takeaway.get('keywords', []), 3)}</div>
      <div style="background:#ecfdf5;border-left:4px solid #10b981;border-radius:10px;padding:10px 11px;margin-bottom:11px;">
        <div style="font-size:14px;font-weight:900;color:#047857;margin-bottom:6px;">时政常识</div>
        <ul style="padding-left:19px;line-height:1.68;font-size:14px;margin:0;">{"".join(f"<li>{h_with_highlight(item)}</li>" for item in common_points[:1])}</ul>
      </div>
      <div style="background:#f5f3ff;border-left:4px solid #8b5cf6;border-radius:10px;padding:10px 11px;margin-bottom:10px;">
        <div style="font-size:14px;font-weight:900;color:#6d28d9;margin-bottom:6px;">必备金句</div>
        <ul style="padding-left:19px;line-height:1.68;font-size:14px;margin:0;">{render_golden_sentences(takeaway_gold, 2)}</ul>
      </div>
      <div style="background:#eef6ff;border-left:4px solid #165dff;border-radius:10px;padding:10px 11px;margin-bottom:10px;">
        <div style="font-size:14px;font-weight:900;color:#165dff;margin-bottom:6px;">可迁移框架</div>
        <div style="font-size:13px;line-height:1.65;color:#475569;">{h(clip_text(takeaway.get("framework"), 50))}</div>
      </div>
      {f'<div style="font-size:14px;font-weight:900;color:#165dff;margin-bottom:6px;">拓展联想</div><div style="font-size:13px;line-height:1.65;color:#475569;background:#f8fafc;border-radius:10px;padding:8px 10px;">{h(takeaway.get("extension"))}</div>' if takeaway.get("extension") else ''}
    </div>

    <h2 style="font-size:21px;margin:20px 0 8px;">今日速读｜申论素材补充</h2>
    {quick_cards}

    <div style="background:#f8fafc;border:1px solid #e6eaf0;border-radius:14px;padding:14px 15px;margin:18px 0 12px;color:#334155;">
      <div style="font-size:15px;font-weight:900;color:#0f172a;margin-bottom:8px;">内测反馈｜30 秒帮我优化一下</div>
      <div style="line-height:1.9;">{render_feedback_buttons(brief)}</div>
    </div>

    <div style="font-size:11px;line-height:1.7;color:#94a3b8;text-align:center;padding:12px;">本内容用于公考/考编晨读积累，建议结合原文、考试大纲和真题场景理解使用。</div>
    {render_unsubscribe_button(brief)}
  </div>
</body>
</html>"""
