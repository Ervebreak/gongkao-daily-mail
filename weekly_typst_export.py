from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from config import settings
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


PREVIEW_FULL_MODULES = [
    "本周高频考点地图",
    "作文素材积累·一例多用",
    "本周金句表达库",
    "本周 3 道考场迁移训练",
    "每日内容压缩回看",
    "精读文章和延伸阅读索引",
]

PREVIEW_GENERIC_POINTS = {
    "基层治理",
    "公共服务",
    "民生保障",
    "社会治理",
    "服务群众",
    "协同治理",
    "担当",
    "奋斗",
    "创新",
}


def clip_complete_sentence(text: Any, limit: int = 180) -> str:
    raw = clean(text)
    if not raw:
        return ""
    if len(raw) <= limit:
        return raw
    window = raw[:limit]
    matches = list(re.finditer(r'[。！？!?][”’"）】》」』]*', window))
    for match in reversed(matches):
        candidate = window[: match.end()].strip()
        if len(candidate) >= max(40, limit // 3):
            return candidate
    return ""


def strip_field_label(text: Any) -> str:
    value = clean(text)
    if not value:
        return ""
    return re.sub(r"^[\u4e00-\u9fffA-Za-z]{1,12}[：:]\s*", "", value).strip()


def unique_non_empty(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = clean(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def is_specific_preview_point(text: str) -> bool:
    compact = re.sub(r"\s+", "", clean(text))
    if not compact:
        return False
    if compact in PREVIEW_GENERIC_POINTS:
        return False
    if len(compact) <= 6 and any(term in compact for term in PREVIEW_GENERIC_POINTS):
        return False
    return any(token in compact for token in ("要", "把", "从", "向", "解决", "推动", "形成", "转向", "避免", "落实", "闭环", "协同", "精准"))


def preview_focus_points(data: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for row in data.get("material_cards") or []:
        if isinstance(row, dict):
            candidates.extend(clean(item) for item in as_list(row.get("target_topics")) if clean(item))
    for row in data.get("practice_questions") or []:
        if isinstance(row, dict):
            candidates.extend(clean(item) for item in as_list(row.get("target_topics")) if clean(item))
            candidates.append(clean(row.get("title")))
    for row in data.get("exam_map_cards") or []:
        if isinstance(row, dict):
            candidates.append(clean(row.get("title")))
            candidates.append(clean(row.get("use_for")))
    result: list[str] = []
    for item in candidates:
        text = strip_field_label(item)
        if not is_specific_preview_point(text):
            continue
        if len(text) > 34:
            clipped = clip_complete_sentence(text, 34)
            text = clipped or text[:34].rstrip("，、；：,;: ")
        if text and text not in result:
            result.append(text)
        if len(result) >= 3:
            break
    return result[:3]


def preview_theme_overview(data: dict[str, Any]) -> str:
    themes = unique_non_empty([day.get("theme") or day.get("featured", {}).get("theme") for day in data.get("days") or []], 4)
    featured_count = int((data.get("stats") or {}).get("featured_count") or len(data.get("days") or []))
    question_count = int((data.get("stats") or {}).get("questions_count") or 0)
    if themes:
        joined = "、".join(themes)
        return f"这份周复盘预览覆盖 {data.get('start_date')} 至 {data.get('end_date')} 的内容，本周主要围绕 {joined} 展开，共整理 {featured_count} 篇精读复盘和 {question_count} 个题干练习方向，帮助你快速知道这一周重点学了什么。"
    return f"这份周复盘预览覆盖 {data.get('start_date')} 至 {data.get('end_date')} 的内容，重点带你快速回看本周精读、训练题和可迁移表达，先建立一周复盘框架，再决定是否深入看完整版资料包。"


def preview_expression_fragment(data: dict[str, Any]) -> str:
    for row in data.get("selected_expression_rows") or data.get("expression_rows") or []:
        if isinstance(row, dict):
            sentence = strip_field_label(row.get("sentence") or row.get("expression") or row.get("text"))
            if sentence:
                return sentence
    for day in data.get("days") or []:
        featured = day.get("featured") if isinstance(day.get("featured"), dict) else {}
        sentence = strip_field_label(featured.get("rewritable_expression"))
        if sentence:
            return sentence
    return ""


def preview_material_fragment(data: dict[str, Any]) -> dict[str, str]:
    for row in data.get("material_cards") or []:
        if not isinstance(row, dict):
            continue
        summary = clip_complete_sentence(row.get("material_summary"), 160) or clean(row.get("material_summary"))
        title = clean(row.get("title") or row.get("source_title") or "本周素材片段")
        source = "、".join(unique_non_empty(as_list(row.get("source_articles")), 2))
        if summary:
            return {"title": title, "source": source, "summary": summary}
    for day in data.get("days") or []:
        featured = day.get("featured") if isinstance(day.get("featured"), dict) else {}
        summary = clip_complete_sentence(featured.get("one_sentence"), 160) or clean(featured.get("one_sentence"))
        if summary:
            return {
                "title": clean(featured.get("title") or "本周精读片段"),
                "source": clean(featured.get("source")),
                "summary": summary,
            }
    return {}


def preview_practice_fragment(data: dict[str, Any]) -> dict[str, str]:
    for row in data.get("practice_questions") or []:
        if not isinstance(row, dict):
            continue
        question = clean(row.get("question"))
        direction = clean(row.get("answer_hint") or row.get("use_hint") or row.get("target_topics"))
        if question:
            return {
                "title": clean(row.get("title") or "本周训练题片段"),
                "question": question,
                "direction": clip_complete_sentence(direction, 90) or direction,
            }
    for day in data.get("days") or []:
        question = day.get("question") if isinstance(day.get("question"), dict) else {}
        stem = clean(question.get("question"))
        framework = [clean(item) for item in as_list(question.get("answer_framework")) if clean(item)]
        if stem:
            return {
                "title": "本周训练题片段",
                "question": stem,
                "direction": "；".join(framework[:2]),
            }
    return {}


def build_preview_data(payloads: list[dict[str, Any]], start_date: str, end_date: str, misses: list[dict[str, str]]) -> dict[str, Any]:
    data = build_data(payloads, start_date, end_date, misses)
    cta_url = settings.paid_trial_entry_url.strip() or settings.feedback_base_url.strip()
    return {
        "start_date": start_date,
        "end_date": end_date,
        "period": data.get("period"),
        "theme_overview": preview_theme_overview(data),
        "focus_points": preview_focus_points(data),
        "full_modules": PREVIEW_FULL_MODULES,
        "expression_preview": preview_expression_fragment(data),
        "material_preview": preview_material_fragment(data),
        "practice_preview": preview_practice_fragment(data),
        "cta_url": cta_url,
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
            for item in takeaway["golden_sentences"][:2]
        )
        daily_sections.append(
            f"""
#day-title("DAY {day["day_no"]:02d}", "{typst_text(day["short_date"])}｜{typst_text(day["weekday"])}｜{typst_text(day["theme"])}", "{typst_text(day["focus"])}")

#block-title[A. 内容压缩回看]
#article-card[
  #muted[{typst_text(featured["source"])}｜{typst_text(featured["published_at"])}｜{typst_text(featured["theme"])}]
  #v(3pt)
  #text(size: 14pt, weight: "bold")[{typst_text(featured["title"])}]
  #v(5pt)
  #info-strip[一句话看懂][{typst_text(featured["one_sentence"])}]
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

#block-title[B. 题干与作答框架]
#question-card[
  #badge[{typst_text(question["question_type"])}]
  #v(4pt)
  #text(size: 11.5pt, weight: "bold")[{typst_text(question["question"])}]
  #text(weight: "bold", fill: brand)[作答框架]
  {answer_framework}
]

#block-title[C. 1-2 句可背表达]
#takeaway-card[
  {golden_blocks if golden_blocks else '#muted[暂无金句]'}
  #if "{typst_text(featured["rewritable_expression"])}" != "" [
    #info-strip[可改写表达][{typst_text(featured["rewritable_expression"])}]
  ]
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

    def row_list(row: dict[str, Any], *keys: str) -> list[str]:
        for key in keys:
            value = row.get(key)
            if isinstance(value, list):
                rows = [clean(item) for item in value if clean(item)]
                if rows:
                    return rows
        return []

    def material_example_blocks(row: dict[str, Any]) -> str:
        blocks: list[str] = []
        for example in as_list(row.get("usage_examples"))[:3]:
            if not isinstance(example, dict):
                continue
            theme = clean(example.get("theme"))
            content = clean(example.get("example"))
            if not theme or not content:
                continue
            blocks.append(f'#material-example[{typst_text(theme)}][{typst_text(content)}]')
        return "\n#v(6pt)\n".join(blocks)

    def merged_material_boundary(row: dict[str, Any]) -> str:
        parts: list[str] = []
        use_boundary = row_value(row, "use_boundary")
        not_suitable = row_list(row, "not_suitable_for")
        if use_boundary:
            parts.append(use_boundary)
        if not_suitable:
            extra = "不宜直接用于" + "、".join(not_suitable)
            if extra not in parts:
                parts.append(extra)
        return " ".join(parts)

    material_parts: list[str] = []
    for idx, row in enumerate((data.get("material_cards") or [])[:3], start=1):
        if not isinstance(row, dict):
            continue
        title = row_value(row, "title", "source_title", "theme") or f"素材卡 {idx:02d}"
        material_type = row_value(row, "material_type", "type")
        source_dates = row_value(row, "source_dates", "date")
        source_articles = row_value(row, "source_articles", "source_title")
        target_topics = row_value(row, "target_topics", "theme")
        material_summary = row_value(row, "material_summary")
        example_blocks = material_example_blocks(row)
        suggested_question_types = row_value(row, "suggested_question_types")
        use_boundary = merged_material_boundary(row)
        material_parts.append(
            f'#material-card[{typst_text(title)}][{typst_text(material_type)}][{typst_text(source_dates)}][{typst_text(source_articles)}]'
            f'[{typst_text(material_summary)}][{example_blocks}]'
            f'[{typst_text(use_boundary)}][{typst_text(target_topics)}][{typst_text(suggested_question_types)}]'
        )
    material_cards = "\n#v(7pt)\n".join(material_parts)
    has_material_cards = bool(material_parts)

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

    overview_exam_points = "\n".join(
        f'- {typst_text(card.get("title"))}：{typst_text(card.get("summary") or card.get("body") or card.get("description"))}'
        for card in (data.get("exam_map_cards") or [])[:5]
        if isinstance(card, dict) and clean(card.get("title"))
    )
    overview_expressions = "\n".join(
        f'- {typst_text(row.get("sentence") or row.get("expression") or row.get("text"))}'
        for row in expression_source[:3]
        if isinstance(row, dict) and clean(row.get("sentence") or row.get("expression") or row.get("text"))
    )
    first_practice = next((row for row in data.get("practice_questions") or [] if isinstance(row, dict)), {})
    overview_practice = (
        f'#badge[{typst_text(row_value(first_practice, "question_type"))}]'
        f'#v(4pt)#text(weight: "bold")[{typst_text(row_value(first_practice, "title") or "本周第一题")}]'
        f'#linebreak(){typst_text(row_value(first_practice, "question"))}'
        if first_practice
        else '#muted[暂无可展示训练题]'
    )
    overview_keywords = t_badges(data.get("hot_keywords") or [], 8)
    review_order_text = (
        "先看本页速览，再看作文素材积累和金句表达库，再做本周 3 道考场迁移训练；周内没怎么看邮件的同学，再看每日内容压缩回看。"
        if has_material_cards
        else "先看本页速览，再看金句表达库，再做本周 3 道考场迁移训练；周内没怎么看邮件的同学，再看每日内容压缩回看。"
    )
    review_method_text = (
        "这份 PDF 按“重点优先”重新组织：先抓考点、作文素材、表达和训练题，再回看每日内容。"
        if has_material_cards
        else "这份 PDF 按“重点优先”重新组织：先抓考点、表达和训练题，再回看每日内容。"
    )
    material_section = ""
    next_section_no = 3
    if has_material_cards:
        material_section = f"""
#pagebreak()
= {next_section_no:02d}｜作文素材积累·一例多用
#info-strip[使用建议][只保留本周真正有事实依据、能迁移到考场表达里的素材；宁缺毋滥，不为凑数补卡。]
{material_cards}
"""
        next_section_no += 1
    expression_section_no = next_section_no
    next_section_no += 1
    practice_section_no = next_section_no
    next_section_no += 1
    daily_section_no = next_section_no
    next_section_no += 1
    quick_section_no = next_section_no

    return f"""
#set document(title: [公考晨读周复盘资料包 V1.3])
#set page(
  paper: "a4",
  margin: (x: 13mm, y: 17mm),
  numbering: "1",
  header: align(left)[#text(size: 8.5pt, fill: rgb("#64748b"))[公考晨读 · 周复盘资料包 V1.3]],
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
#let material-example(theme, body) = block(fill: rgb("#f8fbff"), stroke: 0.45pt + line, inset: 8pt, radius: 6pt, width: 100%, breakable: true)[
  #text(weight: "bold", fill: brand)[#theme]
  #v(3pt)
  #body
]
#let material-card(title, material-type, source-dates, source-articles, material-summary, examples, use-boundary, target-topics, suggested-question-types) = block(fill: white, stroke: 0.6pt + line, inset: 10pt, radius: 7.5pt, width: 100%, breakable: true)[
  #text(size: 12pt, weight: "bold", fill: brand)[作文素材积累·#title（一例多用）]
  #if material-type != "" [#linebreak()#badge[#material-type]]
  #v(5pt)
  #if source-dates != "" or source-articles != "" [#info-strip[来源][#source-dates#if source-dates != "" and source-articles != "" [｜#source-articles]]]
  #if target-topics != "" [#info-strip[可用主题方向][#target-topics]]
  #if suggested-question-types != "" [#info-strip[适用题型][#suggested-question-types]]
  #if material-summary != "" [#info-strip[素材简介][#material-summary]]
  #if examples != "" [
    #v(4pt)
    #text(weight: "bold", fill: brand)[作文示例]
    #v(4pt)
    #examples
  ]
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
  #text(fill: blue, size: 26pt, weight: "bold")[重点优先型周复盘资料包 V1.3]
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
#set page(numbering: "1", header: align(left)[#text(size: 8.5pt, fill: muted-color)[公考晨读 · 周复盘资料包 V1.3]], footer: text(size: 8pt, fill: rgb("#94a3b8"))[周日复盘版 · 速览/考点/素材/表达/训练/回看/索引])

= 01｜本周 3 分钟速览
#info-strip[复盘顺序][{typst_text(review_order_text)}]
#grid(columns: (1fr, 1fr), gutter: 8pt)[
  #panel[高频考点][{overview_exam_points if overview_exam_points else '#muted[暂无高频考点]'}]
][
  #panel[关键词][{overview_keywords if overview_keywords else '#muted[暂无关键词]'}]
]
#grid(columns: (1fr, 1fr), gutter: 8pt)[
  #panel[最值得背][{overview_expressions if overview_expressions else '#muted[暂无精选表达]'}]
][
  #panel[最值得练][{overview_practice}]
]

#block-title[本周主题总览]
#info-strip[复盘方式][{typst_text(review_method_text)}]

#table(columns: (0.8fr, 2fr, 2.2fr, 1.7fr), inset: 5pt, stroke: 0.45pt + line, fill: (x, y) => if y == 0 {{ table-head }} else if calc.odd(y) {{ rgb("#f8fafc") }} else {{ white }},
  [#text(fill: brand, weight: "bold")[日期]], [#text(fill: brand, weight: "bold")[主题]], [#text(fill: brand, weight: "bold")[精读文章]], [#text(fill: brand, weight: "bold")[训练方向]],
  {overview_rows}
)

#pagebreak()
#block-title[02｜本周高频考点地图]
#grid(columns: (1fr, 1fr), gutter: 8pt)[
{map_cards}
]

{material_section}

#pagebreak()
= {expression_section_no:02d}｜本周金句表达库
#info-strip[使用建议][这一部分用于周末集中背诵。优先记能直接放进申论段落或面试表达里的句子。]
#block-title[可背金句]
#quote-bank[
  {expression_rows if expression_rows else '#muted[暂无可抽取金句]'}
]
#block-title[可迁移框架]
{framework_rows if framework_rows else '#muted[暂无可迁移框架]'}

#pagebreak()
= {practice_section_no:02d}｜本周 3 道考场迁移训练
#info-strip[使用建议][三道题分别用于面试综合分析、对策建议和申论作文分论点展开训练。对策建议题不建议硬塞外部案例。]
{practice_questions if practice_questions else '#muted[本周暂无稳定可生成的素材运用题]'}

#pagebreak()
= {daily_section_no:02d}｜每日内容压缩回看
#info-strip[说明][这里只保留主题、精读文章、一句话看懂、文章框架、题干、作答框架和 1-2 句表达；完整参考答案、30 秒表达和参考开头不在本章展开。]
{('#v(10pt)').join(daily_sections)}

#pagebreak()
= {quick_section_no:02d}｜延伸阅读索引
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


def render_preview_typst(data: dict[str, Any]) -> str:
    focus_rows = "\n".join(f"- {typst_text(item)}" for item in data.get("focus_points") or [])
    if not focus_rows:
        focus_rows = "- 本周重点以精读文章主线、题干拆解和可迁移表达为主，先建立复盘框架。"
    module_rows = "\n".join(f"- {typst_text(item)}" for item in data.get("full_modules") or PREVIEW_FULL_MODULES)
    expression_preview = typst_text(data.get("expression_preview") or "本周会从精读文章里提炼可直接复用的表达，完整版会给出更完整的金句表达库。")
    material_preview = data.get("material_preview") if isinstance(data.get("material_preview"), dict) else {}
    material_title = typst_text(material_preview.get("title") or "本周素材片段")
    material_source = typst_text(material_preview.get("source") or "")
    material_summary = typst_text(material_preview.get("summary") or "完整版会把有事实依据、可迁移到申论和面试表达里的素材做成可收藏的复盘卡片。")
    practice_preview = data.get("practice_preview") if isinstance(data.get("practice_preview"), dict) else {}
    practice_title = typst_text(practice_preview.get("title") or "本周训练题片段")
    practice_question = typst_text(practice_preview.get("question") or "完整版资料包会附上本周 3 道考场迁移训练题，帮助你把一周内容转成作答表达。")
    practice_direction = typst_text(practice_preview.get("direction") or "预览版只保留题干或思考方向，不展示完整参考答案。")
    cta_url = clean(data.get("cta_url"))
    cta_line = (
        f"如果你想看完整周 PDF，可以回复邮件，或通过这个入口了解完整版：{typst_text(cta_url)}"
        if cta_url
        else "如果你想看完整周 PDF，可以直接回复邮件了解完整版。"
    )
    return f"""
#set document(title: [公考晨读周复盘预览版])
#set page(
  paper: "a4",
  margin: (x: 15mm, y: 18mm),
  numbering: "1",
)
#set text(font: ("Microsoft YaHei", "SimSun"), size: 10.5pt, lang: "zh")
#set par(justify: false, leading: 0.72em, spacing: 0.65em)

#let brand = rgb("#0f3b68")
#let line = rgb("#d7e2ef")
#let soft = rgb("#f6f8fb")
#let warm = rgb("#fff8e8")
#let muted(body) = text(size: 8.8pt, fill: rgb("#64748b"))[#body]
#let section(title, body) = block(fill: white, stroke: 0.6pt + line, inset: 10pt, radius: 7pt, width: 100%, breakable: true)[#text(size: 12pt, weight: "bold", fill: brand)[#title]#v(5pt)#body]
#let chip(body) = box(fill: rgb("#e9f3ff"), stroke: 0.5pt + rgb("#cfe3fb"), inset: (x: 6pt, y: 2pt), radius: 7pt)[#text(size: 8.2pt, fill: brand, weight: "bold")[#body]]

#box(fill: soft, stroke: 0.8pt + line, inset: 20pt, radius: 12pt, width: 100%)[
  #text(fill: brand, size: 10pt, weight: "bold")[WEEKLY REVIEW · 免费预览版]
  #v(10pt)
  #text(fill: brand, size: 26pt, weight: "bold")[公考晨读周复盘预览]
  #v(6pt)
  #text(size: 11pt)[{typst_text(data.get("period") or "")}]
  #v(12pt)
  #text(size: 11pt)[这是一份周复盘预览，帮你快速了解本周重点，也先看看完整版资料包会提供什么。]
]

#v(10pt)
#section[本周主题速览][{typst_text(data.get("theme_overview") or "")}]

#v(8pt)
#section[本周 3 个高频考点方向][{focus_rows}]

#v(8pt)
#section[完整版 PDF 目录预览][
  {module_rows}
]

#v(8pt)
#section[免费内容片段][
  #text(weight: "bold", fill: brand)[1 条可背表达]
  #v(3pt)
  {expression_preview}
  #v(8pt)
  #text(weight: "bold", fill: brand)[1 个素材简介片段]
  #v(3pt)
  {material_title}
  #if "{material_source}" != "" [#linebreak()#muted[来源：{material_source}]]
  #linebreak(){material_summary}
  #v(8pt)
  #text(weight: "bold", fill: brand)[1 道训练题片段]
  #v(3pt)
  {practice_title}
  #linebreak(){practice_question}
  #if "{practice_direction}" != "" [#linebreak()#muted[思考方向：{practice_direction}]]
]

#v(8pt)
#section[获取完整版][
  完整版周 PDF 会提供更完整的素材、表达、训练题和每日压缩回看。暂时不参加也没关系，这份预览可以先帮你建立本周复盘框架。
  #v(6pt)
  {typst_text(cta_line)}
]
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


def build_typst_weekly_preview_pdf(
    payloads: list[dict[str, Any]],
    misses: list[dict[str, str]],
    pdf_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    if not payloads:
        raise RuntimeError("没有可用于 Typst 周预览版的每日归档。")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_preview_data(payloads, start_date, end_date, misses)
    typ_path = pdf_path.with_suffix(".typ")
    data_path = pdf_path.with_suffix(".json")
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    typ_path.write_text(render_preview_typst(data), encoding="utf-8")
    typst = find_typst_binary()
    if not typst:
        raise RuntimeError(f"未找到 typst 命令，已生成周预览 Typst 源文件：{typ_path}")
    subprocess.run([typst, "compile", str(typ_path), str(pdf_path)], check=True)
    return {
        "pdf_path": str(pdf_path),
        "typ_path": str(typ_path),
        "data_path": str(data_path),
        "engine": "typst",
        "template": "weekly_preview_v1",
        "warnings": [],
    }
