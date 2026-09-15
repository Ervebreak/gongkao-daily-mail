from __future__ import annotations

import re
from typing import Any


BANNED_LITE_CTA_WORDS = (
    "教你",
    "转化价值极高",
    "避免假大空",
    "干瘪对策词",
    "必看",
    "押题",
    "必考",
    "一定会考",
    "保过",
    "上岸",
    "提分神器",
    "内部资料",
    "不看就亏",
)

BLACKLISTED_LITE_ANSWER_MODULE_TERMS = (
    "审题关键",
    "作答主线",
    "完整作答框架",
    "作答框架",
    "答题框架",
    "参考答案",
    "30秒答案",
    "30 秒答案",
)

SAFE_LITE_CTA_BENEFIT_WORDS = (
    "文章框架图",
    "框架图",
    "考场转化",
    "原文问题链",
    "治理边界辨析",
    "素材迁移",
    "表达积累",
    "周末 PDF",
    "申论素材",
    "面试表达",
    "适用题型",
    "使用场景",
)

# Backward-compatible name used by the Lite quality reviewer. Its vocabulary is
# intentionally restricted to values that do not name Full-only answer modules.
GENERIC_BENEFIT_WORDS = SAFE_LITE_CTA_BENEFIT_WORDS

SAFE_LITE_CTA_FALLBACK = (
    "完整版还会展开文章框架图与考场转化，补充原文问题链、治理边界辨析、素材迁移和表达积累，供申论分析、对策题或面试复盘时按需使用。"
)


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _strip_prefixes(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^\s*今日完整版亮点[：:]\s*", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _infer_source_module(brief: dict[str, Any]) -> str:
    question = _ensure_dict(brief.get("daily_question"))
    coordinate = _ensure_dict(brief.get("policy_coordinate"))
    featured = _ensure_dict(brief.get("featured_article"))
    if question.get("question") and (_as_list(question.get("answer_framework")) or question.get("breaking_hint") or question.get("exam_focus")):
        return "daily_question"
    if coordinate.get("authoritative_quote") or coordinate.get("policy_quote") or coordinate.get("exam_transfer"):
        return "policy_coordinate"
    if featured.get("title") or featured.get("one_sentence"):
        return "featured_article"
    return "brief"


def _extract_answer_labels(brief: dict[str, Any], limit: int = 4) -> list[str]:
    question = _ensure_dict(brief.get("daily_question"))
    labels: list[str] = []
    for item in _as_list(question.get("answer_framework")):
        text = str(item or "").strip()
        if not text:
            continue
        if "：" in text:
            text = text.split("：", 1)[0]
        elif ":" in text:
            text = text.split(":", 1)[0]
        text = re.sub(r"^\s*\d+[\.、\)]\s*", "", text).strip("，。、：:； ")
        if text and text not in labels:
            labels.append(text)
        if len(labels) >= limit:
            break
    return labels


def _contains_answer_chain(text: str, brief: dict[str, Any]) -> bool:
    labels = [label for label in _extract_answer_labels(brief) if len(label) >= 2]
    if labels and sum(1 for label in labels if label in text) >= 2:
        return True
    chain_patterns = (
        r"[\w\u4e00-\u9fff]{2,}[—→-][\w\u4e00-\u9fff]{2,}[—→-][\w\u4e00-\u9fff]{2,}",
        r"(?:先|首先).{1,28}(?:再|然后|其次).{1,28}(?:最后|最终)",
        r"(?:一是|第一).{1,32}(?:二是|第二).{1,32}(?:三是|第三)",
        r"(?:读题|审题).{0,12}(?:搭|列|写).{0,8}(?:框架|提纲).{0,12}(?:写成|形成|完成).{0,8}(?:答案|作答)",
    )
    return any(re.search(pattern, text) for pattern in chain_patterns)


def _coordinate_quote_text(value: Any) -> str:
    return str(value or "").strip().rstrip("。；;！!？?")


def build_lite_paid_cta_prompt(brief: dict[str, Any]) -> str:
    featured = _ensure_dict(brief.get("featured_article"))
    question = _ensure_dict(brief.get("daily_question"))
    coordinate = _ensure_dict(brief.get("policy_coordinate"))
    answer_labels = "—".join(_extract_answer_labels(brief))
    quote_text = _coordinate_quote_text(coordinate.get("authoritative_quote") or coordinate.get("policy_quote"))
    prompt_parts = [
        "你是公考晨读邮件编辑，请为免费简版邮件尾部写 1 条“今天完整版多讲了什么”。",
        "目标：只说明完整版解决什么学习问题、包含哪些模块；免费版只给问题、方向和一个样例，不给完整结构、方法和答案。",
        "只输出 JSON，对象结构必须包含：hook_type、hook、source_module。",
        "约束：",
        "1. hook 用 1 句中文，控制在 60-120 字。",
        "2. 只可从这些安全价值类别中选择：文章框架图、考场转化、原文问题链、治理边界辨析、素材迁移、表达积累、周末 PDF，或不涉及答案链的同类表述。",
        "3. 不得直接出现审题关键、作答主线、完整作答框架、参考答案、30秒答案等完整版答案模块名，也不得用同义包装披露答案链。",
        "4. 必须基于当天已有内容，不得虚构外部案例、政策、人物或数据。",
        "5. 不得写出 answer_framework 的具体分点标签、作答链条、candidate_answer 内容或任何完整答案表达。",
        "6. 不得出现教你、转化价值极高、避免假大空、干瘪对策词、必看、押题、必考、一定会考、保过、上岸、提分神器、内部资料、不看就亏。",
        "7. 语气像自然提示，不要写成促销广告。",
        "",
        f"今日主题：{brief.get('today_theme') or ''}",
        f"精读标题：{featured.get('title') or ''}",
        f"精读一句话：{featured.get('one_sentence') or ''}",
        f"今日一题：{question.get('question') or ''}",
        f"作答角度仅供边界检查，禁止在 hook 中复述：{answer_labels}",
        f"政策坐标：{quote_text}",
        f"考场迁移：{coordinate.get('exam_transfer') or ''}",
        f"审题关键：{question.get('exam_focus') or question.get('breaking_hint') or question.get('breaking_direction') or ''}",
    ]
    return "\n".join(prompt_parts)


def fallback_lite_paid_cta_payload(brief: dict[str, Any]) -> dict[str, Any]:
    source_module = _infer_source_module(brief)
    return {
        "hook_type": source_module,
        "hook": SAFE_LITE_CTA_FALLBACK,
        "source_module": source_module,
        "fallback_used": True,
    }


def normalize_lite_paid_cta_payload(value: Any, brief: dict[str, Any]) -> dict[str, Any]:
    fallback = fallback_lite_paid_cta_payload(brief)
    payload = _ensure_dict(value)
    hook = _strip_prefixes(payload.get("hook") or payload.get("highlight") or payload.get("lite_paid_highlight") or value)
    normalized = {
        "hook_type": str(payload.get("hook_type") or payload.get("type") or _infer_source_module(brief)).strip() or fallback["hook_type"],
        "hook": hook,
        "source_module": str(payload.get("source_module") or payload.get("module") or _infer_source_module(brief)).strip() or fallback["source_module"],
        "fallback_used": bool(payload.get("fallback_used", False)),
    }
    return normalized


def is_valid_lite_paid_cta_hook(hook: str, brief: dict[str, Any]) -> bool:
    text = _strip_prefixes(hook)
    if not text:
        return False
    if len(text) < 24 or len(text) > 130:
        return False
    if any(term in text for term in BLACKLISTED_LITE_ANSWER_MODULE_TERMS):
        return False
    if any(word in text for word in BANNED_LITE_CTA_WORDS):
        return False
    if _contains_answer_chain(text, brief):
        return False

    candidate_answer = str(_ensure_dict(brief.get("daily_question")).get("candidate_answer") or "").strip()
    if candidate_answer and candidate_answer in text:
        return False

    benefit_hits = sum(1 for word in GENERIC_BENEFIT_WORDS if word in text)
    if benefit_hits < 2:
        return False
    if benefit_hits >= 6 and len(text) > 120:
        return False

    if re.search(r"(比如|例如)\s*$", text):
        return False
    if re.search(r"(适合迁移到|可以迁移到|适合作为|可用于|完整版会把思路拆成)\s*$", text):
        return False

    if text.endswith(("先稳情绪—", "摸清诉求—", "公开协商—", "闭环反馈—", "：", "、", "，", ",", "；", ";", "（", "(")):
        return False

    return True


def finalize_lite_paid_cta_payload(value: Any, brief: dict[str, Any]) -> dict[str, Any]:
    payload = normalize_lite_paid_cta_payload(value, brief)
    if not is_valid_lite_paid_cta_hook(payload.get("hook") or "", brief):
        return fallback_lite_paid_cta_payload(brief)
    payload["hook"] = _strip_prefixes(payload["hook"])
    payload["fallback_used"] = bool(payload.get("fallback_used"))
    return payload


def resolve_lite_paid_cta_payload(latest_json: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        {"hook": latest_json.get("_lite_paid_highlight") or "", "hook_type": "cache", "source_module": _infer_source_module(brief)},
        _ensure_dict(_ensure_dict(brief.get("lite_paid_cta"))),
        _ensure_dict(_ensure_dict(latest_json.get("lite_paid_cta"))),
        {"hook": brief.get("lite_paid_highlight") or "", "hook_type": "legacy", "source_module": _infer_source_module(brief)},
        {"hook": latest_json.get("lite_paid_highlight") or "", "hook_type": "legacy", "source_module": _infer_source_module(brief)},
    ]
    for candidate in candidates:
        payload = normalize_lite_paid_cta_payload(candidate, brief)
        if is_valid_lite_paid_cta_hook(payload.get("hook") or "", brief):
            payload["fallback_used"] = bool(candidate.get("fallback_used", False))
            return payload
    return fallback_lite_paid_cta_payload(brief)
