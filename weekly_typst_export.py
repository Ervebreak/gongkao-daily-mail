from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import weekly_report as weekly
from weekly_material_curator import build_weekly_enrichment


def find_typst_binary() -> str | None:
    for candidate in [
        shutil.which("typst"),
        "/opt/bin/typst",
        str(Path(__file__).resolve().parent / "bin" / "typst"),
    ]:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def clean(value: Any) -> str:
    return weekly._clean(value)


def as_list(value: Any) -> list[Any]:
    return weekly._as_list(value)


def typst_text(value: Any) -> str:
    text = clean(value)
    return (
        text.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("#", "\\#")
        .replace("$", "\\$")
        .replace("_", "\\_")
    )


def fmt_date(value: str) -> str:
    value = clean(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value.replace("-", ".")
    return value


def short_date(value: str) -> str:
    value = clean(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value[5:].replace("-", ".")
    return value


def weekday_cn(value: str) -> str:
    import datetime as dt

    try:
        day = dt.date.fromisoformat(value)
        return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][day.weekday()]
    except Exception:
        return ""


def first_text(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            text = clean(item.get("sentence") if isinstance(item, dict) else item)
            if text:
                return text
        return ""
    return clean(value)


def normalize_steps(featured: dict[str, Any]) -> list[dict[str, str]]:
    framework_map = featured.get("article_framework_map") if isinstance(featured.get("article_framework_map"), dict) else {}
    raw_steps = framework_map.get("steps") or featured.get("article_framework") or featured.get("structure_breakdown") or []
    steps: list[dict[str, str]] = []
    for raw in as_list(raw_steps):
        if isinstance(raw, dict):
            label = clean(raw.get("label") or raw.get("title"))
            content = clean(raw.get("content") or raw.get("text") or raw.get("summary"))
        else:
            text = clean(raw)
            label, content = "", text
            for mark in ["：", ":"]:
                if mark in text:
                    left, right = text.split(mark, 1)
                    if len(left) <= 18:
                        label, content = left, right
                    break
        if label or content:
            steps.append({"label": label, "content": content})
    return steps


def normalize_tags(featured: dict[str, Any], question: dict[str, Any], takeaway: dict[str, Any]) -> list[str]:
    framework_map = featured.get("article_framework_map") if isinstance(featured.get("article_framework_map"), dict) else {}
    raw = framework_map.get("exam_tags") or question.get("upper_exam_points") or takeaway.get("keywords") or []
    if isinstance(raw, str):
        raw = re.split(r"\s*/\s*|、|，|,", raw)
    tags: list[str] = []
    for item in as_list(raw):
        text = clean(item)
        if text and text not in tags:
            tags.append(text)
    return tags


def normalize_day(payload: dict[str, Any], index: int) -> dict[str, Any]:
    brief = weekly.brief_from_payload(payload)
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    takeaway = brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}
    date = clean(payload.get("date") or payload.get("delivery_date") or brief.get("date"))
    quick_reads = [item for item in as_list(brief.get("quick_reads")) if isinstance(item, dict)]
    framework_map = featured.get("article_framework_map") if isinstance(featured.get("article_framework_map"), dict) else {}
    return {
        "day_no": index,
        "date": date,
        "short_date": short_date(date),
        "weekday": weekday_cn(date),
        "theme": clean(brief.get("today_theme") or featured.get("theme") or payload.get("subject")),
        "focus": clean(brief.get("today_focus") or featured.get("one_sentence") or featured.get("core_viewpoint")),
        "featured": {
            "title": clean(featured.get("title")),
            "source": clean(featured.get("source")),
            "published_at": clean(featured.get("published_at")),
            "theme": clean(featured.get("theme") or brief.get("today_theme")),
            "url": clean(featured.get("url")),
            "one_sentence": clean(featured.get("one_sentence") or featured.get("core_viewpoint")),
            "original_reading_focus": clean(featured.get("original_reading_focus")),
            "three_useful_points": [clean(x) for x in as_list(featured.get("three_useful_points")) if clean(x)],
            "exam_use": [clean(x) for x in as_list(featured.get("exam_use") or featured.get("usable_for_exam") or featured.get("exam_conversion")) if clean(x)],
            "rewritable_expression": clean(featured.get("rewritable_expression")),
            "article_type": clean(featured.get("article_type") or framework_map.get("article_type") or framework_map.get("type")),
            "main_thread": clean(featured.get("main_thread") or framework_map.get("main_thread")),
        },
        "question": {
            "question_type": clean(question.get("question_type")),
            "question": clean(question.get("question")),
            "exam_focus": clean(question.get("exam_focus")),
            "breaking_hint": clean(question.get("breaking_hint")),
            "answer_framework": [clean(x) for x in as_list(question.get("answer_framework") or question.get("answer_frame")) if clean(x)],
            "candidate_answer": clean(question.get("candidate_answer")),
            "thirty_second_answer": clean(question.get("thirty_second_answer")),
            "output_sentence_template": clean(question.get("output_sentence_template")),
        },
        "takeaway": {
            "keywords": [clean(x) for x in as_list(takeaway.get("keywords")) if clean(x)],
            "common_knowledge_points": [clean(x) for x in as_list(takeaway.get("common_knowledge_points")) if clean(x)],
            "golden_sentences": [
                row
                for row in (
                    {
                        "sentence": clean(item.get("sentence") or item.get("text")) if isinstance(item, dict) else clean(item),
                        "scenario": clean(item.get("scenario")) if isinstance(item, dict) else "",
                    }
                    for item in as_list(takeaway.get("golden_sentences"))
                )
                if row["sentence"]
            ],
            "framework": clean(takeaway.get("framework")),
        },
        "steps": normalize_steps(featured),
        "tags": normalize_tags(featured, question, takeaway),
        "quick_reads": quick_reads,
    }


def build_data(payloads: list[dict[str, Any]], start_date: str, end_date: str, misses: list[dict[str, str]]) -> dict[str, Any]:
    days = [normalize_day(payload, idx) for idx, payload in enumerate(payloads, start=1)]
    keyword_counter: Counter[str] = Counter()
    expression_rows: list[dict[str, str]] = []
    framework_rows: list[dict[str, str]] = []
    quick_count = 0
    warnings: list[str] = []
    seen_dates: set[str] = set()
    for day in days:
        if day["date"] in seen_dates:
            warnings.append(f"duplicate delivery_date: {day['date']}")
        seen_dates.add(day["date"])
        if not day["featured"]["title"]:
            warnings.append(f"{day['date']} missing featured_article.title")
        if not day["question"]["question"]:
            warnings.append(f"{day['date']} missing daily_question.question")
        if not day["question"]["candidate_answer"]:
            warnings.append(f"{day['date']} missing daily_question.candidate_answer")
        for key in day["tags"] + day["takeaway"]["keywords"]:
            if key and len(key) <= 20:
                keyword_counter[key] += 1
        for item in day["takeaway"]["golden_sentences"]:
            if item["sentence"]:
                expression_rows.append(
                    {
                        "date": day["short_date"],
                        "theme": day["theme"],
                        "sentence": item["sentence"],
                        "scenario": item["scenario"],
                    }
                )
        if day["takeaway"]["framework"]:
            framework_rows.append({"date": day["short_date"], "theme": day["theme"], "framework": day["takeaway"]["framework"]})
        quick_count += len(day["quick_reads"])
    map_cards = [
        ("数字治理与公共服务", "规则前置、算法治理、适老兜底；适用于数字政务、平台监管、科技向善类题。"),
        ("执法规范与营商环境", "跨部门协同、扫码留痕、分类监管；适用于政策打架、涉企检查、服务型执法。"),
        ("新业态纠纷与多元调解", "第三方专业评议、专家库、部门联动；适用于专业壁垒纠纷和新业态监管服务。"),
        ("生态治理与权责边界", "政府主导、财政兜底、政企分离；适用于公共服务定价、生态治理、公益商业边界。"),
        ("市场秩序与消费公平", "平台责任、算法问责、下沉维权；适用于新型市场监管和消费者权益保护。"),
    ]
    try:
        enrichment = build_weekly_enrichment(days)
    except Exception as exc:
        enrichment = {
            "exam_map_cards": [],
            "selected_expression_rows": [],
            "material_cards": [],
            "practice_questions": [],
            "warnings": [f"weekly enrichment failed open: {type(exc).__name__}: {exc}"],
        }
    warnings.extend(enrichment.get("warnings") or [])
    return {
        "start_date": start_date,
        "end_date": end_date,
        "period": f"{fmt_date(start_date)} - {fmt_date(end_date)}",
        "days": days,
        "misses": misses,
        "warnings": warnings,
        "stats": {
            "featured_count": len(days),
            "questions_count": sum(1 for day in days if day["question"]["question"]),
            "golden_count": len(expression_rows),
            "quick_count": quick_count,
        },
        "hot_keywords": [key for key, _count in keyword_counter.most_common(10)],
        "map_cards": map_cards,
        "expression_rows": expression_rows,
        "framework_rows": framework_rows,
        "exam_map_cards": enrichment.get("exam_map_cards") or [],
        "selected_expression_rows": enrichment.get("selected_expression_rows") or [],
        "material_cards": enrichment.get("material_cards") or [],
        "practice_questions": enrichment.get("practice_questions") or [],
    }


def t_list(items: list[Any], limit: int = 6) -> str:
    rows = [f"- {typst_text(item)}" for item in items[:limit] if clean(item)]
    return "\n".join(rows) if rows else "- 暂无可抽取内容"


def t_badges(items: list[str], limit: int = 8) -> str:
    rows = [f'#badge[{typst_text(item)}]' for item in items[:limit] if clean(item)]
    return " ".join(rows) if rows else ""


def table_cell(value: Any) -> str:
    return f"[{typst_text(value)}]"


def render_typst(data: dict[str, Any]) -> str:
    days = data["days"]
    stats = data["stats"]
    overview_rows = "\n".join(
        ", ".join(
            [
                table_cell(f'{day["short_date"]}\n{day["weekday"]}'),
                table_cell(f'{day["theme"]}\n{day["focus"]}'),
                table_cell(f'{day["featured"]["title"]}\n{day["featured"]["source"]}｜{day["featured"]["published_at"]}'),
                table_cell(f'{day["question"]["question_type"]}\n{" / ".join(day["tags"][:3])}'),
            ]
        )
        + ","
        for day in days
    )
    if data.get("exam_map_cards"):
        map_cards = "][\n".join(
            f'#map-card[{typst_text(card.get("title"))}][{typst_text(card.get("summary") or card.get("body") or card.get("description"))}'
            f'#linebreak()#muted[{typst_text(card.get("use_for") or card.get("use_tip"))}]'
            f'#v(3pt){t_badges(card.get("keywords") or card.get("target_topics") or [], 6)}]'
            for card in data["exam_map_cards"]
            if isinstance(card, dict)
        )
    else:
        map_cards = "][\n".join(f'#map-card[{typst_text(title)}][{typst_text(desc)}]' for title, desc in data["map_cards"])
    daily_sections: list[str] = []
    for day in days:
        featured = day["featured"]
        question = day["question"]
        takeaway = day["takeaway"]
        step_blocks = "\n".join(
            f'#step-item("{idx:02d}")[{typst_text(step["label"])}][{typst_text(step["content"])}]'
            for idx, step in enumerate(day["steps"][:6], start=1)
        )
        answer_framework = t_list(question["answer_framework"], 6)
        golden_blocks = "\n".join(
            f'#quote-card[{typst_text(item["sentence"])}][{typst_text(item["scenario"])}]'
            for item in takeaway["golden_sentences"][:3]
        )
        daily_sections.append(
            f"""
#pagebreak()
#day-title("DAY {day["day_no"]:02d}", "{typst_text(day["short_date"])}｜{typst_text(day["weekday"])}｜{typst_text(day["theme"])}", "{typst_text(day["focus"])}")

#grid(columns: (1fr, 1fr), gutter: 8pt)[
  #mini-panel[核心判断][{typst_text(featured["one_sentence"])}]
][
  #mini-panel[今日题眼][{typst_text(question["exam_focus"])}]
]

#block-title[A. 精读文章复盘]
#article-card[
  #muted[{typst_text(featured["source"])}｜{typst_text(featured["published_at"])}｜{typst_text(featured["theme"])}]
  #v(3pt)
  #text(size: 14pt, weight: "bold")[{typst_text(featured["title"])}]
  #v(5pt)
  #info-strip[一句话看懂][{typst_text(featured["one_sentence"])}]
  #info-strip[原文重点][{typst_text(featured["original_reading_focus"])}]
]

#grid(columns: (1fr, 1fr), gutter: 8pt)[
  #panel[记住 3 个点][{t_list(featured["three_useful_points"], 3)}]
][
  #panel[换成考场话][{t_list(featured["exam_use"], 4)}
  #if "{typst_text(featured["rewritable_expression"])}" != "" [
    #v(4pt)
    #info-strip[可用表达][{typst_text(featured["rewritable_expression"])}]
  ]]
]

#framework-box[
  #text(weight: "bold", fill: brand)[文章框架图]
  #v(3pt)
  #muted[文章类型：{typst_text(featured["article_type"])}｜主线：{typst_text(featured["main_thread"])}]
  #v(4pt)
  {step_blocks if step_blocks else '#muted[暂无框架步骤]'}
  #v(4pt)
  {t_badges(day["tags"], 8)}
]

#block-title[B. 今日一题｜考场转化训练]
#question-card[
  #badge[{typst_text(question["question_type"])}]
  #v(4pt)
  #text(size: 11.5pt, weight: "bold")[{typst_text(question["question"])}]
  #info-strip[审题关键][{typst_text(question["exam_focus"])}]
  #info-strip[破题提示][{typst_text(question["breaking_hint"])}]
  #text(weight: "bold", fill: brand)[作答框架]
  {answer_framework}
  #candidate-answer[{typst_text(question["candidate_answer"])}]
  #answer-box[30 秒表达][{typst_text(question["thirty_second_answer"])}]
  #answer-box[参考开头][{typst_text(question["output_sentence_template"])}]
]

#block-title[C. 今日可带走]
#takeaway-card[
  {t_badges(takeaway["keywords"], 6)}
  #info-strip[时政常识][{typst_text(first_text(takeaway["common_knowledge_points"]))}]
  {golden_blocks if golden_blocks else '#muted[暂无金句]'}
  #info-strip[可迁移框架][{typst_text(takeaway["framework"])}]
]
"""
        )
    expression_source = data.get("selected_expression_rows") or data["expression_rows"]
    expression_parts = []
    for idx, row in enumerate(expression_source, start=1):
        if not isinstance(row, dict):
            continue
        sentence = row.get("sentence") or row.get("expression") or row.get("text")
        date = row.get("date") or "本周"
        theme = row.get("theme") or row.get("exam_point") or row.get("topic") or ""
        scenario = row.get("scenario") or row.get("use_tip") or row.get("usage") or row.get("applicable_exam_point") or ""
        expression_parts.append(
            f'#expr-row("{idx:02d}")[{typst_text(sentence)}][{typst_text(date)}｜{typst_text(theme)}'
            f'{("｜用法：" + typst_text(scenario)) if scenario else ""}]'
        )
    expression_rows = "\n#std.line(length: 100%, stroke: 0.45pt + line)\n".join(expression_parts)
    framework_rows = "\n".join(
        f'#frame-row[{typst_text(row["date"])}｜{typst_text(row["theme"])}][{typst_text(row["framework"])}]'
        for row in data["framework_rows"]
    )
    featured_index_rows = "\n".join(
        ", ".join(
            [
                table_cell(day["short_date"]),
                table_cell(f'{day["featured"]["title"]}\n{day["featured"]["source"]}｜{day["featured"]["published_at"]}\n{day["featured"]["url"]}'),
                table_cell(day["featured"]["theme"]),
                table_cell(day["featured"]["one_sentence"]),
            ]
        )
        + ","
        for day in days
    )
    quick_index_rows: list[str] = []
    for day in days:
        for item in day["quick_reads"]:
            quick_index_rows.append(
                ", ".join(
                    [
                        table_cell(day["short_date"]),
                        table_cell(f'{clean(item.get("title"))}\n{clean(item.get("source"))}｜{clean(item.get("published_at"))}\n{clean(item.get("url"))}'),
                        table_cell(clean(item.get("theme"))),
                        table_cell(clean(item.get("exam_value") or item.get("one_sentence"))),
                    ]
                )
                + ","
            )
    quick_index = "\n".join(quick_index_rows)

    def row_value(row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if isinstance(value, list):
                text = "、".join(clean(item) for item in value if clean(item))
            else:
                text = clean(value)
            if text:
                return text
        return ""

    material_parts: list[str] = []
    for idx, row in enumerate(data.get("material_cards") or [], start=1):
        if not isinstance(row, dict):
            continue
        title = row_value(row, "title", "source_title", "theme") or f"素材卡 {idx:02d}"
        material_type = row_value(row, "material_type", "type")
        source_dates = row_value(row, "source_dates", "date")
        source_articles = row_value(row, "source_articles", "source_title")
        target_topics = row_value(row, "target_topics", "theme")
        core_topic = row_value(row, "core_topic")
        generalizable_logic = row_value(row, "generalizable_logic")
        factual_anchor = row_value(row, "factual_anchor", "anchor")
        exam_paragraph = row_value(row, "exam_paragraph", "exam_value")
        exam_paragraph_specific = row_value(row, "exam_paragraph_specific")
        exam_paragraph_general = row_value(row, "exam_paragraph_general")
        can_use_for = row_value(row, "can_use_for")
        suggested_question_types = row_value(row, "suggested_question_types")
        not_suitable_for = row_value(row, "not_suitable_for")
        memory_sentence = row_value(row, "memory_sentence")
        use_tip = row_value(row, "use_tip")
        use_boundary = row_value(row, "use_boundary")
        material_parts.append(
            f'#material-card[{typst_text(title)}][{typst_text(material_type)}][{typst_text(source_dates)}][{typst_text(source_articles)}]'
            f'[{typst_text(target_topics)}][{typst_text(core_topic)}][{typst_text(generalizable_logic)}]'
            f'[{typst_text(factual_anchor)}][{typst_text(exam_paragraph)}][{typst_text(exam_paragraph_specific)}]'
            f'[{typst_text(exam_paragraph_general)}][{typst_text(can_use_for)}][{typst_text(suggested_question_types)}]'
            f'[{typst_text(not_suitable_for)}][{typst_text(memory_sentence)}][{typst_text(use_tip)}][{typst_text(use_boundary)}]'
        )
    material_cards = "\n#v(7pt)\n".join(material_parts)

    practice_parts: list[str] = []
    for idx, row in enumerate(data.get("practice_questions") or [], start=1):
        if not isinstance(row, dict):
            continue
        title = row_value(row, "title") or f"素材运用题 {idx:02d}"
        question_type = row_value(row, "question_type")
        question = row_value(row, "question")
        target_topics = row_value(row, "target_topics")
        suggested_golden_sentences = row_value(row, "suggested_golden_sentences")
        suggested_case_materials = row_value(row, "suggested_case_materials")
        suggested_policy_expressions = row_value(row, "suggested_policy_expressions")
        answer_hint = row_value(row, "answer_hint", "use_hint")
        mini_reference_answer = row_value(row, "mini_reference_answer")
        use_boundary = row_value(row, "use_boundary")
        if question_type == "对策建议题" and not use_boundary:
            use_boundary = "本题重点是措施表达，不建议硬塞外部案例。"
        practice_parts.append(
            f'#practice-card[{typst_text(title)}][{typst_text(question_type)}][{typst_text(question)}]'
            f'[{typst_text(target_topics)}][{typst_text(suggested_golden_sentences)}]'
            f'[{typst_text(suggested_case_materials)}][{typst_text(suggested_policy_expressions)}]'
            f'[{typst_text(answer_hint)}][{typst_text(mini_reference_answer)}][{typst_text(use_boundary)}]'
        )
    practice_questions = "\n#v(7pt)\n".join(practice_parts)

    return f"""
#set document(title: [公考晨读周复盘资料包 V1.2])
#set page(
  paper: "a4",
  margin: (x: 13mm, y: 17mm),
  numbering: "1",
  header: align(left)[#text(size: 8.5pt, fill: rgb("#64748b"))[公考晨读 · 周复盘资料包 V1]],
  footer: text(size: 8pt, fill: rgb("#94a3b8"))[周日复盘版 · 摘要/框架/表达/素材/题目/索引],
)
#set text(font: ("Microsoft YaHei", "SimSun"), size: 10.2pt, lang: "zh")
#set par(justify: false, leading: 0.72em, spacing: 0.62em)
#set list(spacing: 0.42em)
#set enum(spacing: 0.42em)

#let brand = rgb("#0f3b68")
#let blue = rgb("#185a9d")
#let pale = rgb("#f3f7fc")
#let line = rgb("#d7e2ef")
#let day-surface = rgb("#eef4fb")
#let day-badge-fill = rgb("#dbeafe")
#let print-panel = rgb("#f8fbff")
#let cover-surface = rgb("#eef4fb")
#let cover-card = rgb("#f8fbff")
#let table-head = rgb("#eef4fb")
#let num-fill = rgb("#e9f3ff")
#let muted-color = rgb("#64748b")

#let muted(body) = text(size: 8.6pt, fill: muted-color)[#body]
#let badge(body) = box(fill: rgb("#e9f3ff"), stroke: 0.5pt + rgb("#cfe3fb"), inset: (x: 5pt, y: 2pt), radius: 7pt)[#text(size: 8pt, fill: blue, weight: "bold")[#body]]
#let block-title(body) = [#v(11pt)#box(stroke: (left: 3pt + blue), inset: (left: 7pt))[#text(size: 13pt, fill: brand, weight: "bold")[#body]]#v(6pt)]
#let info-strip(label, body) = block(fill: print-panel, stroke: 0.45pt + line, inset: 7pt, radius: 4.5pt, width: 100%, breakable: true)[#text(weight: "bold", fill: brand)[#label：] #body]
#let panel(title, body) = block(fill: print-panel, stroke: 0.55pt + line, inset: 9pt, radius: 6.5pt, width: 100%, breakable: false)[#text(weight: "bold", fill: brand)[#title]#v(5pt)#body]
#let mini-panel(title, body) = box(fill: rgb("#f8fafc"), stroke: 0.55pt + line, inset: 9pt, radius: 6.5pt, width: 100%)[#text(weight: "bold", fill: brand)[#title]#v(4pt)#body]
#let article-card(body) = block(fill: white, stroke: 0.6pt + line, inset: 10pt, radius: 7.5pt, width: 100%, breakable: false)[#body]
#let framework-box(body) = block(fill: white, stroke: 0.6pt + line, inset: 10pt, radius: 7.5pt, width: 100%, breakable: false)[#body]
#let question-card(body) = block(fill: rgb("#fbfcff"), stroke: 0.6pt + line, inset: 10pt, radius: 7.5pt, width: 100%, breakable: true)[#body]
#let takeaway-card(body) = block(fill: white, stroke: 0.6pt + line, inset: 10pt, radius: 7.5pt, width: 100%, breakable: false)[#body]
#let candidate-answer(body) = block(fill: white, stroke: (left: 3pt + brand, rest: 0.55pt + line), inset: 9pt, radius: 5.5pt, width: 100%, breakable: true)[#text(weight: "bold", fill: brand)[考生版参考答案]#v(5pt)#body]
#let answer-box(label, body) = block(fill: rgb("#fff8e8"), stroke: 0.55pt + rgb("#f0d9aa"), inset: 8pt, radius: 5.5pt, width: 100%, breakable: true)[#text(weight: "bold", fill: brand)[#label：] #body]
#let quote-card(sentence, scenario) = block(fill: rgb("#f8fafc"), stroke: (left: 3pt + blue, rest: 0pt), inset: 8pt, radius: 5.5pt, width: 100%, breakable: true)[#text(weight: "bold")[#sentence]#if scenario != "" [#linebreak()#muted[适用：#scenario]]]
#let step-item(no, label, body) = grid(columns: (24pt, 1fr), gutter: 7pt, box(fill: num-fill, stroke: 0.5pt + rgb("#cfe3fb"), inset: (x: 4.5pt, y: 2.5pt), radius: 10pt)[#text(size: 8pt, fill: blue, weight: "bold")[#no]], [#if label != "" [#text(weight: "bold", fill: brand)[#label]#linebreak()]#body])
#let map-card(title, body) = box(fill: white, stroke: (left: 3pt + blue, rest: 0.55pt + line), inset: 8pt, radius: 6pt, width: 100%)[#text(size: 11pt, weight: "bold", fill: brand)[#title]#v(3pt)#body]
#let day-title(no, title, focus) = box(fill: day-surface, stroke: 0.65pt + line, inset: 12pt, radius: 8pt, width: 100%)[#grid(columns: (48pt, 1fr), gutter: 9pt)[#box(fill: day-badge-fill, inset: 8pt, radius: 7pt)[#text(fill: brand, weight: "bold")[#no]]][#text(fill: brand, size: 14.8pt, weight: "bold")[#title]#linebreak()#text(fill: muted-color, size: 9.6pt)[#focus]]]
#let expr-row(no, sentence, meta) = grid(columns: (28pt, 1fr), gutter: 9pt, box(fill: num-fill, stroke: 0.5pt + rgb("#cfe3fb"), inset: 6pt, radius: 5pt)[#text(fill: blue, weight: "bold", size: 8.5pt)[#no]], [#text(weight: "bold")[#sentence]#linebreak()#muted[#meta]])
#let frame-row(title, body) = box(fill: rgb("#f8fbff"), stroke: 0.55pt + line, inset: 9pt, radius: 6.5pt, width: 100%)[#text(weight: "bold", fill: brand)[#title]#v(4pt)#body]
#let quote-bank(body) = block(fill: white, stroke: 0.6pt + line, inset: 10pt, radius: 7.5pt, width: 100%, breakable: true)[#body]
#let material-card(title, material-type, source-dates, source-articles, target-topics, core-topic, generalizable-logic, factual-anchor, exam-paragraph, exam-paragraph-specific, exam-paragraph-general, can-use-for, suggested-question-types, not-suitable-for, memory-sentence, use-tip, use-boundary) = block(fill: white, stroke: 0.6pt + line, inset: 10pt, radius: 7.5pt, width: 100%, breakable: true)[
  #text(size: 12pt, weight: "bold", fill: brand)[#title]
  #if material-type != "" [#linebreak()#badge[#material-type]]
  #v(5pt)
  #if source-dates != "" or source-articles != "" [#info-strip[来源][#source-dates#if source-dates != "" and source-articles != "" [｜]#source-articles]]
  #if target-topics != "" [#info-strip[适用考点][#target-topics]]
  #if core-topic != "" [#info-strip[可迁移母题][#core-topic]]
  #if generalizable-logic != "" [#info-strip[通用治理逻辑][#generalizable-logic]]
  #if factual-anchor != "" [#info-strip[事实锚点][#factual-anchor]]
  #if exam-paragraph-specific != "" [#info-strip[具体事实写法][#exam-paragraph-specific]]
  #if exam-paragraph-general != "" [#info-strip[通用考场写法][#exam-paragraph-general]]
  #if exam-paragraph-specific == "" and exam-paragraph-general == "" and exam-paragraph != "" [#info-strip[考场表达][#exam-paragraph]]
  #if can-use-for != "" [#info-strip[可用于][#can-use-for]]
  #if suggested-question-types != "" [#info-strip[适用题型][#suggested-question-types]]
  #if not-suitable-for != "" [#info-strip[不适合][#not-suitable-for]]
  #if memory-sentence != "" [#answer-box[记忆句][#memory-sentence]]
  #if use-tip != "" [#info-strip[用法提示][#use-tip]]
  #if use-boundary != "" [#muted[使用边界：#use-boundary]]
]
#let practice-card(title, question-type, question, target-topics, suggested-golden-sentences, suggested-case-materials, suggested-policy-expressions, answer-hint, mini-reference-answer, use-boundary) = block(fill: white, stroke: 0.6pt + line, inset: 10pt, radius: 7.5pt, width: 100%, breakable: true)[
  #text(size: 12pt, weight: "bold", fill: brand)[#title]
  #if question-type != "" [#linebreak()#badge[#question-type]]
  #v(5pt)
  #if question != "" [#text(weight: "bold")[#question]]
  #if target-topics != "" [#info-strip[训练主题][#target-topics]]
  #if suggested-golden-sentences != "" [#info-strip[建议金句][#suggested-golden-sentences]]
  #if suggested-case-materials != "" [#info-strip[建议素材][#suggested-case-materials]]
  #if suggested-policy-expressions != "" [#info-strip[政策表达][#suggested-policy-expressions]]
  #if answer-hint != "" [#info-strip[作答提示][#answer-hint]]
  #if mini-reference-answer != "" [#candidate-answer[#mini-reference-answer]]
  #if use-boundary != "" [#muted[使用边界：#use-boundary]]
]

#set page(numbering: none, header: none, footer: none)
#box(fill: cover-surface, stroke: 0.8pt + line, inset: 24pt, radius: 12pt, width: 100%, height: 135mm)[
  #text(fill: blue, size: 9.5pt, weight: "bold")[WEEKLY REVIEW · 公考晨读周复盘资料包]
  #v(18pt)
  #text(fill: brand, size: 32pt, weight: "bold")[公考晨读]
  #linebreak()
  #text(fill: blue, size: 26pt, weight: "bold")[周复盘资料包 V1.2]
  #v(10pt)
  #text(fill: brand, size: 12pt)[{typst_text(data["period"])}｜周日复盘版｜不新增精读文章]
  #v(24pt)
  #grid(columns: (1fr, 1fr, 1fr, 1fr), gutter: 8pt)[
    #box(fill: cover-card, stroke: 0.6pt + line, inset: 8pt, radius: 10pt)[#text(fill: brand, size: 21pt, weight: "bold")[{stats["featured_count"]}]#linebreak()#text(fill: muted-color, size: 8pt)[篇精读复盘]]
  ][
    #box(fill: cover-card, stroke: 0.6pt + line, inset: 8pt, radius: 10pt)[#text(fill: brand, size: 21pt, weight: "bold")[{stats["questions_count"]}]#linebreak()#text(fill: muted-color, size: 8pt)[道考场训练]]
  ][
    #box(fill: cover-card, stroke: 0.6pt + line, inset: 8pt, radius: 10pt)[#text(fill: brand, size: 21pt, weight: "bold")[{stats["golden_count"]}]#linebreak()#text(fill: muted-color, size: 8pt)[句可背表达]]
  ][
    #box(fill: cover-card, stroke: 0.6pt + line, inset: 8pt, radius: 10pt)[#text(fill: brand, size: 21pt, weight: "bold")[{stats["quick_count"]}]#linebreak()#text(fill: muted-color, size: 8pt)[篇延伸索引]]
  ]
]

#v(8pt)
#grid(columns: (1.2fr, 0.9fr), gutter: 9pt)[
  #panel[使用说明][
    + 先看本周 3 分钟速览。
    + 再看考场素材库和金句表达库。
    + 再做本周 3 道考场迁移训练。
    + 周内没怎么看邮件的同学，再看每日内容压缩回看。
  ]
][
  #panel[本周训练主线][从“技术治理、执法规范、专业纠纷、生态边界”四类问题切入，训练申论对策题与面试综合分析题的材料转化能力。#v(5pt){t_badges(data["hot_keywords"], 8)}]
]

#pagebreak()
#set page(numbering: "1", header: align(left)[#text(size: 8.5pt, fill: muted-color)[公考晨读 · 周复盘资料包 V1]], footer: text(size: 8pt, fill: rgb("#94a3b8"))[周日复盘版 · 摘要/框架/表达/素材/题目/索引])

= 00｜使用说明
#info-strip[复盘顺序][先看本周 3 分钟速览，再看考场素材库和金句表达库，再做本周 3 道考场迁移训练；周内没怎么看邮件的同学，再看每日内容压缩回看。]
#grid(columns: (1fr), gutter: 8pt)[
  #panel[资料包定位][这份 PDF 面向周末复盘，不新增精读文章，只把本周已发送内容重新整理为考点、表达、素材和训练题。]
]

= 01｜本周主题总览
#info-strip[复盘方式][这份 PDF 不是把每日邮件简单拼接，而是按“周末复盘”的方式重新组织：先快速看总览，再集中沉淀素材、表达和训练题。]

#table(columns: (0.8fr, 2fr, 2.2fr, 1.7fr), inset: 5pt, stroke: 0.45pt + line, fill: (x, y) => if y == 0 {{ table-head }} else if calc.odd(y) {{ rgb("#f8fafc") }} else {{ white }},
  [#text(fill: brand, weight: "bold")[日期]], [#text(fill: brand, weight: "bold")[主题]], [#text(fill: brand, weight: "bold")[精读文章]], [#text(fill: brand, weight: "bold")[训练方向]],
  {overview_rows}
)

#pagebreak()
#block-title[02｜本周高频考点地图]
#grid(columns: (1fr, 1fr), gutter: 8pt)[
{map_cards}
]

{''.join(daily_sections)}

#pagebreak()
= 03｜本周金句表达库
#info-strip[使用建议][这一部分用于周末集中背诵。优先记能直接放进申论段落或面试表达里的句子。]
#block-title[可背金句]
#quote-bank[
  {expression_rows if expression_rows else '#muted[暂无可抽取金句]'}
]
#block-title[可迁移框架]
{framework_rows if framework_rows else '#muted[暂无可迁移框架]'}

#pagebreak()
= 04｜本周考场素材库
#info-strip[使用建议][素材卡优先保留有事实锚点或机制做法的内容；没有稳定事实支撑时不强行提炼。]
{material_cards if material_cards else '#muted[本周暂无稳定可提炼的考场素材卡]'}

#pagebreak()
= 05｜本周素材运用题
#info-strip[使用建议][三道题分别用于面试综合分析、对策建议和申论作文分论点展开训练。对策建议题不建议硬塞外部案例。]
{practice_questions if practice_questions else '#muted[本周暂无稳定可生成的素材运用题]'}

#pagebreak()
= 06｜延伸阅读索引
#info-strip[说明][本页只做“摘要 + 原文入口”。如需阅读全文，请复制链接打开原文；PDF 不收录延伸阅读全文。]
#block-title[精读原文入口]
#table(columns: (0.7fr, 2.3fr, 1.2fr, 2.6fr), inset: 5pt, stroke: 0.45pt + line, fill: (x, y) => if y == 0 {{ table-head }} else if calc.odd(y) {{ rgb("#f8fafc") }} else {{ white }},
  [#text(fill: brand, weight: "bold")[日期]], [#text(fill: brand, weight: "bold")[文章]], [#text(fill: brand, weight: "bold")[主题]], [#text(fill: brand, weight: "bold")[一句话价值]],
  {featured_index_rows}
)
#block-title[补充阅读清单]
#table(columns: (0.7fr, 2.3fr, 1.2fr, 2.6fr), inset: 5pt, stroke: 0.45pt + line, fill: (x, y) => if y == 0 {{ table-head }} else if calc.odd(y) {{ rgb("#f8fafc") }} else {{ white }},
  [#text(fill: brand, weight: "bold")[日期]], [#text(fill: brand, weight: "bold")[文章]], [#text(fill: brand, weight: "bold")[主题]], [#text(fill: brand, weight: "bold")[考试价值]],
  {quick_index if quick_index else table_cell("") + "," + table_cell("暂无补充阅读") + "," + table_cell("") + "," + table_cell("") + ","}
)
"""


def build_typst_weekly_pdf(
    payloads: list[dict[str, Any]],
    misses: list[dict[str, str]],
    pdf_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    if not payloads:
        raise RuntimeError("没有可用于 Typst V1 周报的每日归档。")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_data(payloads, start_date, end_date, misses)
    typ_path = pdf_path.with_suffix(".typ")
    data_path = pdf_path.with_suffix(".json")
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    typ_path.write_text(render_typst(data), encoding="utf-8")
    typst = find_typst_binary()
    if not typst:
        raise RuntimeError(f"未找到 typst 命令，已生成 Typst 源文件：{typ_path}")
    subprocess.run([typst, "compile", str(typ_path), str(pdf_path)], check=True)
    return {
        "pdf_path": str(pdf_path),
        "typ_path": str(typ_path),
        "data_path": str(data_path),
        "engine": "typst",
        "template": "v1",
        "warnings": data["warnings"],
    }
