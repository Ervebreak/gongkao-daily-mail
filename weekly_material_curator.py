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
            }
        )
    return compact


def _build_prompt(days: list[dict[str, Any]]) -> str:
    return f"""
你是公考周末复盘资料包编辑。请只基于输入的本周结构化摘要生成周报增强数据。

硬性规则：
1. 只使用输入 JSON 中已有信息，不得编造外部事实、政策、案例、数字、地名、部门名。
2. 不要读取或推测文章全文；输入中没有的事实不要补。
3. 素材卡优先案例型，其次机制型；没有具体案例或机制做法的文章，不要强行进入素材库。
4. 对策建议题不要硬塞外部案例。
5. 所有句子必须完整，不得出现省略号、半截句、悬空动词或未完成判断。
6. 只输出合法 JSON 对象，不要输出解释。

输出字段：
{{
  "exam_map_cards": [
    {{"title": "4到12字考点名", "summary": "完整短句，说明本周为什么高频", "use_for": "适用题型或场景", "keywords": ["关键词"]}}
  ],
  "selected_expression_rows": [
    {{"date": "日期", "theme": "主题", "sentence": "精选金句或可用表达", "scenario": "适用场景"}}
  ],
  "material_cards": [
    {{"date": "日期", "theme": "主题", "type": "case或mechanism", "anchor": "事实锚点或机制做法", "exam_value": "考场怎么用", "source_title": "来源文章标题"}}
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
{json.dumps({"days": _compact_days(days)}, ensure_ascii=False)}
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
        row = _valid_text_map(item, ["date", "theme", "type", "anchor", "exam_value", "source_title"])
        if row and row["type"] in {"case", "mechanism"}:
            material_cards.append(row)

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
