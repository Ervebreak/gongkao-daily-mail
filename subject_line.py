from __future__ import annotations

import re
from typing import Any


HYPE_WORDS = (
    "必考",
    "押题",
    "上岸",
    "不看后悔",
    "一定会考",
    "稳了",
    "包过",
)

EXAM_VALUE_MARKERS = (
    "高频考点",
    "常考场景",
    "申论素材",
    "面试常见题",
    "机关实务题",
    "今日带走",
    "答题角度",
    "政策坐标",
    "怎么答",
    "怎么写",
    "怎么用",
)

GENERIC_SUBJECTS = {
    "基层治理",
    "公共服务",
    "高质量发展",
    "生态文明",
    "政策落实",
    "数字治理",
    "青年奋斗",
    "民生保障",
}

GENERIC_TOPIC_WORDS = (
    "今日热点",
    "今日主题",
    "今天主题",
    "晨读主题",
    "晨读文章",
    "今日晨读",
    "热点解读",
    "热点话题",
    "主题学习",
)

WEAK_TOPIC_PREFIXES = (
    "关于",
    "围绕",
    "聚焦",
    "推进",
    "做好",
    "加强",
    "深化",
    "完善",
    "推动",
    "学习",
)

WEAK_ENDINGS = "，。、：:；;（）()[]【】《》“”\"' "


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _get_nested(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def strip_subject_prefix(subject: str) -> str:
    text = _clean_text(subject)
    if not text:
        return ""
    pattern = re.compile(
        r"^(?:(?:\[\s*公考晨读\s*\]|【公考晨读】|公考晨读|RE:|Re:|re:|FW:|Fw:|fw:|FWD:|Fwd:|fwd:)\s*[-:： ]*)+",
        flags=re.IGNORECASE,
    )
    previous = None
    while text and text != previous:
        previous = text
        text = pattern.sub("", text).strip()
    return text.lstrip(" -:：")


def has_hype_word(subject: str) -> bool:
    text = _clean_text(subject)
    return any(word in text for word in HYPE_WORDS)


def has_exam_value_marker(subject: str) -> bool:
    text = _clean_text(subject)
    return any(word in text for word in EXAM_VALUE_MARKERS)


def is_generic_subject(subject: str) -> bool:
    text = strip_subject_prefix(subject)
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    if not compact:
        return True
    if compact in GENERIC_SUBJECTS:
        return True
    if len(compact) <= 8 and not has_exam_value_marker(text):
        return True
    return False


def _normalize_topic_candidate(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = strip_subject_prefix(text)
    for generic_word in GENERIC_TOPIC_WORDS:
        text = text.replace(generic_word, "")
    text = re.sub(r"^(?:今天|今日|本期|本篇)", "", text).strip()
    for prefix in WEAK_TOPIC_PREFIXES:
        if text.startswith(prefix) and len(text) - len(prefix) >= 4:
            text = text[len(prefix):].strip()
            break
    text = re.split(r"[｜|/\-—_:：，。；;、（）()【】《》\[\]]", text)[0].strip()
    text = text.strip(WEAK_ENDINGS)
    if len(text) > 12:
        text = text[:12].rstrip(WEAK_ENDINGS + "和与及的")
    if len(text) < 2:
        return ""
    return text


def _pick_topic_from_brief(brief: dict) -> str:
    candidates: list[Any] = []
    candidates.extend(_as_list(_get_nested(brief, "daily_question", "upper_exam_points"))[:1])
    candidates.extend(_as_list(_get_nested(brief, "featured_article", "article_framework_map", "exam_tags"))[:1])
    candidates.append(_get_nested(brief, "featured_article", "theme"))
    candidates.append(brief.get("today_theme"))
    candidates.append(_get_nested(brief, "featured_article", "title"))
    for candidate in candidates:
        topic = _normalize_topic_candidate(candidate)
        if topic:
            return topic
    return "基层治理"


def build_subject_from_brief(brief: dict) -> str:
    topic = _pick_topic_from_brief(brief)
    question_type = _clean_text(_get_nested(brief, "daily_question", "question_type"))
    upper_points = _as_list(_get_nested(brief, "daily_question", "upper_exam_points"))
    exam_tags = _as_list(_get_nested(brief, "featured_article", "article_framework_map", "exam_tags"))
    if "机关实务" in question_type:
        return f"机关实务题：{topic}怎么处理"
    if "面试" in question_type:
        return f"面试常见题：{topic}怎么答"
    if "申论" in question_type:
        return f"申论素材：{topic}怎么用"
    if upper_points or exam_tags:
        return f"高频考点：{topic}怎么答"
    return f"今日带走：{topic}的答题角度"


def _fit_subject_length(subject: str, brief: dict) -> str:
    text = _clean_text(subject)
    if len(text) <= 26:
        return text
    question_type = _clean_text(_get_nested(brief, "daily_question", "question_type"))
    topic = _pick_topic_from_brief(brief)
    while len(topic) > 4:
        shorter = topic[:-1].rstrip(WEAK_ENDINGS + "和与及的")
        if not shorter or shorter == topic:
            break
        topic = shorter
        if "机关实务" in question_type:
            text = f"机关实务题：{topic}怎么处理"
        elif "面试" in question_type:
            text = f"面试常见题：{topic}怎么答"
        elif "申论" in question_type:
            text = f"申论素材：{topic}怎么用"
        elif _as_list(_get_nested(brief, "daily_question", "upper_exam_points")) or _as_list(_get_nested(brief, "featured_article", "article_framework_map", "exam_tags")):
            text = f"高频考点：{topic}怎么答"
        else:
            text = f"今日带走：{topic}的答题角度"
        if len(text) <= 26:
            return text
    return text[:26].rstrip(WEAK_ENDINGS + "和与及的")


def normalize_email_subject(brief: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    brief = brief if isinstance(brief, dict) else {}
    original = _clean_text(brief.get("email_subject"))
    stripped = strip_subject_prefix(original)
    if original and stripped != original:
        warnings.append("email_subject prefix removed")

    use_fallback = False
    reasons: list[str] = []
    if not stripped:
        use_fallback = True
        reasons.append("missing")
    if stripped and is_generic_subject(stripped):
        use_fallback = True
        reasons.append("generic")
    if stripped and has_hype_word(stripped):
        use_fallback = True
        reasons.append("hype_word")
    if stripped and len(stripped) > 26:
        use_fallback = True
        reasons.append("too_long")

    final_subject = build_subject_from_brief(brief) if use_fallback else stripped
    final_subject = _fit_subject_length(final_subject, brief)
    if not final_subject:
        final_subject = "今日带走：基层治理的答题角度"
    brief["email_subject"] = final_subject
    if use_fallback:
        warnings.append(f"email_subject normalized via fallback ({','.join(reasons)})")
    elif final_subject != stripped:
        warnings.append("email_subject normalized")
    return brief, warnings
