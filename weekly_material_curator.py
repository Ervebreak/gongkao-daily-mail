from __future__ import annotations

import json
import re
from html import unescape
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

MATERIAL_PROBLEM_KEYWORDS = {
    "问题",
    "矛盾",
    "痛点",
    "堵点",
    "风险",
    "乱象",
    "投诉",
    "纠纷",
    "隐患",
    "短板",
    "难题",
    "困境",
    "失灵",
}

MATERIAL_TRANSFER_KEYWORDS = {
    "可迁移",
    "迁移",
    "申论",
    "面试",
    "答题",
    "考场",
    "母题",
    "框架",
    "治理逻辑",
    "公共问题",
    "公共治理",
    "场景",
}

BROAD_USE_CASE_TERMS = {
    "基层治理",
    "公共服务",
    "民生保障",
    "社会治理",
    "公共治理",
    "治理能力",
    "治理现代化",
}

GENERIC_MATERIAL_THEMES = {
    "奋斗",
    "担当",
    "创新",
    "坚持",
    "服务",
    "治理",
    "落实",
    "作风",
    "能力",
    "发展",
    "群众路线",
    "基层治理",
    "公共服务",
    "社会治理",
    "民生保障",
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
    score += 6 if article.get("role") == "featured" else 2
    score += min(sum(1 for word in MATERIAL_TOPIC_KEYWORDS if word in text) * 4, 20)
    score += min(sum(1 for word in MATERIAL_SCENE_KEYWORDS if word in text) * 6, 30)
    score += min(sum(1 for word in MATERIAL_PROBLEM_KEYWORDS if word in text) * 6, 30)
    score += min(sum(1 for word in MATERIAL_MECHANISM_KEYWORDS if word in text) * 7, 35)
    score += min(sum(1 for word in MATERIAL_TRANSFER_KEYWORDS if word in text) * 6, 30)
    if re.search(r"困境|难题|问题|冲突|争议|痛点|堵点|风险|乱象|治理|整改|帮扶|维权", text):
        score += 12
    if re.search(r"某地|当地|部门|街道|社区|企业|平台|学校|医院|工地|市场|执法|检查", text):
        score += 10
    if article.get("role") == "quick_read" and score >= 45:
        score += 6
    if any(word in text for word in MACRO_THEORY_KEYWORDS):
        score -= 18
    if not any(word in text for word in MATERIAL_SCENE_KEYWORDS | MATERIAL_PROBLEM_KEYWORDS | MATERIAL_MECHANISM_KEYWORDS):
        score -= 18
    if not article.get("url"):
        score -= 8
    if len(text) < 30:
        score -= 6
    return score


def _material_mode_candidates(article: dict[str, Any]) -> list[dict[str, Any]]:
    text = _article_candidate_text(article)
    case_score = min(sum(1 for word in MATERIAL_SCENE_KEYWORDS | MATERIAL_PROBLEM_KEYWORDS if word in text) * 5, 45)
    mechanism_score = min(sum(1 for word in MATERIAL_MECHANISM_KEYWORDS if word in text) * 7, 49)
    expression_score = min(sum(1 for word in MATERIAL_TRANSFER_KEYWORDS | MATERIAL_TOPIC_KEYWORDS if word in text) * 4, 36)
    candidates = [
        {
            "mode": "case",
            "label": "具体案例型",
            "score": case_score + (8 if article.get("role") == "featured" else 0),
            "reason": "优先提炼具体场景、矛盾和对象，适合素材论证和综合分析。",
        },
        {
            "mode": "mechanism",
            "label": "治理路径型",
            "score": mechanism_score + (4 if any(word in text for word in MATERIAL_PROBLEM_KEYWORDS) else 0),
            "reason": "优先提炼机制做法、闭环动作和责任链条，适合对策题和治理路径表达。",
        },
        {
            "mode": "expression",
            "label": "可迁移表达型",
            "score": expression_score + (4 if article.get("role") == "quick_read" else 0),
            "reason": "优先提炼母题表达和治理逻辑，适合分论点、结尾升华和表达积累。",
        },
    ]
    ranked = [item for item in candidates if int(item.get("score") or 0) > 0]
    ranked.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
    return ranked[:3]


def _preferred_material_mode(article: dict[str, Any]) -> dict[str, Any]:
    modes = _material_mode_candidates(article)
    if not modes:
        return {
            "mode": "mechanism",
            "label": "治理路径型",
            "score": 0,
            "reason": "信息较少时默认优先提炼治理动作，避免把窄场景硬写成大案例。",
        }
    return modes[0]


def select_material_candidate_articles(days: list[dict[str, Any]], max_candidates: int = 6) -> list[dict[str, Any]]:
    """Select a small article set suitable for material-card evidence reading."""
    max_candidates = min(max(1, max_candidates), 6)
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
    return scored[:max_candidates]


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


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html or "")
    paragraph_texts = re.findall(r"(?is)<p[^>]*>(.*?)</p>", text)
    if paragraph_texts:
        chunks = paragraph_texts
    else:
        article_match = re.search(r"(?is)<article[^>]*>(.*?)</article>", text)
        content_match = re.search(r'(?is)<div[^>]+(?:class|id)=["\'][^"\']*(?:content|article|main|detail|正文)[^"\']*["\'][^>]*>(.*?)</div>', text)
        chunks = [article_match.group(1) if article_match else content_match.group(1)] if article_match or content_match else [text]
    cleaned: list[str] = []
    for chunk in chunks:
        chunk = re.sub(r"(?is)<br\s*/?>", "\n", chunk)
        chunk = re.sub(r"(?is)<[^>]+>", " ", chunk)
        chunk = unescape(chunk)
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if len(chunk) >= 25 and not re.search(r"责任编辑|版权|新华社客户端|扫一扫|客户端", chunk):
            cleaned.append(chunk)
    text = "\n".join(cleaned)
    if not text:
        text = re.sub(r"(?is)<[^>]+>", " ", html or "")
        text = re.sub(r"\s+", " ", unescape(text)).strip()
    return text


def _fetch_article_text_with_warning(url: str, max_chars: int = 1800) -> tuple[str, str]:
    url = _clean(url)
    if not url:
        return "", "skipped_no_url"
    try:
        import requests

        response = requests.get(url, timeout=12, headers={"User-Agent": USER_AGENT}, verify=False)
        if response.status_code in {403, 404}:
            return "", f"fetch_failed: http_{response.status_code}"
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = "utf-8"
        text = _clip_text(_html_to_text(response.text), max_chars)
        return text, "" if text else "fetch_empty"
    except Exception as exc:
        return "", f"fetch_failed: {type(exc).__name__}"


def fetch_article_text(url: str, max_chars: int = 1800) -> str:
    """Fetch and lightly clean article text; fail open with an empty string."""
    text, _warning = _fetch_article_text_with_warning(url, max_chars=max_chars)
    return text


def build_candidate_evidence(days: list[dict[str, Any]], max_candidates: int = 6) -> list[dict[str, Any]]:
    max_candidates = min(max(1, max_candidates), 6)
    candidates = select_material_candidate_articles(days, max_candidates=max_candidates)
    evidence_rows: list[dict[str, Any]] = []
    for article in candidates:
        evidence_text, warning = _fetch_article_text_with_warning(_clean(article.get("url")), max_chars=1800)
        preferred_mode = _preferred_material_mode(article) if settings.weekly_material_multi_candidate_enabled else {
            "mode": "mechanism",
            "label": "治理路径型",
            "score": 0,
            "reason": "weekly material multi candidate disabled",
        }
        mode_candidates = _material_mode_candidates(article) if settings.weekly_material_multi_candidate_enabled else []
        existing_summary = "；".join(
            item
            for item in [
                _clean(article.get("one_sentence")),
                _clean(article.get("exam_value")),
                _clean(article.get("day_focus")),
            ]
            if item
        )
        row = {
            "role": _clean(article.get("role")),
            "date": _clean(article.get("date")),
            "title": _clean(article.get("title")),
            "source": _clean(article.get("source")),
            "url": _clean(article.get("url")),
            "material_score": article.get("material_score"),
            "selection_reason": _clean(article.get("selection_reason")),
            "preferred_material_mode": preferred_mode.get("mode"),
            "preferred_material_mode_label": preferred_mode.get("label"),
            "preferred_material_mode_reason": preferred_mode.get("reason"),
            "material_mode_candidates": mode_candidates,
            "existing_summary": _clip_text(existing_summary, 500),
            "evidence_text": evidence_text,
        }
        if warning:
            row["warning"] = warning
        evidence_rows.append(row)
    return evidence_rows


def build_material_candidate_evidence(days: list[dict[str, Any]], max_candidates: int = 6) -> list[dict[str, Any]]:
    return build_candidate_evidence(days, max_candidates=max_candidates)


def _build_prompt(days: list[dict[str, Any]], candidate_evidence: list[dict[str, Any]] | None = None) -> str:
    candidate_evidence = candidate_evidence if candidate_evidence is not None else build_candidate_evidence(days)
    return f"""
你是公考周末复盘资料包编辑。请只基于输入的本周结构化摘要和候选文章证据生成周报增强数据。

硬性规则：
1. 只使用输入 JSON 中已有信息，不得编造外部事实、政策、案例、数字、地名、部门名。
2. material_cards 只能从 candidate_evidence 中提炼，优先使用 evidence_text 中出现的事实锚点或机制做法。
2.1 如果 candidate_evidence 提供 preferred_material_mode 或 material_mode_candidates，请优先沿着最适合考场迁移的那条线提炼，不要把同一篇文章同时写成冗长案例、机制和表达三种版本。
3. 不要推测未提供的文章全文；输入中没有的事实不要补。
4. 对策建议题不要硬塞外部案例。
5. 所有句子必须完整，不得出现省略号、半截句、悬空动词或未完成判断。
6. 只输出合法 JSON 对象，不要输出解释。
7. 如果候选文章证据不足，material_cards 可以少于 3 条或为空。
8. 如果某篇 candidate_evidence 没有 evidence_text，不得基于它生成“案例型”素材；只有 existing_summary 或 selection_reason 中有明确机制做法时，才可生成“机制型”素材。
9. material_cards 的 source_articles 和 source_urls 必须能对应到 candidate_evidence 中的 title 和 url。
10. material_cards 不能只写成某一篇文章专属案例，必须从具体事实中抽象出可迁移的公考母题、治理逻辑和通用考场写法。
11. practice_questions 的三道题都必须可直接训练，不得出现空的作答提示或空的考生版参考答案。
12. practice_questions 是唯一的训练题输出容器，不要额外生成“金句小练习”“表达练习”等字段或结构，避免形成 3 个金句练习 + 3 道训练题。
13. 每道 practice_questions 都必须绑定至少 1 句本次 selected_expression_rows 中的金句或表达，suggested_golden_sentences 必须逐字引用 selected_expression_rows[*].sentence。
14. 每道题的 answer_hint 或 mini_reference_answer 必须自然示范这句金句如何嵌入作答，不能只把金句列在 suggested_golden_sentences 里。
15. 对策建议题不强行塞案例，但必须给出可迁移治理动作或政策表达，例如清单管理、分级分类、协同联动、闭环反馈、依法监管、精准服务等。

输出字段：
{{
  "exam_map_cards": [
    {{"title": "4到12字考点名", "summary": "完整短句，说明本周为什么高频", "use_for": "适用题型或场景", "keywords": ["关键词"]}}
  ],
  "selected_expression_rows": [
    {{"date": "日期", "theme": "主题", "sentence": "精选金句或可用表达", "scenario": "适用场景"}}
  ],
  "material_cards": [
    {{"title": "素材卡标题", "material_type": "案例型 / 机制型 / 案例型+机制型", "source_dates": ["日期"], "source_articles": ["来源文章标题"], "source_urls": ["来源文章URL"], "target_topics": ["适用考点"], "core_topic": "抽象母题，如公共服务从有到优", "generalizable_logic": "可迁移治理逻辑", "factual_anchor": "事实锚点或机制做法", "material_summary": "100到180字的素材简介，要说明来源、基本事实和事实边界", "usage_examples": [{{"theme": "具体申论/面试主题", "example": "120到220字的考场表达示例"}}, {{"theme": "另一具体主题", "example": "120到220字的考场表达示例"}}], "exam_paragraph": "默认考场表达，可与具体写法一致", "exam_paragraph_specific": "保留具体事实的考场写法", "exam_paragraph_general": "脱离具体案例也能迁移使用的通用写法", "can_use_for": ["3到5个具体适用场景"], "suggested_question_types": ["适用题型"], "not_suitable_for": ["不适合使用的场景"], "memory_sentence": "一句话记忆", "use_tip": "用法提示", "use_boundary": "使用边界"}}
  ],
  "practice_questions": [
    {{"title": "题目标题", "question_type": "面试综合分析题", "question": "题目", "target_topics": ["训练主题"], "suggested_golden_sentences": ["建议金句"], "suggested_case_materials": ["至少1条素材卡标题"], "suggested_policy_expressions": ["政策表达"], "answer_hint": "作答提示", "mini_reference_answer": "考生版参考答案", "use_boundary": "使用边界"}},
    {{"title": "题目标题", "question_type": "对策建议题", "question": "题目", "target_topics": ["训练主题"], "suggested_golden_sentences": ["建议金句"], "suggested_case_materials": [], "suggested_policy_expressions": ["至少1条政策表达"], "answer_hint": "作答提示", "mini_reference_answer": "考生版参考答案", "use_boundary": "本题重点是措施表达，不建议硬塞外部案例。"}},
    {{"title": "题目标题", "question_type": "申论作文分论点展开题", "question": "题目", "target_topics": ["训练主题"], "suggested_golden_sentences": ["建议金句"], "suggested_case_materials": ["至少1条素材卡标题"], "suggested_policy_expressions": ["政策表达"], "answer_hint": "作答提示", "mini_reference_answer": "考生版参考答案", "use_boundary": "使用边界"}}
  ],
  "warnings": ["无法处理或字段不足的说明"]
}}

数量要求：
- exam_map_cards：4到6个。
- selected_expression_rows：8到15条。
- material_cards：目标 2 到 3 条，最多 3 条；如果只有 1 个合格素材就只输出 1 条；如果没有合格素材就输出空数组；不要为了凑数强行补齐。
- material_cards 每条必须尽量补全 core_topic、generalizable_logic、exam_paragraph_specific、exam_paragraph_general、can_use_for、suggested_question_types、not_suitable_for。
- material_cards 每条必须明确包含 material_summary 和 usage_examples；usage_examples 每条都必须包含 theme 和 example，每个素材 2 到 3 个 usage_examples。
- can_use_for 填 3 到 5 个具体适用场景，不能只写“基层治理、公共服务、民生保障”这类大而空标签；exam_paragraph_general 必须能迁移到同类题目，不能依赖原文专属细节。
- usage_examples[*].theme 不能只写“奋斗、担当、创新、基层治理、公共服务”等空泛词，必须是可用于申论/面试表达的具体主题。
- usage_examples[*].example 必须像考场表达，不能写成小红书鸡汤文或营销文案。
- 宁缺毋滥，不允许为了凑数生成硬拼的素材卡或示例。
- practice_questions：严格3道，题型分别为面试综合分析题、对策建议题、申论作文分论点展开题。
- practice_questions 每题必须有 answer_hint 和 mini_reference_answer。
- practice_questions 每题必须绑定至少 1 条 selected_expression_rows 中的原句，且 answer_hint 或 mini_reference_answer 要示范“这句金句如何放进答案里”。
- 对策建议题 suggested_case_materials 可以为空，但 suggested_policy_expressions 不能为空，use_boundary 必须提醒“本题重点是措施表达，不建议硬塞外部案例。”
- 面试综合分析题和申论作文分论点展开题必须至少关联 1 条素材卡和 1 条金句。
- 不要把金句单独拆成小练习；只能生成上述 3 道 practice_questions。

Material card selection rules:
- Featured articles are preferred only as a small prior. Quick reads must compete on usefulness and may win if they have clearer governance scenes, public conflicts, mechanisms, reusable frameworks, or exam-ready expression.
- Do not let role=featured override weak material value. Drop narrow featured-only facts when a quick_read offers a more generalizable exam material.
- Each material_card must include concrete factual writing and general exam writing: core_topic, generalizable_logic, factual_anchor, exam_paragraph_specific, exam_paragraph_general, can_use_for, suggested_question_types, and use_boundary.
- can_use_for must contain 3 to 5 specific scenarios. Avoid broad empty labels such as 基层治理, 公共服务, 民生保障 unless they are attached to a concrete situation.
- If a card only repeats the source article and cannot become a reusable public-governance motif, lower its priority or omit it.
- practice_questions must remain exactly 3. Do not add golden-sentence mini-practice or any extra practice container.

输入 JSON：
{json.dumps({"days": _compact_days(days), "candidate_evidence": candidate_evidence}, ensure_ascii=False)}
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


def _has_terminal_sentence_end(text: str) -> bool:
    text = _clean(text)
    if not text:
        return False
    return bool(re.search(r'[。！？!?][”’"）】》」』]*\s*$', text))


def _clip_complete_sentence(text: str, limit: int) -> str:
    text = _clean(text)
    if not text:
        return ""
    upper = min(len(text), limit)
    if upper == len(text) and _is_complete_sentence(text) and _has_terminal_sentence_end(text):
        return text
    window = text[:upper]
    matches = list(re.finditer(r'[。！？!?][”’"）】》」』]*', window))
    for match in reversed(matches):
        candidate = window[: match.end()].strip()
        if len(candidate) >= max(60, upper // 2) and _is_complete_sentence(candidate) and _has_terminal_sentence_end(candidate):
            return candidate
    return ""


def _valid_text_map(row: Any, required: list[str]) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    result = {key: _clean(row.get(key)) for key in required}
    if not all(result.values()):
        return None
    if any(not _is_complete_sentence(value) for value in result.values() if len(value) >= 18):
        return None
    return result


def _candidate_evidence_index(candidate_evidence: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in candidate_evidence or []:
        if not isinstance(row, dict):
            continue
        for key in (_clean(row.get("title")), _clean(row.get("url"))):
            if key:
                index[key] = row
    return index


def _material_sources_have_evidence(source_articles: list[str], source_urls: list[str], evidence_index: dict[str, dict[str, Any]]) -> bool:
    for key in source_articles + source_urls:
        row = evidence_index.get(_clean(key))
        if row and _clean(row.get("evidence_text")):
            return True
    return False


def _is_broad_use_case(text: str) -> bool:
    text = _clean(text)
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    if compact in BROAD_USE_CASE_TERMS:
        return True
    return len(compact) <= 6 and any(term in compact for term in BROAD_USE_CASE_TERMS)


def _specific_use_cases(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        value = _clean(value)
        if not value or _is_broad_use_case(value):
            continue
        if value not in result:
            result.append(value)
    return result[:5]


def _is_generic_material_theme(text: str) -> bool:
    text = _clean(text)
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    if compact in GENERIC_MATERIAL_THEMES:
        return True
    return len(compact) <= 8 and any(term in compact for term in GENERIC_MATERIAL_THEMES)


def _normalize_material_summary(item: dict[str, Any], factual_anchor: str, generalizable_logic: str) -> str:
    summary = _clean(item.get("material_summary") or item.get("summary") or item.get("material_intro"))
    if summary:
        return summary
    parts = [part for part in [factual_anchor, generalizable_logic] if part]
    return " ".join(parts[:2]).strip()


def _normalize_usage_examples(item: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    has_explicit_examples = any(key in item for key in ("usage_examples", "theme_examples", "examples"))
    raw_examples = _as_list(item.get("usage_examples") or item.get("theme_examples") or item.get("examples"))
    for raw in raw_examples:
        if not isinstance(raw, dict):
            continue
        theme = _clean(raw.get("theme") or raw.get("title") or raw.get("topic"))
        example = _clean(raw.get("example") or raw.get("content") or raw.get("body") or raw.get("sample"))
        if not theme or not example:
            continue
        rows.append({"theme": theme, "example": example})
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["theme"], row["example"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    if deduped:
        return deduped[:3]
    if has_explicit_examples:
        return []

    fallback_themes = _specific_use_cases([_clean(x) for x in _as_list(item.get("can_use_for")) if _clean(x)])
    if not fallback_themes:
        fallback_themes = [_clean(x) for x in _as_list(item.get("target_topics") or item.get("theme")) if _clean(x)]
    anchor = _clean(item.get("factual_anchor") or item.get("anchor"))
    general = _clean(item.get("exam_paragraph_general") or item.get("exam_paragraph") or item.get("exam_value"))
    specific = _clean(item.get("exam_paragraph_specific"))
    for theme in fallback_themes[:3]:
        if not theme or not general:
            continue
        example = f"写“{theme}”这类题时，可以先点出{anchor or '这类治理场景'}，再顺势说明{general}"
        if specific:
            example = f"{example}。如果需要更贴近材料，还可以补上一句：{specific}"
        deduped.append({"theme": theme, "example": example})
    return deduped[:3]


def _too_close_to_source_only(general_text: str, *source_texts: str) -> bool:
    general = re.sub(r"\s+", "", _clean(general_text))
    if len(general) < 20:
        return True
    for source in source_texts:
        source = re.sub(r"\s+", "", _clean(source))
        if source and (general == source or general in source or source in general):
            return True
    return False


def _golden_sentence_matches(suggested: list[str], selected_rows: list[dict[str, str]]) -> list[str]:
    selected = [_clean(row.get("sentence")) for row in selected_rows if _clean(row.get("sentence"))]
    if not selected:
        return suggested
    matched: list[str] = []
    for sentence in suggested:
        sentence = _clean(sentence)
        if not sentence:
            continue
        if any(sentence == item or sentence in item or item in sentence for item in selected):
            matched.append(sentence)
    return matched


def _question_demonstrates_golden(suggested: list[str], answer_hint: str, mini_reference_answer: str) -> bool:
    body = f"{_clean(answer_hint)} {_clean(mini_reference_answer)}"
    if not suggested:
        return False
    for sentence in suggested:
        sentence = _clean(sentence)
        if not sentence:
            continue
        if sentence in body:
            return True
        compact = re.sub(r"\s+", "", sentence)
        body_compact = re.sub(r"\s+", "", body)
        if len(compact) >= 8 and compact[:8] in body_compact:
            return True
    return False


def _validate_usage_examples(
    usage_examples: list[dict[str, str]],
    source_name: str,
    warnings: list[str],
) -> list[dict[str, str]]:
    valid_rows: list[dict[str, str]] = []
    for row in usage_examples:
        theme = _clean(row.get("theme"))
        example = _clean(row.get("example"))
        if not theme or not example:
            continue
        if _is_generic_material_theme(theme):
            warnings.append(f"drop material card with generic theme: {source_name}")
            return []
        if len(theme) > 24:
            warnings.append(f"drop material card with overlong theme: {source_name}")
            return []
        if len(example) < 60:
            warnings.append(f"drop material card with weak usage example: {source_name}")
            return []
        if len(example) > 320:
            example = _clip_complete_sentence(example, 320)
            if not example:
                warnings.append(f"drop material card with overlong non-closable usage example: {source_name}")
                return []
        elif not _has_terminal_sentence_end(example):
            example = _clip_complete_sentence(example, len(example))
            if not example:
                warnings.append(f"drop material card with incomplete usage example: {source_name}")
                return []
        if not _is_complete_sentence(example) or not _has_terminal_sentence_end(example):
            warnings.append(f"drop material card with incomplete usage example: {source_name}")
            return []
        valid_rows.append({"theme": theme, "example": example})
    return valid_rows[:3]


def _validate_enrichment(payload: dict[str, Any], candidate_evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    warnings = [_clean(item) for item in _as_list(payload.get("warnings")) if _clean(item)]
    evidence_index = _candidate_evidence_index(candidate_evidence)

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

    material_cards: list[dict[str, Any]] = []
    material_type_aliases = {
        "case": "案例型",
        "mechanism": "机制型",
        "case+mechanism": "案例型+机制型",
        "案例": "案例型",
        "机制": "机制型",
        "案例机制": "案例型+机制型",
    }
    valid_material_types = {"案例型", "机制型", "案例型+机制型"}
    for item in _as_list(payload.get("material_cards")):
        if not isinstance(item, dict):
            continue
        raw_material_type = _clean(item.get("material_type") or item.get("type"))
        material_type = material_type_aliases.get(raw_material_type, raw_material_type)
        factual_anchor = _clean(item.get("factual_anchor") or item.get("anchor"))
        exam_paragraph_specific = _clean(item.get("exam_paragraph_specific"))
        exam_paragraph_general = _clean(item.get("exam_paragraph_general"))
        exam_paragraph = _clean(item.get("exam_paragraph") or item.get("exam_value") or exam_paragraph_specific or exam_paragraph_general)
        material_summary = _normalize_material_summary(item, factual_anchor, _clean(item.get("generalizable_logic")))
        source_title = _clean(item.get("source_title"))
        source_articles = [_clean(x) for x in _as_list(item.get("source_articles") or source_title) if _clean(x)]
        source_urls = [_clean(x) for x in _as_list(item.get("source_urls") or item.get("source_url") or item.get("url")) if _clean(x)]
        source_dates = [_clean(x) for x in _as_list(item.get("source_dates") or item.get("date")) if _clean(x)]
        target_topics = [_clean(x) for x in _as_list(item.get("target_topics") or item.get("theme")) if _clean(x)]
        core_topic = _clean(item.get("core_topic"))
        generalizable_logic = _clean(item.get("generalizable_logic"))
        can_use_for = _specific_use_cases([_clean(x) for x in _as_list(item.get("can_use_for")) if _clean(x)])
        suggested_question_types = [_clean(x) for x in _as_list(item.get("suggested_question_types")) if _clean(x)]
        not_suitable_for = [_clean(x) for x in _as_list(item.get("not_suitable_for")) if _clean(x)]
        usage_examples = _validate_usage_examples(_normalize_usage_examples(item), source_articles[0] if source_articles else "unknown", warnings)
        use_boundary = _clean(item.get("use_boundary"))
        if material_type not in valid_material_types or not factual_anchor or not exam_paragraph or not source_articles:
            continue
        if not all([core_topic, generalizable_logic, exam_paragraph_general, suggested_question_types, use_boundary]):
            warnings.append(f"drop material card missing reusable exam fields: {source_articles[0]}")
            continue
        if not material_summary:
            warnings.append(f"drop material card missing summary: {source_articles[0]}")
            continue
        if len(material_summary) < 60:
            warnings.append(f"drop material card with thin summary: {source_articles[0]}")
            continue
        if len(usage_examples) < 2:
            warnings.append(f"drop material card missing reusable usage examples: {source_articles[0]}")
            continue
        if len(can_use_for) < 3:
            warnings.append(f"drop material card with vague can_use_for: {source_articles[0]}")
            continue
        if _too_close_to_source_only(exam_paragraph_general, factual_anchor, exam_paragraph_specific):
            warnings.append(f"drop material card without general exam expression: {source_articles[0]}")
            continue
        if "案例型" in material_type and not _material_sources_have_evidence(source_articles, source_urls, evidence_index):
            warnings.append(f"drop material card without source evidence_text: {source_articles[0]}")
            continue
        text_values = [
            _clean(item.get("title")),
            factual_anchor,
            exam_paragraph,
            core_topic,
            generalizable_logic,
            exam_paragraph_specific,
            exam_paragraph_general,
            material_summary,
            _clean(item.get("memory_sentence")),
            _clean(item.get("use_tip")),
            use_boundary,
            *[row["example"] for row in usage_examples],
        ]
        if any(value and len(value) >= 18 and not _is_complete_sentence(value) for value in text_values):
            continue
        material_cards.append(
            {
                "title": _clean(item.get("title")) or source_articles[0],
                "material_type": material_type,
                "source_dates": source_dates,
                "source_articles": source_articles,
                "source_urls": source_urls,
                "target_topics": target_topics,
                "core_topic": core_topic,
                "generalizable_logic": generalizable_logic,
                "factual_anchor": factual_anchor,
                "material_summary": material_summary,
                "usage_examples": usage_examples,
                "exam_paragraph": exam_paragraph,
                "exam_paragraph_specific": exam_paragraph_specific,
                "exam_paragraph_general": exam_paragraph_general,
                "can_use_for": can_use_for[:5],
                "suggested_question_types": suggested_question_types[:5],
                "not_suitable_for": not_suitable_for[:5],
                "memory_sentence": _clean(item.get("memory_sentence")),
                "use_tip": _clean(item.get("use_tip")),
                "use_boundary": use_boundary,
                # Backward-compatible aliases used by older renderers/tests.
                "date": "、".join(source_dates),
                "theme": "、".join(target_topics),
                "type": material_type,
                "anchor": factual_anchor,
                "exam_value": exam_paragraph,
                "source_title": source_articles[0],
                "source_url": source_urls[0] if source_urls else "",
            }
        )

    practice_questions: list[dict[str, Any]] = []
    allowed_types = ["面试综合分析题", "对策建议题", "申论作文分论点展开题"]
    seen_types: set[str] = set()
    for item in _as_list(payload.get("practice_questions")):
        if not isinstance(item, dict):
            continue
        question_type = _clean(item.get("question_type"))
        question = _clean(item.get("question"))
        answer_hint = _clean(item.get("answer_hint") or item.get("use_hint"))
        mini_reference_answer = _clean(item.get("mini_reference_answer"))
        if not all([question_type, question, answer_hint, mini_reference_answer]):
            continue
        if question_type not in allowed_types or question_type in seen_types:
            continue
        target_topics = [_clean(x) for x in _as_list(item.get("target_topics")) if _clean(x)]
        suggested_golden_sentences = [_clean(x) for x in _as_list(item.get("suggested_golden_sentences")) if _clean(x)]
        suggested_case_materials = [_clean(x) for x in _as_list(item.get("suggested_case_materials")) if _clean(x)]
        suggested_policy_expressions = [_clean(x) for x in _as_list(item.get("suggested_policy_expressions")) if _clean(x)]
        use_boundary = _clean(item.get("use_boundary"))
        suggested_golden_sentences = _golden_sentence_matches(suggested_golden_sentences, selected_expression_rows)
        if not suggested_golden_sentences:
            warnings.append(f"drop practice question without selected golden sentence: {question_type}")
            continue
        if not _question_demonstrates_golden(suggested_golden_sentences, answer_hint, mini_reference_answer):
            warnings.append(f"drop practice question without golden sentence demonstration: {question_type}")
            continue
        if question_type == "对策建议题":
            if not suggested_policy_expressions:
                continue
            if "不建议硬塞外部案例" not in use_boundary:
                use_boundary = "本题重点是措施表达，不建议硬塞外部案例。"
        else:
            if not suggested_golden_sentences or not suggested_case_materials:
                continue
        text_values = [
            _clean(item.get("title")),
            question,
            answer_hint,
            mini_reference_answer,
            use_boundary,
            *suggested_golden_sentences,
            *suggested_policy_expressions,
        ]
        if any(value and len(value) >= 18 and not _is_complete_sentence(value) for value in text_values):
            continue
        seen_types.add(question_type)
        practice_questions.append(
            {
                "title": _clean(item.get("title")) or question_type,
                "question_type": question_type,
                "question": question,
                "target_topics": target_topics,
                "suggested_golden_sentences": suggested_golden_sentences,
                "suggested_case_materials": suggested_case_materials,
                "suggested_policy_expressions": suggested_policy_expressions,
                "answer_hint": answer_hint,
                "mini_reference_answer": mini_reference_answer,
                "use_boundary": use_boundary,
                "use_hint": answer_hint,
            }
        )

    if len(exam_map_cards) < 4:
        warnings.append("weekly enrichment returned fewer than 4 exam_map_cards")
    if len(selected_expression_rows) < 8:
        warnings.append("weekly enrichment returned fewer than 8 selected_expression_rows")
    if len(practice_questions) != 3:
        warnings.append("weekly enrichment did not return exactly 3 practice_questions")

    return {
        "exam_map_cards": exam_map_cards[:6],
        "selected_expression_rows": selected_expression_rows[:15],
        "material_cards": material_cards[:3],
        "practice_questions": practice_questions[:3],
        "warnings": warnings,
    }


def _call_curator_model(days: list[dict[str, Any]]) -> dict[str, Any]:
    from llm_client import chat_completion

    candidate_evidence = build_candidate_evidence(days)
    prompt = _build_prompt(days, candidate_evidence=candidate_evidence)
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
            return _validate_enrichment(response, candidate_evidence=candidate_evidence)
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
