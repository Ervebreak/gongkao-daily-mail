from __future__ import annotations

import re
from typing import Any


BANNED_LITE_CTA_WORDS = (
    "押题",
    "必考",
    "保过",
    "上岸",
    "提分神器",
    "内部资料",
    "不看就亏",
)

GENERIC_BENEFIT_WORDS = (
    "参考答案",
    "框架图",
    "考场转化",
    "金句拆解",
    "周末 PDF",
)

SAFE_LITE_CTA_FALLBACK = (
    "今天完整版会补充参考答案、文章框架图、考场转化和金句拆解，适合把今日文章从“读过”转成“考场能用”。"
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


def _coordinate_quote_text(value: Any) -> str:
    return str(value or "").strip().rstrip("。；;！!？?")


def build_lite_paid_cta_prompt(brief: dict[str, Any]) -> str:
    featured = _ensure_dict(brief.get("featured_article"))
    question = _ensure_dict(brief.get("daily_question"))
    coordinate = _ensure_dict(brief.get("policy_coordinate"))
    answer_labels = "—".join(_extract_answer_labels(brief))
    quote_text = _coordinate_quote_text(coordinate.get("authoritative_quote") or coordinate.get("policy_quote"))
    prompt_parts = [
        "你是公考晨读邮件编辑，请为免费简版邮件尾部写 1 条“今日完整版亮点”。",
        "目标：告诉免费用户今天完整版最值得看的具体内容，说明适合哪类题、可迁移到什么考场场景。",
        "只输出 JSON，对象结构必须包含：hook_type、hook、source_module。",
        "约束：",
        "1. hook 用 1 句中文，控制在 60-120 字。",
        "2. 只写 1 个亮点，不要泛泛罗列参考答案、框架图、金句拆解等固定权益。",
        "3. 必须基于当天已有内容，不得虚构外部案例、政策、人物或数据。",
        "4. 不得泄露完整 candidate_answer，不得照抄参考答案。",
        "5. 不得出现押题、必考、保过、上岸、提分神器、内部资料、不看就亏。",
        "6. 优先从：今日一题拆解 > 政策坐标/权威表达 > 文章框架转化 中选择一个最具体的亮点。",
        "",
        f"今日主题：{brief.get('today_theme') or ''}",
        f"精读标题：{featured.get('title') or ''}",
        f"精读一句话：{featured.get('one_sentence') or ''}",
        f"今日一题：{question.get('question') or ''}",
        f"作答角度：{answer_labels}",
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
    if any(word in text for word in BANNED_LITE_CTA_WORDS):
        return False

    candidate_answer = str(_ensure_dict(brief.get("daily_question")).get("candidate_answer") or "").strip()
    if candidate_answer and candidate_answer in text:
        return False

    benefit_hits = sum(1 for word in GENERIC_BENEFIT_WORDS if word in text)
    if benefit_hits >= 3:
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
