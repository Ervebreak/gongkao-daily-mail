from __future__ import annotations

import re
from typing import Any


STOPWORDS = {
    "今天",
    "今日",
    "文章",
    "全文",
    "作者",
    "指出",
    "强调",
    "认为",
    "问题",
    "治理",
    "价值",
    "导向",
    "考试",
    "迁移",
    "方面",
    "工作",
    "内容",
    "建设",
}

NEGATIVE_CUES = [
    "遮丑",
    "应付检查",
    "应付考核",
    "面子工程",
    "重面子轻里子",
    "形式主义",
    "走过场",
    "摆样子",
    "只做表面文章",
    "掩盖问题",
    "虚假整改",
    "敷衍整改",
    "层层加码",
    "留痕",
    "只求过关",
]

POSITIVE_CUES = [
    "揭丑",
    "群众评判",
    "群众监督",
    "公开透明",
    "问题导向",
    "实事求是",
    "系统治理",
    "闭环治理",
    "长效机制",
    "真效果",
    "真实成效",
    "里子",
    "整改到位",
]

GOVERNANCE_CUES = [
    "系统治理",
    "闭环治理",
    "长效机制",
    "问题导向",
    "群众监督",
    "公开透明",
    "压实责任",
    "协同治理",
    "标本兼治",
    "源头治理",
    "机制约束",
    "整改",
    "反馈",
]

VALUE_CUES = [
    "群众",
    "实效",
    "里子",
    "公开",
    "透明",
    "真实",
    "人民",
    "公平",
    "务实",
    "基层",
]

EXAM_CUES = [
    "申论",
    "面试",
    "作风建设",
    "基层治理",
    "问题整改",
    "监督问效",
]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    if isinstance(value, dict):
        return " ".join(part for part in (_text(item) for item in value.values()) if part).strip()
    if isinstance(value, (list, tuple, set)):
        return " ".join(part for part in (_text(item) for item in value) if part).strip()
    return " ".join(str(value).split()).strip()


def _list_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, dict):
        return [part for part in (_text(item) for item in value.values()) if part]
    if isinstance(value, (list, tuple, set)):
        return [part for part in (_text(item) for item in value) if part]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(items: list[str], limit: int | None = None) -> list[str]:
    result: list[str] = []
    for item in items:
        text = _text(item)
        if not text or text in result:
            continue
        result.append(text)
        if limit and len(result) >= limit:
            break
    return result


def _clip(text: Any, limit: int) -> str:
    normalized = _text(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip("，。；、 ") + "..."


def _brief_fallback_text(brief: dict[str, Any] | None) -> str:
    brief = brief if isinstance(brief, dict) else {}
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    takeaway = brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}
    segments = [
        brief.get("today_theme"),
        brief.get("today_focus"),
        brief.get("email_subject"),
        featured.get("title"),
        featured.get("one_sentence"),
        featured.get("core_viewpoint"),
        featured.get("main_thread"),
        featured.get("original_overview"),
        featured.get("article_framework"),
        featured.get("exam_use"),
        featured.get("usable_for_exam"),
        question.get("question"),
        question.get("exam_focus"),
        question.get("answer_framework"),
        takeaway.get("keywords"),
        takeaway.get("framework"),
    ]
    return _text(segments)


def resolve_policy_profile_text(article_full_text: Any = "", brief: dict[str, Any] | None = None) -> tuple[str, str]:
    full_text = _text(article_full_text)
    if full_text:
        return full_text, "full_text"
    return _brief_fallback_text(brief), "brief_fallback"


def _split_sentences(text: str) -> list[str]:
    normalized = _text(text).replace("\n", " ")
    rows = re.split(r"(?<=[。！？；!?])\s*|(?<=\.)\s{2,}", normalized)
    return [row.strip(" 。；") for row in rows if row.strip(" 。；")]


def _compact_sentence(sentence: str, limit: int = 100) -> str:
    sentence = _text(sentence)
    if not sentence:
        return ""
    sentence = sentence.rstrip("。；")
    if len(sentence) <= limit:
        return sentence
    return sentence[:limit].rstrip("，。；、 ") + "..."


def _best_sentence(sentences: list[str], cues: list[str]) -> str:
    best = ""
    best_score = -1
    for sentence in sentences:
        score = sum(1 for cue in cues if cue and cue in sentence)
        if score <= 0:
            continue
        if score > best_score or (score == best_score and (not best or len(sentence) < len(best))):
            best = sentence
            best_score = score
    return _compact_sentence(best, 100)


def _extract_quoted_terms(title: str, text: str) -> list[str]:
    combined = f"{_text(title)} {_text(text)}"
    terms = re.findall(r"[“\"《](.{2,12}?)[”\"》]", combined)
    return _dedupe([item for item in terms if item not in STOPWORDS], limit=8)


def _extract_regex_anchors(text: str) -> list[str]:
    normalized = _text(text)
    hits: list[str] = []
    patterns = [
        r"[\u4e00-\u9fff]{2,8}/[\u4e00-\u9fff]{2,8}",
        r"[\u4e00-\u9fff]{2,8}何以变[\u4e00-\u9fff]{2,8}",
        r"重[\u4e00-\u9fff]{1,6}轻[\u4e00-\u9fff]{1,6}",
        r"[\u4e00-\u9fff]{2,8}工程",
        r"[\u4e00-\u9fff]{2,8}检查",
        r"[\u4e00-\u9fff]{2,8}评判",
        r"[\u4e00-\u9fff]{2,8}治理",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, normalized):
            if match not in hits:
                hits.append(match)
    return hits


def _extract_keyword_hits(text: str, vocabulary: list[str]) -> list[str]:
    normalized = _text(text)
    return [word for word in vocabulary if word and word in normalized]


def _compact_word_candidates(*values: Any, limit: int = 10) -> list[str]:
    normalized = _text(values)
    candidates = re.findall(r"[\u4e00-\u9fff]{2,10}", normalized)
    result: list[str] = []
    for item in candidates:
        if item in STOPWORDS or item in result:
            continue
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _fallback_problem(title: str, negative_behaviors: list[str], anchors: list[str]) -> str:
    if negative_behaviors:
        return f"文章聚焦{'、'.join(negative_behaviors[:3])}等现象，追问表面整改为何难以转化为真实治理成效"
    if anchors:
        return f"文章围绕{anchors[0]}等治理偏差，追问问题为什么会从个别现象演化成系统性顽疾"
    return f"文章围绕《{title or '今日文章'}》揭示的治理偏差，追问表面应对为何替代了真正整改"


def _fallback_governance(positive_behaviors: list[str], anchors: list[str]) -> str:
    lead = positive_behaviors[:2] or anchors[:2]
    if lead:
        return f"文章强调从{'、'.join(lead)}出发，把整改拉回问题导向、群众评判和系统治理的闭环上"
    return "文章强调把整改拉回问题导向、公开监督和系统治理，避免只看表面动作不看真实成效"


def _fallback_value(text: str) -> str:
    normalized = _text(text)
    if "群众" in normalized or "人民" in normalized:
        return "文章强调以群众感受和群众评判作为衡量整改成效的重要标尺"
    if "里子" in normalized:
        return "文章强调不能只看面子和声势，而要把治理成效落到群众真正能感知的里子上"
    return "文章强调用真实成效、问题导向和公开监督校准治理方向"


def _build_queries(
    article_title: str,
    article_source: str,
    profile: dict[str, Any],
) -> list[str]:
    fine_anchors = _list_text(profile.get("fine_anchors"))
    negative_behaviors = _list_text(profile.get("negative_behaviors"))
    positive_behaviors = _list_text(profile.get("positive_behaviors"))
    governance_logic = _text(profile.get("governance_logic"))
    value_orientation = _text(profile.get("value_orientation"))
    title_query = _clip(" ".join(_dedupe([article_title] + fine_anchors[:2], limit=3)), 48)
    problem_query = _clip(" ".join(_dedupe(negative_behaviors[:3] or [profile.get("core_problem")], limit=3)), 48)
    value_query = _clip(" ".join(_dedupe(positive_behaviors[:2] + _compact_word_candidates(value_orientation, limit=2), limit=4)), 48)
    governance_query = _clip(" ".join(_dedupe(_compact_word_candidates(governance_logic, limit=3) + fine_anchors[:2], limit=4)), 48)
    exam_query = _clip("申论 面试 " + " ".join(_dedupe(fine_anchors[:3] or EXAM_CUES[:2], limit=3)), 48)
    source_query = _clip(" ".join(_dedupe([article_source, article_title] + fine_anchors[:1], limit=3)), 48)
    return _dedupe([title_query, problem_query, value_query, governance_query, exam_query, source_query], limit=6)


def build_policy_profile(
    article_title: str,
    article_source: str,
    article_full_text: Any = "",
    brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_text, _ = resolve_policy_profile_text(article_full_text, brief)
    title = _text(article_title)
    source = _text(article_source)
    sentences = _split_sentences(source_text)

    quoted_terms = _extract_quoted_terms(title, source_text)
    keyword_anchors = _extract_keyword_hits(source_text, NEGATIVE_CUES + POSITIVE_CUES + GOVERNANCE_CUES)
    regex_anchors = _extract_regex_anchors(f"{title} {source_text}")
    fine_anchors = _dedupe(
        regex_anchors + quoted_terms + keyword_anchors + _compact_word_candidates(title, limit=4),
        limit=10,
    )

    negative_behaviors = _dedupe(
        _extract_keyword_hits(source_text, NEGATIVE_CUES) + [item for item in fine_anchors if item in NEGATIVE_CUES or "工程" in item],
        limit=6,
    )
    positive_behaviors = _dedupe(
        _extract_keyword_hits(source_text, POSITIVE_CUES) + [item for item in fine_anchors if item in POSITIVE_CUES or "治理" in item],
        limit=6,
    )

    core_problem = _best_sentence(sentences, NEGATIVE_CUES) or _fallback_problem(title, negative_behaviors, fine_anchors)
    governance_logic = _best_sentence(sentences, GOVERNANCE_CUES + POSITIVE_CUES) or _fallback_governance(positive_behaviors, fine_anchors)
    value_orientation = _best_sentence(sentences, VALUE_CUES + POSITIVE_CUES) or _fallback_value(source_text)

    profile = {
        "core_problem": _clip(core_problem, 120),
        "governance_logic": _clip(governance_logic, 120),
        "value_orientation": _clip(value_orientation, 120),
        "negative_behaviors": negative_behaviors[:6],
        "positive_behaviors": positive_behaviors[:6],
        "fine_anchors": fine_anchors[:10],
        "retrieval_queries": [],
    }
    profile["retrieval_queries"] = _build_queries(title, source, profile)
    return profile
