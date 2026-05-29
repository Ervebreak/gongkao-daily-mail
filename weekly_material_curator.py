from __future__ import annotations

import json
import re
from typing import Any

from config import settings


EXPECTED_KEYS = (
    "exam_map_cards",
    "selected_expression_rows",
    "material_cards",
    "practice_questions",
    "warnings",
)

MATERIAL_TOPIC_KEYWORDS = {
    "基层治理",
    "公共服务",
    "依法行政",
    "劳动权益",
    "安全生产",
    "市场监管",
    "校园治理",
    "青年就业",
    "民生",
    "就业",
    "教育",
    "医疗",
    "养老",
    "社区",
    "执法",
    "监管",
    "营商环境",
}

MATERIAL_SCENE_KEYWORDS = {
    "群众",
    "企业",
    "社区",
    "学校",
    "学生",
    "家长",
    "劳动者",
    "平台",
    "商家",
    "游客",
    "老人",
    "儿童",
    "基层",
    "一线",
    "纠纷",
    "投诉",
    "矛盾",
    "隐患",
    "事故",
    "整治",
    "服务",
    "办理",
    "就业",
    "欠薪",
    "执法",
    "监管",
}

MATERIAL_MECHANISM_KEYWORDS = {
    "机制",
    "做法",
    "举措",
    "清单",
    "台账",
    "闭环",
    "协同",
    "联动",
    "网格",
    "热线",
    "平台",
    "制度",
    "标准",
    "流程",
    "问责",
    "回访",
    "公示",
    "分类",
    "分级",
    "试点",
}

MACRO_THEORY_KEYWORDS = {
    "理论",
    "思想",
    "精神",
    "战略",
    "全局",
    "大局",
    "宏观",
    "体系",
    "现代化",
    "高质量发展",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "；".join(_clean(item) for item in value if _clean(item))
    if isinstance(value, dict):
        return "；".join(_clean(item) for item in value.values() if _clean(item))
    return str(value).strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _blank_enrichment(warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "exam_map_cards": [],
        "selected_expression_rows": [],
        "material_cards": [],
        "practice_questions": [],
        "warnings": list(warnings or []),
    }


def _model_candidates() -> list[str]:
    candidates = [
        settings.content_quality_llm_model,
        settings.writing_llm_model,
        settings.llm_model,
    ]
    return _dedupe(candidates)


def _fallback_model_candidates() -> list[str]:
    candidates = [
        settings.content_quality_llm_fallback_model,
        settings.writing_llm_fallback_model,
        settings.llm_fallback_model,
    ]
    return _dedupe(candidates)


def _dedupe(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for model in candidates:
        model = (model or "").strip()
        if model and model not in seen:
            seen.add(model)
            result.append(model)
    return result


def _timeout_seconds() -> int:
    return int(getattr(settings, "content_quality_timeout", None) or settings.llm_timeout)


def _clip_text(text: Any, limit: int = 900) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    for mark in ["。", "！", "？", "；"]:
        pos = cut.rfind(mark)
        if pos >= max(80, limit // 2):
            return cut[: pos + 1].strip()
    return cut[:limit].rstrip("，,；;、：:").strip()


def _compact_days(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for day in days:
        featured = day.get("featured") if isinstance(day.get("featured"), dict) else {}
        question = day.get("question") if isinstance(day.get("question"), dict) else {}
        takeaway = day.get("takeaway") if isinstance(day.get("takeaway"), dict) else {}
        compact.append(
            {
                "date": _clean(day.get("date")),
                "theme": _clean(day.get("theme")),
                "focus": _clean(day.get("focus")),
                "tags": [_clean(item) for item in _as_list(day.get("tags")) if _clean(item)][:8],
                "featured": {
                    "title": _clean(featured.get("title")),
                    "source": _clean(featured.get("source")),
                    "url": _clean(featured.get("url")),
                    "published_at": _clean(featured.get("published_at")),
                    "one_sentence": _clean(featured.get("one_sentence")),
                    "original_reading_focus": _clean(featured.get("original_reading_focus")),
                    "three_useful_points": [_clean(item) for item in _as_list(featured.get("three_useful_points")) if _clean(item)][:4],
                    "exam_use": [_clean(item) for item in _as_list(featured.get("exam_use")) if _clean(item)][:4],
                    "article_type": _clean(featured.get("article_type")),
                    "main_thread": _clean(featured.get("main_thread")),
                },
                "steps": [
                    {"label": _clean(item.get("label")), "content": _clean(item.get("content"))}
                    for item in _as_list(day.get("steps"))
                    if isinstance(item, dict) and (_clean(item.get("label")) or _clean(item.get("content")))
                ][:5],
                "question": {
                    "question_type": _clean(question.get("question_type")),
                    "question": _clean(question.get("question")),
                    "exam_focus": _clean(question.get("exam_focus")),
                    "breaking_hint": _clean(question.get("breaking_hint")),
                    "answer_framework": [_clean(item) for item in _as_list(question.get("answer_framework")) if _clean(item)][:5],
                },
                "takeaway": {
                    "keywords": [_clean(item) for item in _as_list(takeaway.get("keywords")) if _clean(item)][:6],
                    "common_knowledge_points": [_clean(item) for item in _as_list(takeaway.get("common_knowledge_points")) if _clean(item)][:2],
                    "golden_sentences": [
                        {
                            "sentence": _clean(item.get("sentence")),
                            "scenario": _clean(item.get("scenario")),
                        }
                        for item in _as_list(takeaway.get("golden_sentences"))
                        if isinstance(item, dict) and _clean(item.get("sentence"))
                    ][:3],
                    "framework": _clean(takeaway.get("framework")),
                },
                "quick_reads": [
                    {
                        "title": _clean(item.get("title")),
                        "source": _clean(item.get("source")),
                        "url": _clean(item.get("url")),
                        "theme": _clean(item.get("theme")),
                        "exam_value": _clean(item.get("exam_value")),
                        "one_sentence": _clean(item.get("one_sentence")),
                    }
                    for item in _as_list(day.get("quick_reads"))
                    if isinstance(item, dict) and (_clean(item.get("title")) or _clean(item.get("url")))
                ][:3],
            }
        )
    return compact


def _article_candidate_text(article: dict[str, Any]) -> str:
    fields = [
        article.get("title"),
        article.get("theme"),
        article.get("exam_value"),
        article.get("one_sentence"),
        article.get("day_focus"),
        article.get("source"),
    ]
    return " ".join(_clean(item) for item in fields if _clean(item))


def _material_candidate_score(article: dict[str, Any]) -> int:
    text = _article_candidate_text(article)
    score = 0
    score += 10 if article.get("role") == "featured" else 4
    score += min(sum(1 for word in MATERIAL_TOPIC_KEYWORDS if word in text) * 5, 25)
    score += min(sum(1 for word in MATERIAL_SCENE_KEYWORDS if word in text) * 4, 24)
    score += min(sum(1 for word in MATERIAL_MECHANISM_KEYWORDS if word in text) * 4, 24)
    if re.search(r"困境|难题|问题|冲突|争议|痛点|堵点|风险|乱象|治理|整改|帮扶|维权", text):
        score += 12
    if re.search(r"某地|当地|部门|街道|社区|企业|平台|学校|医院|工地|市场|执法|检查", text):
        score += 10
    if any(word in text for word in MACRO_THEORY_KEYWORDS):
        score -= 12
    if not article.get("url"):
        score -= 8
    if len(text) < 30:
        score -= 6
    return score


def select_material_candidate_articles(days: list[dict[str, Any]], max_candidates: int = 6) -> list[dict[str, Any]]:
    """Select a small article set suitable for material-card evidence reading."""
    compact_days = _compact_days(days)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for day in compact_days:
        date = _clean(day.get("date"))
        theme = _clean(day.get("theme"))
        focus = _clean(day.get("focus"))
        featured = day.get("featured") if isinstance(day.get("featured"), dict) else {}
        featured_url = _clean(featured.get("url"))
        featured_key = featured_url or _clean(featured.get("title"))
        if featured_key and featured_key not in seen:
            seen.add(featured_key)
            candidates.append(
                {
                    "role": "featured",
                    "date": date,
                    "title": _clean(featured.get("title")),
                    "source": _clean(featured.get("source")),
                    "url": featured_url,
                    "theme": _clean(featured.get("theme") or theme),
                    "one_sentence": _clean(featured.get("one_sentence")),
                    "exam_value": "；".join(_clean(item) for item in _as_list(featured.get("exam_use"))[:3] if _clean(item)),
                    "day_focus": focus,
                }
            )
        for item in _as_list(day.get("quick_reads")):
            if not isinstance(item, dict):
                continue
            key = _clean(item.get("url")) or _clean(item.get("title"))
            if not key or key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "role": "quick_read",
                    "date": date,
                    "title": _clean(item.get("title")),
                    "source": _clean(item.get("source")),
                    "url": _clean(item.get("url")),
                    "theme": _clean(item.get("theme") or theme),
                    "one_sentence": _clean(item.get("one_sentence")),
                    "exam_value": _clean(item.get("exam_value")),
                    "day_focus": focus,
                }
            )
    scored = [
        {
            **item,
            "material_score": _material_candidate_score(item),
            "selection_reason": _selection_reason(item),
        }
        for item in candidates
    ]
    scored.sort(key=lambda item: (-int(item.get("material_score") or 0), item.get("date") or "", item.get("title") or ""))
    return scored[: max(1, max_candidates)]


def _selection_reason(article: dict[str, Any]) -> str:
    text = _article_candidate_text(article)
    reasons: list[str] = []
    if any(word in text for word in MATERIAL_TOPIC_KEYWORDS):
        reasons.append("命中高频考点")
    if any(word in text for word in MATERIAL_SCENE_KEYWORDS):
        reasons.append("包含具体场景或问题")
    if any(word in text for word in MATERIAL_MECHANISM_KEYWORDS):
        reasons.append("包含机制做法")
    if article.get("role") == "featured":
        reasons.append("本周精读文章")
    return "；".join(reasons[:3]) or "标题摘要具备素材提炼可能"


def _extract_article_paragraphs(html: str, url: str = "") -> list[str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    if "data.people.com.cn/rmrb/" in url:
        root = soup.select_one(".detail_con") or soup.select_one(".div_detail")
    else:
        root = soup.select_one(".rm_txt_con, .artDet, .main, .content, article")
    root = root or soup
    paragraphs: list[str] = []
    for p in root.find_all("p"):
        text = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
        if len(text) >= 25 and not re.search(r"责任编辑|版权|新华社客户端|扫一扫|客户端", text):
            paragraphs.append(text)
    if paragraphs:
        return paragraphs[:12]
    text = re.sub(r"\s+", " ", root.get_text(" ", strip=True)).strip()
    chunks = re.split(r"(?<=[。！？])", text)
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 35][:10]


def _fetch_article_evidence(article: dict[str, Any]) -> dict[str, Any]:
    url = _clean(article.get("url"))
    if not url:
        return {**article, "evidence_status": "skipped_no_url", "evidence_paragraphs": []}
    try:
        import requests

        response = requests.get(url, timeout=12, headers={"User-Agent": USER_AGENT}, verify=False)
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = "utf-8"
        paragraphs = _extract_article_paragraphs(response.text, url)
        return {
            **article,
            "evidence_status": "ok" if paragraphs else "empty",
            "evidence_paragraphs": [_clip_text(paragraph, 260) for paragraph in paragraphs[:8]],
        }
    except Exception as exc:
        return {
            **article,
            "evidence_status": f"fetch_failed: {type(exc).__name__}",
            "evidence_paragraphs": [],
        }


def build_material_candidate_evidence(days: list[dict[str, Any]], max_candidates: int = 6) -> list[dict[str, Any]]:
    candidates = select_material_candidate_articles(days, max_candidates=max_candidates)
    return [_fetch_article_evidence(article) for article in candidates]


def _build_prompt(days: list[dict[str, Any]]) -> str:
    material_candidate_articles = build_material_candidate_evidence(days, max_candidates=6)
    return f"""
你是公考周末复盘资料包编辑。请只基于输入的本周结构化摘要和候选文章证据生成周报增强数据。

硬性规则：
1. 只使用输入 JSON 中已有信息，不得编造外部事实、政策、案例、数字、地名、部门名。
2. material_cards 只能从 material_candidate_articles 中提炼，优先使用 evidence_paragraphs 中出现的事实锚点或机制做法。
3. 不要推测未提供的文章全文；输入中没有的事实不要补。
4. 对策建议题不要硬塞外部案例。
5. 所有句子必须完整，不得出现省略号、半截句、悬空动词或未完成判断。
6. 只输出合法 JSON 对象，不要输出解释。
7. 如果候选文章证据不足，material_cards 可以少于 3 条或为空。

输出字段：
{{
  "exam_map_cards": [
    {{"title": "4到12字考点名", "summary": "完整短句，说明本周为什么高频", "use_for": "适用题型或场景", "keywords": ["关键词"]}}
  ],
  "selected_expression_rows": [
    {{"date": "日期", "theme": "主题", "sentence": "精选金句或可用表达", "scenario": "适用场景"}}
  ],
  "material_cards": [
    {{"title": "素材卡标题", "material_type": "case或mechanism", "source_dates": ["日期"], "source_articles": ["来源文章标题"], "target_topics": ["适用考点"], "factual_anchor": "事实锚点或机制做法", "exam_paragraph": "可放入申论或面试的素材段", "memory_sentence": "一句话记忆", "use_tip": "用法提示", "use_boundary": "使用边界"}}
  ],
  "practice_questions": [
    {{"question_type": "面试综合分析题", "question": "题目", "use_hint": "素材运用提示"}},
    {{"question_type": "对策建议题", "question": "题目", "use_hint": "素材运用提示"}},
    {{"question_type": "申论作文分论点展开题", "question": "题目", "use_hint": "素材运用提示"}}
  ],
  "warnings": ["无法处理或字段不足的说明"]
}}

数量要求：
- exam_map_cards：4到6个。
- selected_expression_rows：8到15条。
- material_cards：3到6条，必须有事实锚点或机制做法。
- practice_questions：严格3道，题型分别为面试综合分析题、对策建议题、申论作文分论点展开题。

输入 JSON：
{json.dumps({"days": _compact_days(days), "material_candidate_articles": material_candidate_articles}, ensure_ascii=False)}
""".strip()


def _is_complete_sentence(text: str) -> bool:
    text = _clean(text)
    if not text:
        return False
    if "…" in text or "..." in text:
        return False
    if text[-1] in "，、；：,;:":
        return False
    return True


def _valid_text_map(row: Any, required: list[str]) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    result = {key: _clean(row.get(key)) for key in required}
    if not all(result.values()):
        return None
    if any(not _is_complete_sentence(value) for value in result.values() if len(value) >= 18):
        return None
    return result


def _validate_enrichment(payload: dict[str, Any]) -> dict[str, Any]:
    warnings = [_clean(item) for item in _as_list(payload.get("warnings")) if _clean(item)]

    exam_map_cards: list[dict[str, Any]] = []
    for item in _as_list(payload.get("exam_map_cards")):
        row = _valid_text_map(item, ["title", "summary", "use_for"])
        if not row:
            continue
        keywords = [_clean(x) for x in _as_list(item.get("keywords") if isinstance(item, dict) else []) if _clean(x)]
        row["keywords"] = keywords[:6]
        exam_map_cards.append(row)

    selected_expression_rows: list[dict[str, str]] = []
    for item in _as_list(payload.get("selected_expression_rows")):
        row = _valid_text_map(item, ["date", "theme", "sentence", "scenario"])
        if row:
            selected_expression_rows.append(row)

    material_cards: list[dict[str, str]] = []
    for item in _as_list(payload.get("material_cards")):
        if not isinstance(item, dict):
            continue
        material_type = _clean(item.get("material_type") or item.get("type"))
        factual_anchor = _clean(item.get("factual_anchor") or item.get("anchor"))
        exam_paragraph = _clean(item.get("exam_paragraph") or item.get("exam_value"))
        source_title = _clean(item.get("source_title"))
        source_articles = [_clean(x) for x in _as_list(item.get("source_articles") or source_title) if _clean(x)]
        source_dates = [_clean(x) for x in _as_list(item.get("source_dates") or item.get("date")) if _clean(x)]
        target_topics = [_clean(x) for x in _as_list(item.get("target_topics") or item.get("theme")) if _clean(x)]
        if material_type not in {"case", "mechanism"} or not factual_anchor or not exam_paragraph or not source_articles:
            continue
        text_values = [
            _clean(item.get("title")),
            factual_anchor,
            exam_paragraph,
            _clean(item.get("memory_sentence")),
            _clean(item.get("use_tip")),
            _clean(item.get("use_boundary")),
        ]
        if any(value and len(value) >= 18 and not _is_complete_sentence(value) for value in text_values):
            continue
        material_cards.append(
            {
                "title": _clean(item.get("title")) or source_articles[0],
                "material_type": material_type,
                "source_dates": source_dates,
                "source_articles": source_articles,
                "target_topics": target_topics,
                "factual_anchor": factual_anchor,
                "exam_paragraph": exam_paragraph,
                "memory_sentence": _clean(item.get("memory_sentence")),
                "use_tip": _clean(item.get("use_tip")),
                "use_boundary": _clean(item.get("use_boundary")),
                # Backward-compatible aliases used by older renderers/tests.
                "date": "、".join(source_dates),
                "theme": "、".join(target_topics),
                "type": material_type,
                "anchor": factual_anchor,
                "exam_value": exam_paragraph,
                "source_title": source_articles[0],
            }
        )

    practice_questions: list[dict[str, str]] = []
    allowed_types = ["面试综合分析题", "对策建议题", "申论作文分论点展开题"]
    seen_types: set[str] = set()
    for item in _as_list(payload.get("practice_questions")):
        row = _valid_text_map(item, ["question_type", "question", "use_hint"])
        if not row:
            continue
        if row["question_type"] not in allowed_types or row["question_type"] in seen_types:
            continue
        seen_types.add(row["question_type"])
        practice_questions.append(row)

    if len(exam_map_cards) < 4:
        warnings.append("weekly enrichment returned fewer than 4 exam_map_cards")
    if len(selected_expression_rows) < 8:
        warnings.append("weekly enrichment returned fewer than 8 selected_expression_rows")
    if len(material_cards) < 3:
        warnings.append("weekly enrichment returned fewer than 3 material_cards")
    if len(practice_questions) != 3:
        warnings.append("weekly enrichment did not return exactly 3 practice_questions")

    return {
        "exam_map_cards": exam_map_cards[:6],
        "selected_expression_rows": selected_expression_rows[:15],
        "material_cards": material_cards[:6],
        "practice_questions": practice_questions[:3],
        "warnings": warnings,
    }


def _call_curator_model(days: list[dict[str, Any]]) -> dict[str, Any]:
    from llm_client import chat_completion

    prompt = _build_prompt(days)
    errors: list[str] = []
    candidates = _model_candidates() + _fallback_model_candidates()
    for attempt, model in enumerate(candidates, start=1):
        try:
            response = chat_completion(
                model,
                prompt,
                timeout=_timeout_seconds(),
                trace={
                    "stage": "weekly_material_curator",
                    "attempt": attempt,
                    "candidate_count": len(candidates),
                    "fallback_used": attempt > 1,
                },
            )
            if not isinstance(response, dict):
                raise ValueError("weekly material curator returned non-object JSON")
            return _validate_enrichment(response)
        except Exception as exc:
            errors.append(f"{model}: {type(exc).__name__}: {exc}")
    return _blank_enrichment(["weekly material curator model failed: " + " | ".join(errors[:4])])


def _fallback_selected_expression_rows(days: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for day in days:
        takeaway = day.get("takeaway") if isinstance(day.get("takeaway"), dict) else {}
        for item in _as_list(takeaway.get("golden_sentences")):
            if not isinstance(item, dict):
                continue
            sentence = _clean(item.get("sentence"))
            scenario = _clean(item.get("scenario"))
            if sentence and _is_complete_sentence(sentence):
                rows.append(
                    {
                        "date": _clean(day.get("short_date") or day.get("date")),
                        "theme": _clean(day.get("theme")),
                        "sentence": sentence,
                        "scenario": scenario,
                    }
                )
    return rows[:15]


def build_weekly_enrichment(days: list[dict[str, Any]]) -> dict[str, Any]:
    """Build fail-open weekly enrichment from normalized weekly days."""
    if not days:
        return _blank_enrichment(["weekly enrichment skipped: no days"])

    if not settings.dashscope_api_key:
        result = _blank_enrichment(["weekly enrichment skipped: DASHSCOPE_API_KEY is empty"])
    else:
        result = _call_curator_model(days)

    if not result.get("selected_expression_rows"):
        result["selected_expression_rows"] = _fallback_selected_expression_rows(days)
    for key in EXPECTED_KEYS:
        result.setdefault(key, [] if key != "warnings" else [])
    return result
