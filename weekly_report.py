from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from typing import Any

import requests

from config import settings
from daily_archive import put_oss_object
from email_sender import send_email
from history import oss_config, oss_headers, oss_ready, oss_url

TZ = dt.timezone(dt.timedelta(hours=8))


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "；".join(_clean(x) for x in value if _clean(x))
    if isinstance(value, dict):
        return "；".join(_clean(x) for x in value.values() if _clean(x))
    return str(value).strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _plain_text(value: Any) -> str:
    text = _clean(value)
    return (
        text.replace("**", "")
        .replace("•", "-")
        .replace("·", "-")
        .replace("……", "")
        .replace("...", "")
        .strip()
    )


def _limit_text(value: Any, max_chars: int = 120) -> str:
    text = _plain_text(value)
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars + 1]
    # Prefer a complete short sentence instead of a hard clipped half sentence.
    for mark in ["。", "；", ";", "！", "？", ",", "，"]:
        pos = cut.rfind(mark)
        if pos >= max(24, max_chars // 2):
            return cut[: pos + 1].strip()
    return cut[:max_chars].rstrip("，,；;、：:").strip()


def _numbered_lines(items: list[Any], limit: int = 4, max_chars: int = 90) -> list[str]:
    rows: list[str] = []
    for idx, item in enumerate(_as_list(items)[:limit], start=1):
        text = _limit_text(item, max_chars)
        if text:
            rows.append(f"{idx:02d} {text}")
    return rows


def _date_range(end_date: dt.date, days: int) -> list[str]:
    start = end_date - dt.timedelta(days=max(days, 1) - 1)
    return [(start + dt.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(max(days, 1))]


def _oss_get_text(object_key: str) -> tuple[bool, str, str]:
    if not oss_ready():
        return False, "", "OSS配置不完整"
    cfg = oss_config()
    cfg["object_key"] = object_key.strip().lstrip("/")
    try:
        resp = requests.get(oss_url(cfg), headers=oss_headers("GET", cfg), timeout=20)
        if resp.status_code == 404:
            return False, "", "not_found"
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        return True, resp.text, ""
    except Exception as exc:
        return False, "", str(exc)


def load_daily_archives(end_date: dt.date | None = None, days: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    end_date = end_date or dt.datetime.now(TZ).date()
    days = days or settings.weekly_pdf_days
    rows: list[dict[str, Any]] = []
    misses: list[dict[str, str]] = []
    prefix = settings.daily_archive_prefix.strip().strip("/")
    for date_text in _date_range(end_date, days):
        key = f"{prefix}/{date_text}.json"
        ok, text, err = _oss_get_text(key)
        if not ok:
            misses.append({"date": date_text, "key": key, "error": err})
            continue
        try:
            payload = json.loads(text)
            payload.setdefault("date", date_text)
            # Also load the archived HTML for the weekly compilation PDF.
            # The daily JSON is useful for metadata, but the HTML archive is the
            # closest representation of the complete email that users received.
            html_key = f"{prefix}/{date_text}.html"
            html_ok, html_text, _html_err = _oss_get_text(html_key)
            if html_ok and html_text:
                payload["_archived_html"] = html_text
                payload["_archived_html_key"] = html_key
            rows.append(payload)
        except Exception as exc:
            misses.append({"date": date_text, "key": key, "error": f"json_parse_failed: {exc}"})
    return rows, misses


def brief_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("brief") or payload


def daily_summary(payload: dict[str, Any]) -> dict[str, Any]:
    brief = brief_from_payload(payload)
    featured = brief.get("featured_article") or {}
    question = brief.get("daily_question") or {}
    takeaway = brief.get("today_takeaway") or {}
    quick_reads = [x for x in _as_list(brief.get("quick_reads")) if isinstance(x, dict)]
    framework_map = featured.get("article_framework_map") or {}
    steps = framework_map.get("steps") or featured.get("article_framework") or []
    return {
        "date": payload.get("date") or brief.get("date") or "",
        "subject": payload.get("subject") or brief.get("email_subject") or "",
        "theme": brief.get("today_theme") or featured.get("theme") or "",
        "focus": brief.get("today_focus") or featured.get("one_sentence") or "",
        "featured_title": featured.get("title") or "",
        "featured_source": featured.get("source") or "",
        "featured_url": featured.get("url") or "",
        "featured_one_sentence": featured.get("one_sentence") or featured.get("core_viewpoint") or "",
        "framework_type": framework_map.get("type") or framework_map.get("article_type") or featured.get("article_type") or "",
        "framework_thread": framework_map.get("main_thread") or featured.get("main_thread") or "",
        "framework_steps": steps,
        "question_type": question.get("question_type") or "",
        "question": question.get("question") or "",
        "answer_framework": question.get("answer_framework") or question.get("answer_frame") or [],
        "keywords": takeaway.get("keywords") or [],
        "golden_sentences": takeaway.get("golden_sentences") or [],
        "takeaway_framework": takeaway.get("framework") or "",
        "quick_reads": quick_reads,
    }


def build_weekly_markdown(payloads: list[dict[str, Any]], start_date: str, end_date: str, misses: list[dict[str, str]]) -> str:
    lines: list[str] = []
    lines.append(f"# 公考晨读本周复盘资料包｜{start_date} 至 {end_date}")
    lines.append("")
    lines.append("> 用途：周末集中复盘、热点素材归档、申论/面试练习。")
    lines.append("")
    lines.append("## 一、本周目录")
    for payload in payloads:
        s = daily_summary(payload)
        lines.append(f"- **{s['date']}｜{s['theme']}**：{s['featured_title']}（{s['featured_source']}）")
    if misses:
        lines.append("")
        lines.append("### 未纳入的日期")
        for miss in misses:
            lines.append(f"- {miss.get('date')}：{miss.get('error')}")
    lines.append("")
    lines.append("## 二、每日精读与考场转化")
    for payload in payloads:
        s = daily_summary(payload)
        lines.append("")
        lines.append(f"## {s['date']}｜{s['theme']}")
        lines.append(f"**精读文章**：{s['featured_title']}（{s['featured_source']}）")
        if s["featured_one_sentence"]:
            lines.append(f"**一句话看懂**：{s['featured_one_sentence']}")
        if s["framework_type"] or s["framework_thread"] or s["framework_steps"]:
            lines.append("")
            lines.append("### 文章框架图")
            if s["framework_type"]:
                lines.append(f"- 文章类型：{s['framework_type']}")
            if s["framework_thread"]:
                lines.append(f"- 文章主线：{s['framework_thread']}")
            for idx, step in enumerate(_as_list(s["framework_steps"])[:5], start=1):
                if isinstance(step, dict):
                    label = step.get("label") or f"第{idx}层"
                    content = step.get("content") or ""
                    lines.append(f"- {idx}. **{label}**：{content}")
                else:
                    lines.append(f"- {idx}. {step}")
        lines.append("")
        lines.append("### 今日一题")
        if s["question_type"]:
            lines.append(f"- 题型：{s['question_type']}")
        lines.append(f"- 题目：{s['question']}")
        if s["answer_framework"]:
            lines.append("- 作答框架：" + "；".join(_clean(x) for x in _as_list(s["answer_framework"])[:4]))
        lines.append("")
        lines.append("### 今日可带走")
        if s["keywords"]:
            lines.append("- 关键词：" + "、".join(_clean(x) for x in _as_list(s["keywords"])[:5]))
        gold_rows = []
        for g in _as_list(s["golden_sentences"])[:2]:
            gold_rows.append(g.get("sentence") if isinstance(g, dict) else _clean(g))
        if gold_rows:
            lines.append("- 必备金句：" + "；".join(x for x in gold_rows if x))
        if s["takeaway_framework"]:
            lines.append("- 可迁移框架：" + s["takeaway_framework"])
        if s["quick_reads"]:
            lines.append("")
            lines.append("### 速读补充")
            for item in s["quick_reads"][:2]:
                lines.append(f"- {item.get('title','')}（{item.get('source','')}）：{item.get('exam_value') or item.get('one_sentence') or ''}")
    return "\n".join(lines).strip() + "\n"


def build_weekly_html(payloads: list[dict[str, Any]], start_date: str, end_date: str, misses: list[dict[str, str]]) -> str:
    def p(text: Any) -> str:
        return html.escape(_clean(text))

    cards = []
    toc = []
    for payload in payloads:
        s = daily_summary(payload)
        toc.append(f"<li><b>{p(s['date'])}｜{p(s['theme'])}</b>：{p(s['featured_title'])}（{p(s['featured_source'])}）</li>")
        steps_html = ""
        for idx, step in enumerate(_as_list(s["framework_steps"])[:5], start=1):
            if isinstance(step, dict):
                steps_html += f"<li><b>{p(step.get('label') or f'第{idx}层')}</b>：{p(step.get('content'))}</li>"
            else:
                steps_html += f"<li>{p(step)}</li>"
        gold = []
        for g in _as_list(s["golden_sentences"])[:2]:
            gold.append(g.get("sentence") if isinstance(g, dict) else _clean(g))
        quick_html = "".join(
            f"<li>{p(item.get('title'))}（{p(item.get('source'))}）：{p(item.get('exam_value') or item.get('one_sentence'))}</li>"
            for item in s["quick_reads"][:2]
        )
        cards.append(f"""
        <section class="day-card">
          <div class="date">{p(s['date'])}</div>
          <h2>{p(s['theme'])}</h2>
          <p class="article"><b>精读：</b>{p(s['featured_title'])}（{p(s['featured_source'])}）</p>
          <p><b>一句话看懂：</b>{p(s['featured_one_sentence'])}</p>
          <div class="block"><b>文章框架图</b><ul>{steps_html}</ul></div>
          <div class="block"><b>今日一题</b><p>{p(s['question'])}</p></div>
          <div class="block"><b>今日可带走</b><p>关键词：{p('、'.join(_clean(x) for x in _as_list(s['keywords'])[:5]))}</p><p>金句：{p('；'.join(x for x in gold if x))}</p></div>
          <div class="block"><b>速读补充</b><ul>{quick_html}</ul></div>
        </section>
        """)
    miss_html = "" if not misses else "<h3>未纳入日期</h3><ul>" + "".join(f"<li>{p(m.get('date'))}：{p(m.get('error'))}</li>" for m in misses) + "</ul>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>公考晨读周汇总</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;background:#f6f8fb;color:#0f172a;margin:0;padding:24px;}}
.wrap{{max-width:820px;margin:0 auto;}}
.cover{{background:linear-gradient(135deg,#174a7e,#1f78bd);color:white;border-radius:18px;padding:28px;margin-bottom:18px;}}
h1{{font-size:30px;margin:0 0 8px;}} h2{{font-size:22px;margin:0 0 10px;}} .day-card{{background:white;border:1px solid #e6eaf0;border-radius:16px;padding:18px;margin:16px 0;page-break-inside:avoid;}}
.date{{color:#165dff;font-weight:800;font-size:13px;margin-bottom:5px;}} .block{{background:#f8fafc;border-radius:12px;padding:12px;margin-top:10px;}} li{{line-height:1.75;}} p{{line-height:1.75;}}
</style></head><body><div class="wrap">
<div class="cover"><div>WEEKLY REVIEW 周末复盘</div><h1>公考晨读周汇总</h1><p>{p(start_date)} 至 {p(end_date)}</p></div>
<div class="day-card"><h2>本周目录</h2><ul>{''.join(toc)}</ul>{miss_html}</div>
{''.join(cards)}
</div></body></html>"""


def build_weekly_pdf(markdown_text: str, pdf_path: Path, title: str) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except Exception as exc:
        raise RuntimeError("缺少 reportlab 依赖，无法生成 PDF。请在 requirements.txt 或 FC 依赖层加入 reportlab。") from exc

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    base = ParagraphStyle("CN", parent=styles["Normal"], fontName="STSong-Light", fontSize=10.5, leading=17, spaceAfter=6)
    h1 = ParagraphStyle("CNH1", parent=base, fontSize=20, leading=28, alignment=TA_CENTER, textColor=colors.HexColor("#174a7e"), spaceAfter=14)
    h2 = ParagraphStyle("CNH2", parent=base, fontSize=15, leading=22, textColor=colors.HexColor("#165dff"), spaceBefore=10, spaceAfter=8)
    h3 = ParagraphStyle("CNH3", parent=base, fontSize=12.5, leading=19, textColor=colors.HexColor("#0f172a"), spaceBefore=6, spaceAfter=5)
    bullet_style = ParagraphStyle("CNBullet", parent=base, leftIndent=12, firstLineIndent=-8)
    quote_style = ParagraphStyle("CNQuote", parent=base, leftIndent=10, textColor=colors.HexColor("#475569"), backColor=colors.HexColor("#f8fafc"))

    def esc(s: str) -> str:
        return html.escape(s).replace("  ", "&nbsp;&nbsp;")

    # Build from the Markdown heading itself. Do not pre-insert the title,
    # otherwise the first Markdown H1 will trigger a PageBreak and create a
    # nearly blank first page.
    story: list[Any] = []
    seen_h1 = False
    for line in markdown_text.splitlines():
        raw = line.rstrip()
        if not raw:
            if story:
                story.append(Spacer(1, 4))
            continue
        if raw.startswith("# "):
            # Only start a new page for a second or later H1. The first H1 is
            # the document title and should stay on page 1.
            if seen_h1 and story:
                story.append(PageBreak())
            seen_h1 = True
            story.append(Paragraph(esc(raw[2:]), h1))
        elif raw.startswith("## "):
            story.append(Paragraph(esc(raw[3:]), h2))
        elif raw.startswith("### "):
            story.append(Paragraph(esc(raw[4:]), h3))
        elif raw.startswith("> "):
            story.append(Paragraph(esc(raw[2:]), quote_style))
        elif raw.startswith("- "):
            text = raw[2:].replace("**", "")
            # Some mobile PDF viewers render the bullet glyph as '?', especially
            # with CID fonts. Use ASCII '-' for maximum compatibility after download.
            story.append(Paragraph("- " + esc(text), bullet_style))
        else:
            story.append(Paragraph(esc(raw.replace("**", "")), base))

    if not story:
        story.append(Paragraph(esc(title), h1))

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    doc.build(story)




def build_weekly_pdf_booklet(payloads: list[dict[str, Any]], misses: list[dict[str, str]], pdf_path: Path, start_date: str, end_date: str) -> None:
    """Generate a booklet-style weekly PDF.

    Design goals:
    - first page is a real cover, not a blank title page;
    - avoid the bullet glyph that may render as '?' in some mobile PDF viewers;
    - use compact cards, practice questions and material excerpts instead of a pure text dump.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
            KeepTogether,
        )
    except Exception as exc:
        raise RuntimeError("缺少 reportlab 依赖，无法生成 PDF。请在 requirements.txt 或 FC 依赖层加入 reportlab。") from exc

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()

    navy = colors.HexColor("#153B73")
    blue = colors.HexColor("#165DFF")
    light_blue = colors.HexColor("#EFF6FF")
    pale = colors.HexColor("#F8FAFC")
    line = colors.HexColor("#DDE7F2")
    gray = colors.HexColor("#475569")
    dark = colors.HexColor("#0F172A")
    red = colors.HexColor("#B42318")

    base = ParagraphStyle("CN", parent=styles["Normal"], fontName="STSong-Light", fontSize=9.2, leading=14.5, textColor=dark, spaceAfter=4)
    small = ParagraphStyle("Small", parent=base, fontSize=8.2, leading=12, textColor=gray)
    tiny = ParagraphStyle("Tiny", parent=base, fontSize=7.5, leading=10.5, textColor=gray)
    cover_title = ParagraphStyle("CoverTitle", parent=base, fontSize=25, leading=34, alignment=TA_CENTER, textColor=colors.white, spaceAfter=8)
    cover_sub = ParagraphStyle("CoverSub", parent=base, fontSize=12, leading=18.5, alignment=TA_CENTER, textColor=colors.white)
    h1 = ParagraphStyle("H1", parent=base, fontSize=18, leading=25.5, textColor=navy, spaceBefore=4, spaceAfter=10)
    h2 = ParagraphStyle("H2", parent=base, fontSize=13.5, leading=20, textColor=blue, spaceBefore=8, spaceAfter=6)
    h3 = ParagraphStyle("H3", parent=base, fontSize=11, leading=16, textColor=dark, spaceBefore=3, spaceAfter=4)
    tag = ParagraphStyle("Tag", parent=base, fontSize=8.4, leading=11, textColor=blue)
    quote = ParagraphStyle("Quote", parent=base, fontSize=9.2, leading=14.2, textColor=dark, leftIndent=4, rightIndent=4)

    def esc(s: Any) -> str:
        return html.escape(_plain_text(s)).replace("\n", "<br/>")

    def para(text: Any, style: ParagraphStyle = base) -> Paragraph:
        return Paragraph(esc(text), style)

    def chip(text: Any) -> Paragraph:
        return Paragraph(esc(text), tag)

    def card(rows: list[list[Any]], widths: list[float] | None = None, bg=colors.white):
        tbl = Table(rows, colWidths=widths, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 0.7, line),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#EDF2F7")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return tbl

    summaries = [daily_summary(p) for p in payloads]
    theme_count = len([s for s in summaries if s.get("theme")])
    question_count = len([s for s in summaries if s.get("question")])
    gold_count = sum(len(_as_list(s.get("golden_sentences"))[:2]) for s in summaries)

    story: list[Any] = []

    # Cover page
    story.append(Spacer(1, 28 * mm))
    cover_table = Table([
        [Paragraph("公考晨读", cover_sub)],
        [Paragraph("本周复盘资料包", cover_title)],
        [Paragraph(f"{esc(start_date)} 至 {esc(end_date)}", cover_sub)],
        [Paragraph("每日精读 - 文章框架 - 每日一题 - 素材摘抄", cover_sub)],
    ], colWidths=[160 * mm])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), navy),
        ("BOX", (0, 0), (-1, -1), 0, navy),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(cover_table)
    story.append(Spacer(1, 10 * mm))
    stat_rows = [[para("本周精读", small), para(str(len(summaries)), h2), para("每日一题", small), para(str(question_count), h2), para("金句素材", small), para(str(gold_count), h2)]]
    story.append(card(stat_rows, widths=[25*mm, 20*mm, 25*mm, 20*mm, 25*mm, 20*mm], bg=light_blue))
    story.append(Spacer(1, 8 * mm))
    intro = "这一版先按每日晨读原有内容整理，重点保留每天的精读文章、文章框架、每日一题、可带走素材和速读补充。等每日模块结构稳定后，再升级为按热点、题型、素材、框架分区的月刊/特刊版。"
    story.append(card([[para(intro, quote)]], widths=[160*mm], bg=pale))
    story.append(PageBreak())

    # TOC / week overview
    story.append(Paragraph("01 本周目录", h1))
    toc_rows = [[para("日期", h3), para("主题", h3), para("精读文章", h3)]]
    for s in summaries:
        toc_rows.append([
            para(s.get("date"), small),
            para(_limit_text(s.get("theme"), 24), base),
            para(f"{_limit_text(s.get('featured_title'), 42)}（{_limit_text(s.get('featured_source'), 10)}）", small),
        ])
    story.append(card(toc_rows, widths=[28*mm, 45*mm, 86*mm]))
    if misses:
        story.append(Spacer(1, 5))
        miss_text = "；".join(f"{m.get('date')}：{m.get('error')}" for m in misses[:8])
        story.append(card([[para("未纳入日期", h3), para(miss_text, small)]], widths=[32*mm, 127*mm], bg=pale))

    story.append(Spacer(1, 10))
    story.append(Paragraph("02 本周热点速览", h1))
    hot_rows = []
    for idx, s in enumerate(summaries, start=1):
        keywords = "、".join(_limit_text(x, 12) for x in _as_list(s.get("keywords"))[:4])
        hot_rows.append([para(f"{idx:02d}", h2), para(_limit_text(s.get("theme"), 30), h3), para(keywords or "-", small)])
    if hot_rows:
        story.append(card(hot_rows, widths=[16*mm, 58*mm, 85*mm], bg=colors.white))
    story.append(PageBreak())

    # Daily-first review cards. This is intentionally not a separate true-question bank.
    story.append(Paragraph("03 每日内容复盘", h1))
    story.append(Paragraph("说明：本周先按每天晨读内容归档，保留原有模块；其中“每日一题”来自当天邮件，不等同于真题库。", small))
    story.append(Spacer(1, 5))
    for idx, s in enumerate(summaries, start=1):
        steps = []
        if s.get("framework_type"):
            steps.append(f"文章类型：{_limit_text(s.get('framework_type'), 36)}")
        if s.get("framework_thread"):
            steps.append(f"文章主线：{_limit_text(s.get('framework_thread'), 72)}")
        for j, step in enumerate(_as_list(s.get("framework_steps"))[:5], start=1):
            if isinstance(step, dict):
                label = _limit_text(step.get("label") or f"第{j}层", 18)
                content = _limit_text(step.get("content"), 68)
                steps.append(f"{j:02d} {label} - {content}" if content else f"{j:02d} {label}")
            else:
                steps.append(f"{j:02d} {_limit_text(step, 86)}")
        step_text = "<br/>".join(esc(x) for x in steps) or "-"

        answer = "；".join(_limit_text(x, 86) for x in _as_list(s.get("answer_framework"))[:4])
        gold = []
        for g in _as_list(s.get("golden_sentences"))[:2]:
            gold.append(_limit_text(g.get("sentence") if isinstance(g, dict) else g, 76))
        keywords = "、".join(_limit_text(x, 12) for x in _as_list(s.get("keywords"))[:5])
        quick_text = "；".join(
            f"{_limit_text(item.get('title'), 24)}（{_limit_text(item.get('source'), 8)}）"
            for item in _as_list(s.get("quick_reads"))[:2]
            if isinstance(item, dict)
        )

        rows = [
            [chip(f"DAY {idx:02d}  {s.get('date')}  |  {_limit_text(s.get('theme'), 28)}")],
            [para(f"精读文章：{_limit_text(s.get('featured_title'), 72)}（{_limit_text(s.get('featured_source'), 12)}）", base)],
            [para(f"一句话看懂：{_limit_text(s.get('featured_one_sentence') or s.get('focus'), 120)}", quote)],
            [Paragraph(f"<b>文章框架</b><br/>{step_text}", base)],
            [Paragraph(f"<b>每日一题</b><br/>{esc(_limit_text(s.get('question'), 220))}", base)],
            [para(f"参考框架：{answer or '-'}", small)],
            [para(f"关键词：{keywords or '-'}", small)],
            [para(f"可背表达：{'；'.join(gold) if gold else '-'}", small)],
            [para(f"速读补充：{quick_text or '-'}", small)],
        ]
        story.append(KeepTogether([card(rows, widths=[160*mm], bg=colors.white), Spacer(1, 9)]))

    story.append(PageBreak())

    # Material index remains as a lightweight cross-day summary.
    story.append(Paragraph("04 素材摘抄索引", h1))
    story.append(Paragraph("这一页只做跨天索引，方便回看；详细题目和框架仍放在每日内容复盘中。", small))
    material_rows = [[para("日期", h3), para("关键词", h3), para("可背表达 / 金句", h3)]]
    for s in summaries:
        keywords = "、".join(_limit_text(x, 10) for x in _as_list(s.get("keywords"))[:5])
        gold = []
        for g in _as_list(s.get("golden_sentences"))[:2]:
            gold.append(_limit_text(g.get("sentence") if isinstance(g, dict) else g, 70))
        material_rows.append([para(s.get("date"), small), para(keywords or "-", small), para("；".join(gold) or "-", small)])
    story.append(card(material_rows, widths=[28*mm, 48*mm, 83*mm]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("05 可迁移框架", h1))
    for idx, s in enumerate(summaries, start=1):
        fw = _limit_text(s.get("takeaway_framework"), 160)
        if fw:
            story.append(card([[chip(f"{idx:02d} {s.get('date')}｜{_limit_text(s.get('theme'), 22)}"), para(fw, small)]], widths=[58*mm, 101*mm], bg=colors.white))
            story.append(Spacer(1, 5))

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("STSong-Light", 8)
        canvas.setFillColor(gray)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"公考晨读本周复盘资料包 - {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"公考晨读本周复盘资料包｜{start_date}至{end_date}",
    )
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)




def _clean_pdf_line(line: str) -> str:
    """Clean archive/email text before placing it into the weekly PDF."""
    import ast
    import re
    text = html.unescape(str(line or "")).strip()
    if not text:
        return ""
    text = text.replace("•", "-").replace("·", "-").replace("…", "").replace("……", "").replace("...", "")
    text = text.replace("适用场景：适用场景：", "适用场景：")
    text = text.replace("主题：['", "主题：['")
    text = " ".join(text.split())

    # Hide unfinished placeholders from early test emails.
    bad_markers = ["待补充", "第X条", "第 X 条", "XXX", "xxxx"]
    if any(m in text for m in bad_markers):
        return ""

    # Convert Python-list-looking text into user-friendly slash-separated text.
    def repl_list(match: re.Match[str]) -> str:
        raw = match.group(0)
        try:
            value = ast.literal_eval(raw)
            if isinstance(value, (list, tuple)):
                return " / ".join(str(x).strip(" '\"") for x in value if str(x).strip())
        except Exception:
            pass
        return raw

    text = re.sub(r"\[[^\[\]]{2,160}\]", repl_list, text)
    return text.strip()


def _html_to_plain_lines(html_text: str) -> list[str]:
    """Convert the archived daily email HTML into readable plain-text lines.

    The weekly PDF is a compilation for end users, so we keep learning content
    but remove repeated feedback footers, email-client noise and placeholders.
    """
    if not html_text:
        return []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")
        for node in soup(["script", "style", "noscript", "svg"]):
            node.decompose()
        for a in soup.find_all("a"):
            href = (a.get("href") or "").strip()
            text = a.get_text(" ", strip=True)
            if href and href.startswith("http") and href not in text and len(text) <= 12:
                a.append(f" {href}")
        text = soup.get_text("\n", strip=True)
    except Exception:
        import re
        text = re.sub(r"<script[\s\S]*?</script>", "", html_text, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "\n", text)

    lines: list[str] = []
    seen_blank = False
    skip_markers = [
        "如果邮件显示异常", "退订", "unsubscribe", "内测反馈", "回复本邮件",
        "Open in browser", "查看原文", "欢迎直接回复", "今天这封有没有帮助",
        "哪个模块最有用", "内容会不会太长", "如果每天早上", "哪怕只回一句",
        "内容长度：", "最有用：", "今日一题：像考试题", "本内容用于公考",
        "如果你希望后续增加每日/每周 PDF", "后续会优先测试每周PDF", "后续会优先测试每周 PDF",
        "① 今天这封", "② 哪个模块", "③ 内容会不会", "④ 如果每天",
    ]
    for raw in text.splitlines():
        line = _clean_pdf_line(raw)
        if not line:
            if not seen_blank and lines:
                lines.append("")
            seen_blank = True
            continue
        if any(x.lower() in line.lower() for x in skip_markers):
            continue
        seen_blank = False
        if not lines or lines[-1] != line:
            lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _structured_daily_lines(summary: dict[str, Any]) -> list[str]:
    """Fallback when a daily HTML archive is unavailable."""
    lines: list[str] = []
    def add(label: str, value: Any):
        text = _plain_text(value)
        if text:
            lines.append(f"{label}：{text}")
    add("今日主题", summary.get("theme"))
    add("精读文章", f"{summary.get('featured_title')}（{summary.get('featured_source')}）")
    add("一句话看懂", summary.get("featured_one_sentence") or summary.get("focus"))
    if summary.get("framework_type") or summary.get("framework_thread") or summary.get("framework_steps"):
        lines.append("文章框架图")
        add("文章类型", summary.get("framework_type"))
        add("文章主线", summary.get("framework_thread"))
        for idx, step in enumerate(_as_list(summary.get("framework_steps"))[:8], start=1):
            if isinstance(step, dict):
                label = step.get("label") or f"第{idx}层"
                content = step.get("content") or ""
                lines.append(f"{idx}. {label}：{content}" if content else f"{idx}. {label}")
            else:
                lines.append(f"{idx}. {_plain_text(step)}")
    if summary.get("question"):
        lines.append("今日一题")
        add("题型", summary.get("question_type"))
        add("题目", summary.get("question"))
        answer = "；".join(_plain_text(x) for x in _as_list(summary.get("answer_framework")) if _plain_text(x))
        add("作答框架", answer)
    if summary.get("keywords") or summary.get("golden_sentences") or summary.get("takeaway_framework"):
        lines.append("今日可带走")
        add("关键词", "、".join(_plain_text(x) for x in _as_list(summary.get("keywords"))))
        gold = []
        for g in _as_list(summary.get("golden_sentences")):
            gold.append(g.get("sentence") if isinstance(g, dict) else _plain_text(g))
        add("必备金句", "；".join(x for x in gold if x))
        add("可迁移框架", summary.get("takeaway_framework"))
    if summary.get("quick_reads"):
        lines.append("今日速读")
        for item in _as_list(summary.get("quick_reads")):
            if isinstance(item, dict):
                lines.append(f"- {item.get('title','')}（{item.get('source','')}）：{item.get('exam_value') or item.get('one_sentence') or ''}")
    return [x for x in lines if _plain_text(x)]


def build_weekly_pdf_compilation(payloads: list[dict[str, Any]], misses: list[dict[str, str]], pdf_path: Path, start_date: str, end_date: str) -> None:
    """Generate a polished daily-email compilation PDF.

    Current product stage: daily modules are still changing. Therefore this PDF
    preserves each day's sent email content, but applies PDF-specific cleanup:
    - remove repeated feedback footers and technical placeholders;
    - render module/submodule headings with colored bands;
    - compact framework-number lines into 01｜标题：内容;
    - hide page number on the cover page.
    """
    try:
        import re
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether
    except Exception as exc:
        raise RuntimeError("缺少 reportlab 依赖，无法生成 PDF。请在 requirements.txt 或 FC 依赖层加入 reportlab。") from exc

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#153B73")
    blue = colors.HexColor("#165DFF")
    blue2 = colors.HexColor("#2563EB")
    gray = colors.HexColor("#475569")
    dark = colors.HexColor("#0F172A")
    pale = colors.HexColor("#F8FAFC")
    line = colors.HexColor("#DDE7F2")
    light_blue = colors.HexColor("#EFF6FF")
    soft_yellow = colors.HexColor("#FFF7ED")
    soft_green = colors.HexColor("#ECFDF5")

    base = ParagraphStyle("CN", parent=styles["Normal"], fontName="STSong-Light", fontSize=10.5, leading=17.2, textColor=dark, spaceAfter=3)
    small = ParagraphStyle("Small", parent=base, fontSize=9.2, leading=14.2, textColor=gray, spaceAfter=2)
    h_cover = ParagraphStyle("Cover", parent=base, fontSize=27, leading=35, alignment=1, textColor=colors.white, spaceAfter=8)
    cover_sub = ParagraphStyle("CoverSub", parent=base, fontSize=12, leading=18.5, alignment=1, textColor=colors.white)
    h1 = ParagraphStyle("H1", parent=base, fontSize=18, leading=25.5, textColor=navy, spaceBefore=5, spaceAfter=8)
    h2_text = ParagraphStyle("H2Text", parent=base, fontSize=13.2, leading=18.5, textColor=colors.white, spaceAfter=0)
    h3_text = ParagraphStyle("H3Text", parent=base, fontSize=11.3, leading=15.8, textColor=blue2, spaceAfter=0)
    h3 = ParagraphStyle("H3", parent=base, fontSize=12.0, leading=17.2, textColor=navy, spaceBefore=4, spaceAfter=3)
    quote = ParagraphStyle("Quote", parent=base, fontSize=10.2, leading=16.6, textColor=dark, backColor=colors.HexColor("#F7FAFC"), leftIndent=4, rightIndent=4, spaceBefore=2, spaceAfter=4)
    compact = ParagraphStyle("Compact", parent=base, fontSize=10.1, leading=16.2, textColor=dark, spaceAfter=2)
    link_style = ParagraphStyle("Link", parent=base, fontSize=9.0, leading=13.2, textColor=gray, spaceAfter=2)
    chip_text = ParagraphStyle("ChipText", parent=base, fontSize=8.8, leading=11.2, textColor=blue2, spaceAfter=0, alignment=1)
    section_hint = ParagraphStyle("SectionHint", parent=small, fontSize=8.6, leading=12.2, textColor=gray, spaceAfter=2)
    gold_title = ParagraphStyle("GoldTitle", parent=base, fontSize=10.0, leading=15.2, textColor=colors.HexColor("#7C2D12"), spaceAfter=2)

    main_headings = {
        "DAILY BRIEFING 每日晨读", "每日晨读", "今日 3 件事", "今日3件事",
        "今日精读", "今日精读｜面试表达与申论素材储备", "文章框架图", "文章框架图｜一眼看懂文章怎么展开",
        "文章框架图｜先看懂文章怎么展开", "今日一题", "今日一题｜考场转化训练", "每日一题",
        "今日可带走", "今日可带走｜必备金句 + 可迁移框架", "今日可带走｜3句表达 + 1个框架",
        "今日可带走｜1个常识 + 2句必备金句 + 1个框架", "今日速读", "今日速读｜申论素材补充", "速读补充",
    }
    sub_headings = {
        "今日主题", "核心判断", "今日一题", "原文速览", "核心观点", "考试转化", "考场怎么用",
        "公基常识必记", "题目", "题型", "审题关键", "答题框架", "作答框架", "参考框架",
        "30秒输出", "30秒表达", "一句话可带走", "今日关键词", "关键词", "高频常识点", "时政常识",
        "金句摘记", "必备金句", "可迁移框架", "拓展联想", "记住3个点", "换成考场话",
        "可用表达", "可直接改写的表达", "如果点原文，重点看", "真正有用的 3-4 个点", "真正有用的3-4个点",
        "整体考试价值", "可迁移考点", "一句话看懂", "点击阅读原文", "来源", "精读文章",
    }

    def esc(s: Any) -> str:
        value = _plain_text(s)
        parts: list[str] = []
        pos2 = 0
        banned_terms = {"重点词", "易考词", "关键词", "重点", "易错点", "易考点"}
        for match in re.finditer(r"【([^】]{1,18})】", value):
            parts.append(html.escape(value[pos2:match.start()]))
            raw_term = match.group(1).strip()
            if raw_term not in banned_terms:
                term = html.escape(raw_term)
                parts.append(f'<font color="#165dff"><b>{term}</b></font>')
            pos2 = match.end()
        parts.append(html.escape(value[pos2:]))
        return "".join(parts)


    def para(text: Any, style: ParagraphStyle = base) -> Paragraph:
        return Paragraph(esc(text), style)

    def boxed(rows: list[list[Any]], widths: list[float] | None = None, bg=colors.white):
        tbl = Table(rows, colWidths=widths, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 0.6, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return tbl

    def heading_band(text: str, level: int = 2):
        if level == 2:
            bg = navy
            style = h2_text
            pad_top, pad_bottom = 5, 5
        else:
            bg = light_blue
            style = h3_text
            pad_top, pad_bottom = 4, 4
        tbl = Table([[Paragraph(esc(text), style)]], colWidths=[160 * mm], hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 0.4, bg),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), pad_top),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad_bottom),
        ]))
        return tbl

    def keyword_chip_row(items: list[Any]):
        chips = [x for x in (_plain_text(i) for i in _as_list(items)) if x][:6]
        if not chips:
            return None
        row = []
        for item in chips:
            cell = Table([[Paragraph(esc(item), chip_text)]], colWidths=[None], hAlign="LEFT")
            cell.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF4FF")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6E4FF")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            row.append(cell)
        tbl = Table([row], hAlign="LEFT")
        tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        return tbl

    def golden_sentence_cards(items: list[Any]):
        cards = []
        for item in _as_list(items)[:2]:
            if isinstance(item, dict):
                sentence = _plain_text(item.get("sentence"))
                scenario = _plain_text(item.get("scenario"))
            else:
                sentence = _plain_text(item)
                scenario = ""
            if not sentence:
                continue
            rows = [[Paragraph("必备金句", gold_title)], [Paragraph(esc(sentence), quote)]]
            if scenario:
                rows.append([Paragraph(f"适用场景：{esc(scenario)}", small)])
            cards.append(boxed(rows, widths=[160*mm], bg=soft_yellow))
        return cards

    def framework_emphasis_block(text: Any):
        t = _plain_text(text)
        if not t:
            return None
        rows = [
            [Paragraph("可迁移框架", h3_text)],
            [Paragraph(esc(t), compact)],
            [Paragraph("建议把它当成申论分析框架或答题顺序来记。", section_hint)],
        ]
        return boxed(rows, widths=[160*mm], bg=soft_green)

    def is_heading_line(text: str) -> int:
        t = text.strip().strip("：:")
        if not t:
            return 0
        if t in main_headings:
            return 2
        if t in sub_headings:
            return 3
        # Headings with dynamic suffixes, e.g. 今日精读｜xxx.
        if any(t.startswith(x) for x in ["今日精读｜", "今日一题｜", "今日可带走｜", "今日速读｜", "文章框架图｜"]):
            return 2
        if any(t.startswith(x) for x in ["考场怎么用", "可直接改写", "如果点原文", "记住", "换成考场", "可用表达", "审题关键", "破题提示", "作答框架", "答题框架"]):
            return 3
        if len(t) <= 14 and any(w in t for w in ["主题", "判断", "精读", "框架", "题目", "金句", "关键词", "常识", "表达", "考场", "速读"]):
            return 3
        return 0

    def normalize_daily_lines(lines: list[str]) -> list[str]:
        """Clean, de-duplicate and compact framework-number sequences."""
        cleaned: list[str] = []
        for raw in lines:
            line = _clean_pdf_line(raw)
            if not line:
                if cleaned and cleaned[-1] != "":
                    cleaned.append("")
                continue
            # Avoid raw markdown/HTML leftovers and duplicated metadata.
            line = line.replace("｜一眼看懂文章怎么展开", "｜一眼看懂文章怎么展开")
            if line.startswith("点击阅读原文 "):
                continue
            if line == "点击阅读原文":
                continue
            if line == "查看原文":
                continue
            if line.startswith(("原文链接", "链接：", "备用搜索：", "如打不开", "http")):
                continue
            if not cleaned or cleaned[-1] != line:
                cleaned.append(line)
        while cleaned and cleaned[-1] == "":
            cleaned.pop()

        out: list[str] = []
        i = 0
        while i < len(cleaned):
            line = cleaned[i]
            if re.fullmatch(r"[1-9]\d?", line.strip()) and i + 1 < len(cleaned):
                num = int(line.strip())
                label = cleaned[i + 1].strip()
                content = ""
                consume = 2
                if i + 2 < len(cleaned):
                    nxt = cleaned[i + 2].strip()
                    if nxt and not re.fullmatch(r"[1-9]\d?", nxt) and is_heading_line(nxt) == 0 and not nxt.startswith("http") and len(nxt) >= 10:
                        content = nxt
                        consume = 3
                if label and is_heading_line(label) == 0:
                    compact_line = f"{num:02d}｜{label}"
                    if content:
                        compact_line += f"：{content}"
                    out.append(compact_line)
                    i += consume
                    continue
            out.append(line)
            i += 1
        return out

    summaries = [daily_summary(p) for p in payloads]
    story: list[Any] = []

    # Cover - no footer/page number on this page.
    story.append(Spacer(1, 28 * mm))
    cover = Table([
        [Paragraph("公考晨读", cover_sub)],
        [Paragraph("本周复盘资料包", h_cover)],
        [Paragraph(f"{esc(start_date)} 至 {esc(end_date)}", cover_sub)],
        [Paragraph("按天收录每日晨读主要内容，便于周末集中复盘和打印归档", cover_sub)],
    ], colWidths=[160 * mm])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), navy),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(cover)
    story.append(Spacer(1, 9 * mm))
    note = "说明：当前版本优先做周末复盘整理，不新增每日精读内容；后续可继续升级为专题/月刊式资料包。"
    story.append(boxed([[para(note, quote)]], widths=[160*mm], bg=pale))
    story.append(PageBreak())

    # TOC
    story.append(Paragraph("01 本周目录", h1))
    toc_rows = [[para("日期", h3), para("主题", h3), para("精读文章", h3)]]
    for s in summaries:
        toc_rows.append([
            para(s.get("date"), small),
            para(s.get("theme") or "-", base),
            para(f"{s.get('featured_title') or '-'}（{s.get('featured_source') or '-'}）", small),
        ])
    story.append(boxed(toc_rows, widths=[28*mm, 50*mm, 81*mm]))
    if misses:
        story.append(Spacer(1, 6))
        missing_dates = "、".join(str(m.get("date")) for m in misses[:10] if m.get("date"))
        miss_text = f"本周部分日期暂无正式晨读归档：{missing_dates}。本汇编仅收录已归档内容。" if missing_dates else "本周部分日期暂无正式晨读归档。"
        story.append(boxed([[para("归档说明", h3), para(miss_text, small)]], widths=[32*mm, 127*mm], bg=pale))
    story.append(PageBreak())

    # Daily complete compilation
    story.append(Paragraph("02 每日晨读汇编", h1))
    for idx, payload in enumerate(payloads, start=1):
        s = daily_summary(payload)
        title_line = f"DAY {idx:02d}｜{s.get('date')}｜{s.get('theme') or s.get('subject') or '每日晨读'}"
        story.append(KeepTogether([
            Paragraph(title_line, h1),
            boxed([[para(f"精读文章：{s.get('featured_title') or '-'}（{s.get('featured_source') or '-'}）", base)]], widths=[160*mm], bg=light_blue),
            Spacer(1, 5),
        ]))

        # Structured weekly highlights: keyword tags + golden sentence cards + framework emphasis block.
        if s.get("keywords") or s.get("golden_sentences") or s.get("takeaway_framework"):
            story.append(heading_band("本页重点提要", level=3))
            chip_tbl = keyword_chip_row(s.get("keywords") or [])
            if chip_tbl is not None:
                story.append(chip_tbl)
                story.append(Spacer(1, 3))
            for card_item in golden_sentence_cards(s.get("golden_sentences") or []):
                story.append(card_item)
                story.append(Spacer(1, 3))
            framework_block = framework_emphasis_block(s.get("takeaway_framework"))
            if framework_block is not None:
                story.append(framework_block)
                story.append(Spacer(1, 5))

        lines = _html_to_plain_lines(payload.get("_archived_html") or "")
        if not lines:
            lines = _structured_daily_lines(s)
        cleaned: list[str] = []
        for line_text in lines:
            if not line_text:
                cleaned.append("")
                continue
            if line_text in {s.get("subject"), s.get("featured_title"), s.get("theme")}:
                continue
            cleaned.append(line_text)
        cleaned = normalize_daily_lines(cleaned)

        for line_text in cleaned:
            if not line_text:
                story.append(Spacer(1, 3))
                continue
            stripped = line_text.strip().strip("：:")
            level = is_heading_line(stripped)
            if level == 2:
                story.append(Spacer(1, 4))
                story.append(heading_band(stripped, level=2))
            elif level == 3:
                story.append(Spacer(1, 2))
                story.append(heading_band(stripped, level=3))
            elif stripped.startswith("原文链接：") or stripped.startswith("http") or stripped.startswith("如打不开"):
                continue
            elif re.match(r"^\d{2}｜", stripped):
                story.append(boxed([[para(stripped, compact)]], widths=[160*mm], bg=soft_green))
            elif stripped.startswith(("【", "[")) and len(stripped) <= 28:
                story.append(boxed([[para(stripped, h3_text)]], widths=[160*mm], bg=soft_yellow))
            elif stripped.startswith(("- ", "1. ", "2. ", "3. ", "4. ", "5. ")):
                story.append(Paragraph(esc(stripped), compact))
            else:
                story.append(Paragraph(esc(stripped), base))
        if idx != len(payloads):
            story.append(PageBreak())

    def add_page_number(canvas, doc):
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setFont("STSong-Light", 8)
        canvas.setFillColor(gray)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"公考晨读本周复盘资料包 - {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
        title=f"公考晨读本周复盘资料包｜{start_date}至{end_date}",
    )
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)

def build_weekly_assets(event: Any | None = None) -> dict[str, Any]:
    """生成周汇总 Markdown/HTML/PDF，并上传 OSS；不发送邮件。

    用于两种场景：
    1) weekly_pdf 独立模式：生成后再单独发送周报邮件；
    2) daily 晨读模式：周末生成后作为附件挂到当天晨读邮件。
    """
    payload = event if isinstance(event, dict) else {}
    end_text = str(payload.get("end_date") or "").strip()
    days = int(payload.get("days") or settings.weekly_pdf_days)
    end_date = dt.datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else dt.datetime.now(TZ).date()
    date_list = _date_range(end_date, days)
    start_date, end_date_text = date_list[0], date_list[-1]

    archives, misses = load_daily_archives(end_date=end_date, days=days)
    if not archives:
        raise RuntimeError(f"没有读取到任何日归档，无法生成周 PDF。检查 OSS daily 目录：{settings.daily_archive_prefix}")

    title = f"公考晨读本周复盘资料包｜{start_date} 至 {end_date_text}"
    md = build_weekly_markdown(archives, start_date, end_date_text, misses)
    html_body = build_weekly_html(archives, start_date, end_date_text, misses)

    out_dir = settings.output_dir / "weekly"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"gongkao-weekly-{start_date}_to_{end_date_text}"
    md_path = out_dir / f"{base_name}.md"
    html_path = out_dir / f"{base_name}.html"
    pdf_path = out_dir / f"{base_name}.pdf"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html_body, encoding="utf-8")
    # Weekly PDF generation has one production path: the V1 review packet
    # implemented in weekly_typst_export.py.
    from weekly_typst_export import build_data, build_typst_weekly_pdf, build_typst_weekly_preview_pdf

    pdf_engine = "typst"
    shared_weekly_data = build_data(archives, start_date, end_date_text, misses)
    typst_meta: dict[str, Any] | None = build_typst_weekly_pdf(
        archives,
        misses,
        pdf_path,
        start_date,
        end_date_text,
        data=shared_weekly_data,
    )
    preview_pdf_path = out_dir / f"{base_name}-lite-preview.pdf"
    preview_meta: dict[str, Any] | None = None
    preview_error = ""
    try:
        preview_meta = build_typst_weekly_preview_pdf(
            archives,
            misses,
            preview_pdf_path,
            start_date,
            end_date_text,
            data=shared_weekly_data,
        )
    except Exception as exc:
        preview_error = f"{type(exc).__name__}: {exc}"

    upload_meta: dict[str, Any] = {}
    if settings.history_storage == "oss":
        prefix = settings.weekly_pdf_prefix.strip().strip("/")
        upload_meta["pdf"] = put_oss_object(f"{prefix}/{pdf_path.name}", pdf_path.read_bytes(), "application/pdf")
        upload_meta["md"] = put_oss_object(f"{prefix}/{md_path.name}", md_path.read_bytes(), "text/markdown; charset=utf-8")
        upload_meta["html"] = put_oss_object(f"{prefix}/{html_path.name}", html_path.read_bytes(), "text/html; charset=utf-8")
        if preview_meta and preview_pdf_path.exists():
            upload_meta["lite_preview_pdf"] = put_oss_object(f"{prefix}/{preview_pdf_path.name}", preview_pdf_path.read_bytes(), "application/pdf")

    attachment = {
        "filename": f"公考晨读本周复盘资料包_{start_date}_至_{end_date_text}.pdf",
        "content": pdf_path.read_bytes(),
        "content_type": "application/pdf",
    }
    lite_preview_attachment = None
    if preview_meta and preview_pdf_path.exists():
        lite_preview_attachment = {
            "filename": f"公考晨读周复盘预览版_{start_date}_至_{end_date_text}.pdf",
            "content": preview_pdf_path.read_bytes(),
            "content_type": "application/pdf",
        }
    return {
        "status": "ok",
        "mode": "weekly_pdf_assets",
        "start_date": start_date,
        "end_date": end_date_text,
        "days_requested": days,
        "archives_loaded": len(archives),
        "misses": misses,
        "local_pdf": str(pdf_path),
        "pdf_engine": pdf_engine,
        "typst_meta": typst_meta,
        "local_md": str(md_path),
        "local_html": str(html_path),
        "markdown": md,
        "html": html_body,
        "attachment": attachment,
        "lite_preview": {
            "status": "ok" if lite_preview_attachment else "failed",
            "local_pdf": str(preview_pdf_path) if lite_preview_attachment else "",
            "attachment": lite_preview_attachment,
            "oss_pdf_path": ((upload_meta.get("lite_preview_pdf") or {}).get("oss_path") if lite_preview_attachment else ""),
            "attachment_filename": (lite_preview_attachment or {}).get("filename") if lite_preview_attachment else "",
            "pdf_engine": "typst" if lite_preview_attachment else "",
            "typst_meta": preview_meta,
            "error": preview_error,
        },
        "oss_upload": upload_meta,
    }


def run_weekly_pdf(event: Any | None = None, test_mode: bool = False) -> dict[str, Any]:
    assets = build_weekly_assets(event)
    start_date, end_date_text = assets["start_date"], assets["end_date"]
    send_result: dict[str, Any] | None = None
    if settings.send_email and settings.weekly_pdf_send_email:
        attachments = [assets["attachment"]] if settings.weekly_pdf_attach else []
        send_result = send_email(
            f"{settings.subject_prefix}本周复盘资料包｜{start_date}至{end_date_text}",
            assets["markdown"],
            assets["html"],
            test_mode=test_mode,
            attachments=attachments,
        )

    return {
        "status": "ok",
        "mode": "weekly_pdf",
        "test_mode": test_mode,
        "start_date": start_date,
        "end_date": end_date_text,
        "days_requested": assets["days_requested"],
        "archives_loaded": assets["archives_loaded"],
        "misses": assets["misses"],
        "local_pdf": assets["local_pdf"],
        "local_md": assets["local_md"],
        "local_html": assets["local_html"],
        "oss_upload": assets["oss_upload"],
        "send_result": send_result,
    }
