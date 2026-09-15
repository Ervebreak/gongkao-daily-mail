from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote, urlencode

from config import settings
from exam_transfer_card import build_exam_transfer_card
from lite_paid_cta import SAFE_LITE_CTA_FALLBACK, resolve_lite_paid_cta_payload


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


DISPLAY_PREFIXES = (
    "如果点原文，重点看",
    "可用表达",
    "作答主线",
    "审题关键",
    "换成考场话",
    "考场话",
)


def strip_exam_use_prefix(value: Any) -> str:
    return strip_display_prefix(value, "换成考场话", "考场话")


def strip_display_prefix(value: Any, *prefixes: str) -> str:
    text = str(value or "").strip()
    candidates = prefixes or DISPLAY_PREFIXES
    changed = True
    while changed:
        changed = False
        for prefix in candidates:
            clean_prefix = str(prefix or "").strip()
            if not clean_prefix:
                continue
            for candidate in (clean_prefix, f"{clean_prefix}：", f"{clean_prefix}:"):
                if text.startswith(candidate):
                    text = text[len(candidate):].strip()
                    changed = True
                    break
            if changed:
                break
    return text


def is_exam_use_display_item(value: Any) -> bool:
    text = str(value or "").strip()
    blocked_prefixes = ("可用表达", "可复用表达", "万能表达", "表达积累", "如果点原文，重点看", "审题关键", "作答主线")
    return bool(text) and not text.startswith(blocked_prefixes)


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


def split_candidate_answer_paragraphs(value: Any, limit: int = 450) -> list[str]:
    text = clip_text(value, limit)
    if not text:
        return []
    normalized = re.sub(r"(第一|第二|第三|第四|首先|其次|再次|最后|一是|二是|三是)", r"\n\1", text)
    parts = [part.strip() for part in normalized.splitlines() if part.strip()]
    if len(parts) >= 2:
        return parts[:4]

    sentences = [part.strip() for part in re.split(r"(?<=[。！？])", text) if part.strip()]
    if len(sentences) <= 1:
        return [text]

    paragraphs: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > 120:
            paragraphs.append(current.strip())
            current = sentence
        else:
            current += sentence
    if current.strip():
        paragraphs.append(current.strip())
    return paragraphs[:4] or [text]


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


def normalize_reading_guide(brief: dict[str, Any]) -> dict[str, str]:
    guide = ensure_dict(brief.get("reading_guide"))
    return {
        "core_value": clip_text(guide.get("core_value") or "", 45),
        "focus_path": clip_text(guide.get("focus_path") or "", 55),
        "learning_outcome": clip_text(guide.get("learning_outcome") or "", 55),
    }


def render_reading_guide_plain(brief: dict[str, Any]) -> list[str]:
    guide = normalize_reading_guide(brief)
    return [
        "📌 今天这封怎么用",
        "抓住一个点：" + str(guide.get("core_value") or ""),
        "重点看这里：" + str(guide.get("focus_path") or ""),
        "看完带走：" + str(guide.get("learning_outcome") or ""),
        "",
    ]


def render_reading_guide_html(brief: dict[str, Any]) -> str:
    guide = normalize_reading_guide(brief)
    return f"""
    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:15px;padding:13px 14px;margin-bottom:15px;">
      <div style="font-size:13px;color:#165dff;font-weight:900;margin-bottom:8px;">📌 今天这封怎么用</div>
      <div style="background:#eef6ff;border-left:4px solid #165dff;border-radius:10px;padding:8px 10px;line-height:1.6;font-size:14px;margin-bottom:7px;"><b>抓住一个点：</b>{h(guide.get('core_value') or '')}</div>
      <div style="background:#eef6ff;border-left:4px solid #165dff;border-radius:10px;padding:8px 10px;line-height:1.6;font-size:14px;margin-bottom:7px;"><b>重点看这里：</b>{h(guide.get('focus_path') or '')}</div>
      <div style="background:#fff8e8;border-left:4px solid #f59e0b;border-radius:10px;padding:8px 10px;line-height:1.6;font-size:14px;"><b>看完带走：</b>{h(guide.get('learning_outcome') or '')}</div>
    </div>
    """


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


def coordinate_quote_text(value: Any) -> str:
    return str(value or "").strip().rstrip("。；;！!？?")


def coordinate_source_text(value: Any) -> str:
    return str(value or "").strip().rstrip("。；;！!？?")


ANSWER_ANGLE_TRUNCATED_TAILS = (
    "责任主",
    "等方",
    "等机",
    "等措",
    "平台责",
    "转移中",
    "标准衔",
    "围绕企",
    "事项清",
    "闭环落",
)

ANSWER_ANGLE_DANGLING_ENDINGS = (
    "通过",
    "由于",
    "为了",
    "围绕",
    "依托",
    "推动",
    "促进",
    "强化",
    "完善",
    "构建",
    "形成",
    "建立",
)


def has_truncated_answer_angle(value: Any) -> bool:
    text = str(value or "").strip().rstrip("。；;！!？?")
    if not text:
        return False
    if any(text.endswith(tail) for tail in ANSWER_ANGLE_TRUNCATED_TAILS):
        return True
    if len(text) <= 8:
        return False
    if ("：" in text or ":" in text or "，" in text) and any(text.endswith(tail) for tail in ANSWER_ANGLE_DANGLING_ENDINGS):
        return True
    return False


def should_render_policy_coordinate(brief: dict[str, Any]) -> bool:
    coordinate = ensure_dict(brief.get("policy_coordinate"))
    display_type = str(coordinate.get("display_evidence_type") or "").strip().lower()
    if display_type in {"", "none"}:
        return False
    try:
        policy_match_score = float(coordinate.get("policy_match_score") or 0)
    except (TypeError, ValueError):
        policy_match_score = 0.0
    try:
        qiushi_match_score = float(coordinate.get("qiushi_match_score") or 0)
    except (TypeError, ValueError):
        qiushi_match_score = 0.0
    source_type = str(coordinate.get("source_type") or "").strip().lower()
    display_level = str(coordinate.get("display_level") or "").strip().lower()
    if display_level == "hidden":
        return False
    if display_type == "qiushi" and qiushi_match_score < 70:
        return False
    if display_type == "policy" and policy_match_score < 75:
        return False
    if source_type == "qiushi_only" and qiushi_match_score < 70:
        return False
    if source_type == "policy_only" and policy_match_score < 75:
        return False
    answer_angles = as_list(coordinate.get("answer_angles"))
    if any(has_truncated_answer_angle(item) for item in answer_angles):
        return False
    return True


def policy_coordinate_lines(brief: dict[str, Any]) -> list[str]:
    if not should_render_policy_coordinate(brief):
        return []
    coordinate = ensure_dict(brief.get("policy_coordinate"))
    display_type = str(coordinate.get("display_evidence_type") or "").strip().lower()
    policy_quote = coordinate_quote_text(coordinate.get("policy_quote"))
    policy_source = coordinate_source_text(coordinate.get("policy_source"))
    authoritative_quote = coordinate_quote_text(coordinate.get("authoritative_quote"))
    authoritative_source = coordinate_source_text(coordinate.get("authoritative_source"))
    if display_type in {"", "none"}:
        return []

    lines = ["【今日政策坐标】"]
    if display_type in {"policy", "both"} and policy_quote and policy_source:
        lines.append(f"政策原文：{policy_source}提出，“{policy_quote}”。")
    if display_type in {"qiushi", "both"} and authoritative_quote and authoritative_source:
        lines.append(f"权威论述：{authoritative_source}强调，“{authoritative_quote}”。")

    article_connection = str(coordinate.get("article_connection") or "").strip()
    exam_transfer = str(coordinate.get("exam_transfer") or "").strip()
    if article_connection:
        lines.append(f"文章落点：{article_connection}")
    if exam_transfer:
        lines.append(f"考场迁移：{exam_transfer}")
    return lines


def render_policy_coordinate_plain(brief: dict[str, Any]) -> list[str]:
    lines = policy_coordinate_lines(brief)
    return ["", *lines] if lines else []


def render_policy_coordinate_html(brief: dict[str, Any]) -> str:
    if not should_render_policy_coordinate(brief):
        return ""
    coordinate = ensure_dict(brief.get("policy_coordinate"))
    display_type = str(coordinate.get("display_evidence_type") or "").strip().lower()
    policy_quote = coordinate_quote_text(coordinate.get("policy_quote"))
    policy_source = coordinate_source_text(coordinate.get("policy_source"))
    authoritative_quote = coordinate_quote_text(coordinate.get("authoritative_quote"))
    authoritative_source = coordinate_source_text(coordinate.get("authoritative_source"))
    if display_type in {"", "none"}:
        return ""

    policy_block = ""
    if display_type in {"policy", "both"} and policy_quote and policy_source:
        policy_block = f"""
      <div style="font-size:14px;line-height:1.75;color:#334155;">
        <b>政策原文：</b>{h(policy_source)}提出，“{h(policy_quote)}”。
      </div>
        """
    authoritative_block = ""
    if display_type in {"qiushi", "both"} and authoritative_quote and authoritative_source:
        authoritative_block = f"""
      <div style="font-size:14px;line-height:1.75;color:#334155;margin-top:8px;">
        <b>权威论述：</b>{h(authoritative_source)}强调，“{h(authoritative_quote)}”。
      </div>
        """

    article_connection = str(coordinate.get("article_connection") or "").strip()
    exam_transfer = str(coordinate.get("exam_transfer") or "").strip()
    article_block = (
        f'<div style="font-size:14px;line-height:1.75;color:#334155;margin-top:8px;"><b>文章落点：</b>{h(article_connection)}</div>'
        if article_connection
        else ""
    )
    exam_block = (
        f'<div style="font-size:14px;line-height:1.75;color:#334155;margin-top:8px;"><b>考场迁移：</b>{h(exam_transfer)}</div>'
        if exam_transfer
        else ""
    )
    return f"""
    <h2 style="font-size:21px;margin:20px 0 10px;">今日政策坐标</h2>
    <div style="background:#fff;border:1px solid #dbeafe;border-radius:16px;padding:15px;margin-bottom:15px;">
      {policy_block}
      {authoritative_block}
      {article_block}
      {exam_block}
    </div>
    """


def exam_transfer_card_payload(brief: dict[str, Any]) -> dict[str, Any]:
    card = ensure_dict(brief.get("exam_transfer_card"))
    if card.get("surface_issue") and card.get("deep_logic") and card.get("exam_expression"):
        return card
    return build_exam_transfer_card(brief)


def render_exam_transfer_card_plain(brief: dict[str, Any]) -> list[str]:
    card = exam_transfer_card_payload(brief)
    transfer_angles = [clip_text(item, 42) for item in as_list(card.get("transfer_angles"))[:5] if str(item).strip()]
    lines = [
        "",
        "考场转化卡｜这篇文章到底考什么",
        "表面在讲：" + clip_text(card.get("surface_issue"), 100),
        "真正考点：" + clip_text(card.get("deep_logic"), 140),
    ]
    evidence_type = str(card.get("evidence_type") or "none").strip().lower()
    if evidence_type in {"policy", "both"} and card.get("policy_quote") and card.get("policy_source"):
        lines.append(f"政策原文：{card.get('policy_source')}——{card.get('policy_quote')}")
    if evidence_type in {"qiushi", "both"} and card.get("authoritative_quote") and card.get("authoritative_source"):
        lines.append(f"权威论述：{card.get('authoritative_source')}——{card.get('authoritative_quote')}")
    if card.get("exam_transfer"):
        lines.append("适合迁移到：" + clip_text(card.get("exam_transfer"), 150))
    if transfer_angles:
        lines.append("作答角度：")
        lines.extend(f"- {item}" for item in transfer_angles[:5])
    lines.append("一句能直接用：" + clip_text(card.get("exam_expression"), 80))
    return lines


def render_exam_transfer_card_html(brief: dict[str, Any]) -> str:
    card = exam_transfer_card_payload(brief)
    transfer_angles = [clip_text(item, 42) for item in as_list(card.get("transfer_angles"))[:5] if str(item).strip()]
    evidence_type = str(card.get("evidence_type") or "none").strip().lower()
    evidence_blocks: list[str] = []
    if evidence_type in {"policy", "both"} and card.get("policy_quote") and card.get("policy_source"):
        evidence_blocks.append(
            f'<div style="font-size:14px;line-height:1.72;color:#334155;margin-top:8px;"><b>政策原文：</b>{h(card.get("policy_source"))}——{h(card.get("policy_quote"))}</div>'
        )
    if evidence_type in {"qiushi", "both"} and card.get("authoritative_quote") and card.get("authoritative_source"):
        evidence_blocks.append(
            f'<div style="font-size:14px;line-height:1.72;color:#334155;margin-top:8px;"><b>权威论述：</b>{h(card.get("authoritative_source"))}——{h(card.get("authoritative_quote"))}</div>'
        )
    angle_block = ""
    if transfer_angles:
        angle_block = f"""
      <div style="margin-top:10px;">
        <div style="font-size:14px;font-weight:900;color:#165dff;margin-bottom:6px;">可迁移作答角度</div>
        <ul style="padding-left:19px;line-height:1.72;font-size:14px;margin:0;">{list_items(transfer_angles, 5)}</ul>
      </div>
        """
    transfer_summary = (
        f'<div style="font-size:14px;line-height:1.72;color:#334155;margin-top:10px;"><b>适合迁移到：</b>{h(clip_text(card.get("exam_transfer"), 150))}</div>'
        if card.get("exam_transfer")
        else ""
    )
    return f"""
      <div style="margin-top:12px;background:#f8fafc;border:1px solid #dbeafe;border-radius:14px;padding:12px;">
        <div style="font-size:14px;font-weight:900;color:#165dff;margin-bottom:8px;">考场转化卡｜这篇文章到底考什么</div>
        <div style="font-size:14px;line-height:1.72;color:#334155;"><b>表面在讲：</b>{h(clip_text(card.get("surface_issue"), 100))}</div>
        <div style="font-size:14px;line-height:1.72;color:#334155;margin-top:8px;"><b>真正考点：</b>{h(clip_text(card.get("deep_logic"), 140))}</div>
        {''.join(evidence_blocks)}
        {transfer_summary}
        {angle_block}
        <div style="margin-top:10px;background:#fff;border:1px solid #e6eaf0;border-radius:10px;padding:9px 10px;">
          <div style="font-size:13px;font-weight:900;color:#0f172a;margin-bottom:5px;">一句能直接写进答案里</div>
          <div style="font-size:14px;line-height:1.72;color:#334155;">{h(clip_text(card.get("exam_expression"), 80))}</div>
        </div>
      </div>
    """


FEEDBACK_FORM_URL = "https://wj.qq.com/s2/26569188/8ddc/"
FEEDBACK_UID_PLACEHOLDER = "__FEEDBACK_UID__"
FEEDBACK_EMAIL_HASH_PLACEHOLDER = "__FEEDBACK_EMAIL_HASH__"
UNSUBSCRIBE_SUBJECT = "退订公考晨读邮件"
UNSUBSCRIBE_BODY = (
    "你好，我想暂停/退订公考晨读邮件。"
    "请将我当前接收这封邮件的邮箱从发送名单中移除，谢谢。"
)


def _append_query(url: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


def _render_auto_unsubscribe_url(brief: dict[str, Any]) -> str:
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


def _render_mailto_unsubscribe_url() -> str:
    recipient = settings.unsubscribe_email.strip()
    if not recipient:
        return ""
    query = urlencode(
        {
            "subject": UNSUBSCRIBE_SUBJECT,
            "body": UNSUBSCRIBE_BODY,
        },
        quote_via=quote,
    )
    return f"mailto:{recipient}?{query}"


def render_unsubscribe_url(brief: dict[str, Any]) -> str:
    if settings.unsubscribe_mode == "auto" and settings.feedback_base_url.strip():
        auto_url = _render_auto_unsubscribe_url(brief)
        if auto_url:
            return auto_url
    return _render_mailto_unsubscribe_url()


def render_unsubscribe_button(brief: dict[str, Any]) -> str:
    url = render_unsubscribe_url(brief)
    if not url:
        return ""
    return f"""
    <div style="text-align:center;padding:8px 12px 18px;color:#64748b;font-size:12px;line-height:1.8;">
      如果你暂时不想继续接收，可以
      <a href="{h(url)}" target="_blank"
         style="color:#165dff;text-decoration:none;font-weight:800;">
        点击这里发送退订邮件
      </a>
      ，我会手动处理。
    </div>
    """


def render_plain_unsubscribe_text(brief: dict[str, Any]) -> str:
    url = render_unsubscribe_url(brief)
    if not url:
        return ""
    return f"如果你暂时不想继续接收，可以点击这里发送退订邮件，我会手动处理：{url}"


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


def _brief_from_latest_json(latest_json: dict[str, Any]) -> dict[str, Any]:
    brief = latest_json.get("brief") if isinstance(latest_json, dict) else None
    if isinstance(brief, dict):
        return brief
    return latest_json if isinstance(latest_json, dict) else {}


def _lite_paid_entry_url() -> str:
    return settings.paid_trial_entry_url.strip() or FEEDBACK_FORM_URL


def _lite_paid_mailto_url() -> str:
    recipient = settings.unsubscribe_email.strip()
    if not recipient:
        return ""
    query = urlencode(
        {
            "subject": "体验完整版晨读邮件",
            "body": "你好，我想体验完整版晨读邮件，请发我内测说明和付款方式。",
        },
        quote_via=quote,
    )
    return f"mailto:{recipient}?{query}"


def _lite_paid_feature_list() -> list[str]:
    return [
        "文章框架图",
        "考场转化",
        "原文问题链",
        "治理边界辨析",
        "素材迁移",
        "表达积累",
        "周末 PDF 汇编",
    ]


def _lite_paid_plan_list() -> list[str]:
    return [
        "4.9 元 / 7 天",
        "9.9 元 / 30 天",
    ]


def _lite_paid_plan_summary() -> str:
    return "｜".join(_lite_paid_plan_list())


def _lite_paid_feature_summary() -> str:
    return "、".join(_lite_paid_feature_list()) + "。"


def _lite_paid_highlight_topic(brief: dict[str, Any]) -> str:
    question = ensure_dict(brief.get("daily_question"))
    featured = ensure_dict(brief.get("featured_article"))
    value = (
        question.get("exam_focus")
        or question.get("breaking_hint")
        or question.get("breaking_direction")
        or featured.get("theme")
        or brief.get("today_theme")
        or "基层治理与公共服务"
    )
    return clip_text(strip_display_prefix(value, "审题关键", "作答主线", "换成考场话"), 24)


def _lite_paid_highlight_chain(brief: dict[str, Any]) -> str:
    labels: list[str] = []
    for item in _lite_answer_angles(brief):
        text = str(item or "").strip()
        if "：" in text:
            label = text.split("：", 1)[0]
        elif ":" in text:
            label = text.split(":", 1)[0]
        else:
            label = text
        label = re.sub(r"^\s*\d+[\.、\)]\s*", "", label).strip("，。、：:； ")
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= 4:
            break
    return "—".join(labels[:4])


def _lite_paid_highlight_scenarios(brief: dict[str, Any]) -> str:
    coordinate = ensure_dict(brief.get("policy_coordinate"))
    featured = ensure_dict(brief.get("featured_article"))
    question = ensure_dict(brief.get("daily_question"))
    scenario = (
        coordinate.get("exam_transfer")
        or question.get("breaking_direction")
        or question.get("exam_focus")
        or featured.get("theme")
        or brief.get("today_theme")
        or "基层治理、公共服务、作风建设类题"
    )
    return clip_text(strip_display_prefix(scenario, "考场迁移", "审题关键", "作答主线"), 40)


def _lite_paid_highlight_fallback(brief: dict[str, Any]) -> str:
    return SAFE_LITE_CTA_FALLBACK


def _lite_paid_highlight(latest_json: dict[str, Any], brief: dict[str, Any]) -> str:
    payload = resolve_lite_paid_cta_payload(latest_json, brief)
    highlight = str(payload.get("hook") or _lite_paid_highlight_fallback(brief)).strip()
    if isinstance(latest_json, dict):
        latest_json["_lite_paid_highlight"] = highlight
        latest_json["lite_paid_highlight"] = highlight
        latest_json["lite_paid_cta"] = {
            "hook_type": str(payload.get("hook_type") or "").strip(),
            "hook": highlight,
            "source_module": str(payload.get("source_module") or "").strip(),
            "fallback_used": bool(payload.get("fallback_used")),
        }
    brief["lite_paid_highlight"] = highlight
    brief["lite_paid_cta"] = {
        "hook_type": str(payload.get("hook_type") or "").strip(),
        "hook": highlight,
        "source_module": str(payload.get("source_module") or "").strip(),
        "fallback_used": bool(payload.get("fallback_used")),
    }
    return highlight


def _lite_theme(brief: dict[str, Any], latest_json: dict[str, Any]) -> str:
    return str(brief.get("today_theme") or brief.get("email_subject") or latest_json.get("subject") or "").strip()


def _lite_featured_title(brief: dict[str, Any]) -> str:
    featured = ensure_dict(brief.get("featured_article"))
    question = ensure_dict(brief.get("daily_question"))
    return str(
        featured.get("title")
        or question.get("question_source_title")
        or brief.get("email_subject")
        or brief.get("today_theme")
        or "今日晨读重点"
    ).strip()


def _lite_featured_one_sentence(brief: dict[str, Any]) -> str:
    featured = ensure_dict(brief.get("featured_article"))
    overview = as_list(featured.get("original_overview"))
    return clip_text(
        featured.get("one_sentence")
        or featured.get("core_viewpoint")
        or featured.get("main_thread")
        or (overview[0] if overview else "")
        or brief.get("today_focus")
        or "",
        180,
    )


def _lite_three_step_line(brief: dict[str, Any]) -> str:
    lite_email = ensure_dict(brief.get("lite_email"))
    manual = str(lite_email.get("three_step_line") or "").strip()
    if manual:
        return clip_text(manual, 48)

    featured = ensure_dict(brief.get("featured_article"))
    framework_map = ensure_dict(featured.get("article_framework_map"))
    framework_style = str(framework_map.get("framework_style") or "").strip()
    if framework_style:
        labels: list[str] = []
        for chunk in re.split(r"\s*(?:→|->)\s*", framework_style):
            piece = strip_display_prefix(chunk)
            piece = re.split(r"[：:]", piece, maxsplit=1)[0].strip()
            piece = re.sub(r"\s+", "", piece)[:8].strip("，、：:； ")
            if piece:
                labels.append(piece)
            if len(labels) >= 3:
                break
        line = " → ".join(labels)
        return line[:48].rstrip("，、：:； ") if line else ""

    steps = normalize_framework_steps(as_list(framework_map.get("steps")), 3)
    labels = [re.sub(r"\s+", "", str(step.get("label") or "").strip())[:8].strip("，、：:； ") for step in steps]
    labels = [item for item in labels if item][:3]
    line = " → ".join(labels)
    return line[:48].rstrip("，、：:； ") if line else ""


def _lite_expression(brief: dict[str, Any]) -> str:
    featured = ensure_dict(brief.get("featured_article"))
    return clip_text(strip_display_prefix(featured.get("rewritable_expression"), "可用表达", "一句表达"), 180)


def _lite_answer_angles(brief: dict[str, Any]) -> list[str]:
    question = ensure_dict(brief.get("daily_question"))
    theme = str(brief.get("today_theme") or "这个主题").strip()
    hint_text = strip_display_prefix(
        question.get("breaking_hint") or question.get("breaking_direction") or question.get("exam_focus") or "",
        "作答主线",
        "审题关键",
    )
    prompts = [
        "先看题目在问什么对象、什么矛盾、要你完成什么任务。",
        f"再想它和“{clip_text(theme, 18)}”有什么关系，别急着展开分点答案。",
    ]
    if hint_text:
        prompts.append(f"可以顺着这个方向想：{clip_text(hint_text, 42)}")
    else:
        prompts.append("可以先用一句话判断：这道题不是泛泛表态，而是要把问题放回具体场景里处理。")
    prompts.append("样例：我会先把问题和诉求看清楚，再考虑怎样把工作做得稳妥、可执行。")
    angles: list[str] = []
    for item in prompts:
        if item and item not in angles:
            angles.append(item)
        if len(angles) >= 4:
            break
    return angles


def _lite_quick_reads(brief: dict[str, Any]) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for item in as_list(brief.get("quick_reads"))[:2]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        cards.append(
            {
                "title": title,
                "source": str(item.get("source") or "").strip(),
                "theme": str(item.get("theme") or "").strip(),
                "one_sentence": clip_text(item.get("one_sentence") or "", 90),
            }
        )
    return cards


def _lite_required_missing(brief: dict[str, Any], latest_json: dict[str, Any]) -> list[str]:
    question = ensure_dict(brief.get("daily_question"))
    missing: list[str] = []
    if not _lite_featured_title(brief):
        missing.append("featured_title")
    if not _lite_featured_one_sentence(brief):
        missing.append("featured_one_sentence")
    if not today_question_text(brief) and not question.get("question"):
        missing.append("daily_question")
    if not _lite_theme(brief, latest_json):
        missing.append("theme")
    return missing


def render_lite_plain_text(latest_json: dict[str, Any]) -> str:
    brief = _brief_from_latest_json(latest_json)
    missing = _lite_required_missing(brief, latest_json)
    if missing and isinstance(latest_json, dict):
        latest_json["lite_quality_warning"] = missing

    featured = ensure_dict(brief.get("featured_article"))
    question_text = today_question_text(brief)
    three_step_line = _lite_three_step_line(brief)
    quick_reads = _lite_quick_reads(brief)
    paid_url = _lite_paid_entry_url()
    paid_mailto_url = _lite_paid_mailto_url() or paid_url
    paid_highlight = _lite_paid_highlight(latest_json, brief)
    meta = " / ".join(
        part
        for part in (
            str(featured.get("source") or "").strip(),
            str(featured.get("published_at") or "").strip(),
            str(featured.get("theme") or "").strip(),
        )
        if part
    )
    lines = [
        "公考晨读·免费简版",
        f"今日主题：{_lite_theme(brief, latest_json)}",
        "",
        "今日精读文章",
        f"标题：{_lite_featured_title(brief)}",
        f"信息：{meta}" if meta else "",
        f"原文链接：{featured.get('url') or ''}",
        f"一句话：{_lite_featured_one_sentence(brief)}",
    ]
    if three_step_line:
        lines.extend(["", f"3步看懂：{three_step_line}"])
    lines.extend(
        [
            "",
            f"一句可用表达：{_lite_expression(brief)}",
            "",
            "今日一题",
            question_text,
            "",
            "思考提示",
        ]
    )
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(_lite_answer_angles(brief), start=1))
    if quick_reads:
        lines.extend(["", "今日速读"])
        for idx, item in enumerate(quick_reads, start=1):
            quick_meta = " / ".join(part for part in (item["source"], item["theme"]) if part)
            lines.append(f"{idx}. {item['title']}")
            if quick_meta:
                lines.append(f"   {quick_meta}")
            if item["one_sentence"]:
                lines.append(f"   {item['one_sentence']}")
    lines.extend(
        [
            "",
            "今天完整版多讲了什么",
            "完整版会补充：",
            paid_highlight,
            "",
            f"完整版还包含：{_lite_paid_feature_summary()}",
            "",
            f"体验说明：{_lite_paid_plan_summary()}",
            "",
            f"回复“体验”了解说明：{paid_mailto_url}" if paid_mailto_url else "",
            f"查看报名表：{paid_url}" if paid_url else "",
            "暂时不参加也没关系，免费简版会继续保留。",
        ]
    )
    return "\n".join(line for line in lines if line is not None)


def render_lite_email(latest_json: dict[str, Any]) -> str:
    brief = _brief_from_latest_json(latest_json)
    missing = _lite_required_missing(brief, latest_json)
    if missing and isinstance(latest_json, dict):
        latest_json["lite_quality_warning"] = missing

    featured = ensure_dict(brief.get("featured_article"))
    question_text = today_question_text(brief)
    paid_url = _lite_paid_entry_url()
    paid_mailto_url = _lite_paid_mailto_url() or paid_url
    paid_highlight = _lite_paid_highlight(latest_json, brief)
    three_step_line = _lite_three_step_line(brief)
    angle_items = "".join(
        f'<li style="margin:0 0 8px;color:#334155;line-height:1.72;">{h(item)}</li>'
        for item in _lite_answer_angles(brief)
    )
    quick_read_cards = "".join(
        f"""
    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:14px;padding:14px 15px;margin-bottom:10px;">
      <div style="font-size:16px;line-height:1.6;font-weight:900;color:#0f172a;">{h(item['title'])}</div>
      <div style="font-size:12px;color:#64748b;margin-top:5px;">{h(' / '.join(part for part in (item['source'], item['theme']) if part))}</div>
      <div style="font-size:14px;line-height:1.72;color:#334155;margin-top:8px;">{h(item['one_sentence'])}</div>
    </div>"""
        for item in _lite_quick_reads(brief)
    )
    featured_meta = " / ".join(
        part
        for part in (
            str(featured.get("source") or "").strip(),
            str(featured.get("published_at") or "").strip(),
            str(featured.get("theme") or "").strip(),
        )
        if part
    )
    three_step_block = ""
    if three_step_line:
        three_step_block = f"""
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:14px;padding:14px 15px;margin-bottom:12px;">
      <div style="font-size:13px;color:#1d4ed8;font-weight:900;margin-bottom:6px;">3步看懂</div>
      <div style="font-size:15px;line-height:1.72;color:#1e3a8a;font-weight:800;">{h(three_step_line)}</div>
    </div>"""
    quick_reads_block = ""
    if quick_read_cards:
        quick_reads_block = f"""
    <div style="margin-bottom:12px;">
      <div style="font-size:13px;color:#0f172a;font-weight:900;margin:0 0 8px 2px;">今日速读</div>
      {quick_read_cards}
    </div>"""
    return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f6f8fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;color:#0f172a;">
  <div style="max-width:680px;margin:0 auto;padding:20px 12px;">
    <div style="background:linear-gradient(135deg,#123c73,#1d4ed8);color:#fff;border-radius:18px;padding:20px 18px;margin-bottom:14px;">
      <div style="font-size:12px;letter-spacing:1.3px;opacity:.84;">DAILY BRIEFING · 免费简版</div>
      <div style="font-size:24px;font-weight:900;line-height:1.35;margin-top:8px;">{h(_lite_theme(brief, latest_json))}</div>
    </div>

    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:16px;padding:16px 16px;margin-bottom:12px;">
      <div style="font-size:13px;color:#1d4ed8;font-weight:900;margin-bottom:6px;">今日精读文章</div>
      <div style="font-size:19px;line-height:1.5;font-weight:900;color:#0f172a;">{h(_lite_featured_title(brief))}</div>
      <div style="font-size:12px;color:#64748b;margin-top:6px;">{h(featured_meta)}</div>
      <div style="margin-top:8px;"><a href="{h(featured.get('url') or '')}" target="_blank" style="color:#1d4ed8;text-decoration:none;font-size:13px;font-weight:800;">查看原文</a></div>
      <div style="font-size:15px;line-height:1.75;color:#334155;margin-top:10px;">{h(_lite_featured_one_sentence(brief))}</div>
    </div>

    {three_step_block}

    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:14px;padding:14px 15px;margin-bottom:12px;">
      <div style="font-size:13px;color:#165dff;font-weight:900;margin-bottom:6px;">一句可用表达</div>
      <div style="font-size:15px;line-height:1.75;color:#334155;">{h(_lite_expression(brief))}</div>
    </div>

    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:14px;padding:14px 15px;margin-bottom:12px;">
      <div style="font-size:13px;color:#b45309;font-weight:900;margin-bottom:6px;">今日一题</div>
      <div style="font-size:15px;line-height:1.78;color:#334155;font-weight:800;">{h(question_text)}</div>
    </div>

    <div style="background:#f8fafc;border:1px solid #dbe4ee;border-radius:14px;padding:14px 15px;margin-bottom:12px;">
      <div style="font-size:13px;color:#0f172a;font-weight:900;margin-bottom:8px;">思考提示</div>
      <ol style="margin:0;padding-left:18px;">{angle_items}</ol>
    </div>

    {quick_reads_block}

    <div style="background:#fff8e8;border:1px solid #fed7aa;border-radius:16px;padding:15px 16px;">
      <div style="font-size:17px;font-weight:900;color:#92400e;margin-bottom:8px;">今天完整版多讲了什么</div>
      <div style="font-size:13px;color:#b45309;font-weight:900;margin-bottom:6px;">完整版会补充</div>
      <div style="font-size:14px;line-height:1.82;color:#78350f;margin-bottom:10px;">{h(paid_highlight)}</div>
      <div style="font-size:14px;line-height:1.8;color:#78350f;margin-bottom:8px;">完整版还包含：{h(_lite_paid_feature_summary())}</div>
      <div style="font-size:12px;line-height:1.7;color:#92400e;margin-bottom:12px;">体验说明：{h(_lite_paid_plan_summary())}</div>
      <div style="margin-bottom:10px;">
        <a href="{h(paid_mailto_url)}" target="_blank" style="display:inline-block;background:#fffbeb;color:#92400e;text-decoration:none;border:1px solid #fcd34d;border-radius:999px;padding:9px 14px;font-size:13px;font-weight:700;margin:0 8px 8px 0;">回复“体验”了解说明</a>
        <a href="{h(paid_url)}" target="_blank" style="display:inline-block;background:transparent;color:#92400e;text-decoration:none;border:1px solid #fdba74;border-radius:999px;padding:9px 14px;font-size:13px;font-weight:700;margin:0 8px 8px 0;">查看报名表</a>
      </div>
      <div style="font-size:13px;line-height:1.8;color:#92400e;">暂时不参加也没关系，免费简版会继续保留。</div>
    </div>
  </div>
</body>
</html>"""


def render_plain_text(brief: dict[str, Any]) -> str:
    featured = brief["featured_article"]
    question = brief["daily_question"]
    takeaway = brief["today_takeaway"]
    framework_map = ensure_dict(featured.get("article_framework_map"))
    steps = normalize_framework_steps(as_list(framework_map.get("steps") or featured.get("article_framework") or []), 5)
    golden = as_list(takeaway.get("golden_sentences"))[:2]
    original_focus = strip_display_prefix(featured.get("original_reading_focus"), "如果点原文，重点看")
    exam_focus = strip_display_prefix(
        question.get("exam_focus") or question.get("review_key") or question.get("breaking_direction"),
        "审题关键",
    )
    reference_sentence = strip_display_prefix(
        question.get("output_sentence_template") or question.get("thirty_second_answer") or "",
        "参考句式",
    )
    candidate_answer_paragraphs = split_candidate_answer_paragraphs(
        question.get("candidate_answer") or "附上考生版参考答案，方便对照作答。",
        450,
    )
    lines = [
        str(brief["email_subject"]),
        f"日期：{brief['date']}",
        f"今日主题：{brief['today_theme']}",
        "",
        *render_reading_guide_plain(brief),
        "今日精读｜面试表达与申论素材储备",
        f"{featured.get('title')}（{source_line(featured)}）",
        f"链接：{featured.get('url') or '原文链接暂不可用'}",
        f"备用搜索：{fallback_search_text(featured)}",
        ("如果点原文，重点看：" + original_focus) if original_focus else "",
        "一句话看懂：" + str(featured.get("one_sentence", "")),
        "",
        "文章框架图｜一眼看懂文章怎么展开",
        f"文章类型：{framework_map.get('type') or framework_map.get('article_type', '')}",
        f"文章主线：{framework_map.get('main_thread', '')}",
        *[
            f"{idx}. {step.get('label', '')}：{step.get('content', '')}"
            for idx, step in enumerate(steps, start=1)
        ],
        *render_exam_transfer_card_plain(brief),
        "",
        "今日一题｜考场转化训练",
        "题型：" + str(question.get("question_type", "")),
        "题目：" + str(question.get("question", today_question_text(brief))),
        "审题关键：" + exam_focus,
        "作答框架：" + "；".join(clip_text(item, 95) for item in (as_list(question.get("answer_framework")) or as_list(question.get("answer_frame")))[:4]),
        "考生版参考答案：",
        *candidate_answer_paragraphs,
        "30秒输出任务：" + clip_text(question.get("output_prompt") or "请用一句话写出这道题的开头表态。", 80),
        "我的一句话：________________",
        "参考句式：" + clip_text(reference_sentence, 120),
        "",
        "今日可带走｜1个常识 + 2句必备金句",
        "关键词：" + "、".join(str(item) for item in as_list(takeaway.get("keywords"))[:5]),
        "时政常识：" + "；".join(str(item) for item in as_list(takeaway.get("common_knowledge_points"))[:1]),
        "必备金句：" + "；".join(
            (item.get("sentence") if isinstance(item, dict) else str(item)) for item in golden
        ),
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
    quick_cards = render_quick_reads(brief)
    takeaway_gold = as_list(takeaway.get("golden_sentences"))[:2]
    common_points = as_list(takeaway.get("common_knowledge_points"))[:1]
    original_focus = strip_display_prefix(
        featured.get("original_reading_focus") or "点开原文时，重点看作者如何从具体事实推导出治理判断，以及哪些表述可以改写进申论或面试。",
        "如果点原文，重点看",
    )
    breaking_hint = strip_display_prefix(
        question.get("breaking_hint") or question.get("breaking_direction") or question.get("review_key") or "",
        "作答主线",
    )
    exam_focus = strip_display_prefix(
        question.get("exam_focus") or question.get("review_key") or question.get("breaking_direction"),
        "审题关键",
    )
    candidate_answer_html = "".join(
        f'<p style="margin:0 0 10px;line-height:1.78;">{h(paragraph)}</p>'
        for paragraph in split_candidate_answer_paragraphs(
            question.get("candidate_answer") or "我认为，解决这类问题，关键是把文章中的判断转成具体场景里的执行办法。",
            450,
        )
    )

    return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f6f8fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;color:#0f172a;">
  <div style="max-width:620px;margin:0 auto;padding:16px 12px;">
    <div style="background:linear-gradient(135deg,#174a7e,#1f78bd);color:#fff;border-radius:16px;padding:18px 18px;margin-bottom:12px;">
      <div style="font-size:12px;letter-spacing:1.4px;opacity:.86;">DAILY BRIEFING 每日晨读</div>
      <div style="font-size:24px;font-weight:900;line-height:1.32;margin-top:7px;">{h(brief['email_subject'])}</div>
      <div style="font-size:14px;line-height:1.65;margin-top:9px;opacity:.94;">{h(brief['today_focus'])}</div>
    </div>

    {render_reading_guide_html(brief)}

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

      {render_exam_transfer_card_html(brief)}

    </div>

    <h2 style="font-size:21px;margin:20px 0 10px;">今日一题｜考场转化训练</h2>
    <div style="background:#fff;border:1px solid #e6eaf0;border-radius:16px;padding:16px;margin-bottom:15px;">
      <div style="display:inline-block;background:#fff8e8;color:#b45309;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:900;margin-bottom:8px;">题型：{h(question.get('question_type'))}</div>
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:4px 0 5px;">题目</div>
      <div style="font-size:16px;font-weight:900;line-height:1.65;margin-bottom:10px;">{h(question.get('question') or three_question)}</div>
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:8px 0 5px;">审题关键</div>
      <div style="font-size:14px;line-height:1.7;color:#334155;background:#fff8e8;border-left:4px solid #f59e0b;border-radius:10px;padding:9px 10px;">{h(exam_focus)}</div>
      {f'<div style="font-size:14px;color:#b45309;font-weight:900;margin:11px 0 5px;">作答主线</div><div style="font-size:14px;line-height:1.7;color:#334155;background:#fff8e8;border-left:4px solid #f59e0b;border-radius:10px;padding:9px 10px;">{h(clip_text(breaking_hint, 140))}</div>' if breaking_hint else ''}
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:11px 0 5px;">作答框架</div>
      <ol style="padding-left:21px;line-height:1.72;font-size:14px;margin:0;">{render_question_frame(question)}</ol>
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:11px 0 5px;">考生版参考答案</div>
      <div style="font-size:14px;line-height:1.78;color:#334155;background:#f8fafc;border-radius:10px;padding:10px 11px;">
        {candidate_answer_html}
      </div>
      <div style="font-size:14px;color:#b45309;font-weight:900;margin:11px 0 5px;">30秒输出</div>
      <div style="font-size:14px;line-height:1.72;color:#334155;background:#fff8e8;border-radius:10px;padding:10px 11px;">
        <div style="font-weight:900;color:#3f3f46;margin-bottom:6px;">{h(normalize_output_prompt(question.get('output_prompt')))}</div>
        <div style="color:#64748b;margin:3px 0 7px;">我的一句话：________________</div>
        <div><span style="font-weight:900;color:#92400e;">参考句式：</span>{h(clip_text(normalize_reference_sentence(question), 120))}</div>
      </div>
    </div>

    <h2 style="font-size:21px;margin:20px 0 10px;">今日可带走｜1个常识 + 2句必备金句</h2>
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

