from __future__ import annotations

import re
from typing import Any

from lite_paid_cta import BANNED_LITE_CTA_WORDS, GENERIC_BENEFIT_WORDS, SAFE_LITE_CTA_FALLBACK, resolve_lite_paid_cta_payload
from question_quality import _looks_incomplete


INTERNAL_MARKERS = (
    "lite_paid_cta",
    "lite_paid_highlight",
    "hook_type",
    "source_module",
    "fallback_used",
    "quality gate",
    "candidate",
    "debug",
    "json",
    "后台字段",
    "内部说明",
)

FULL_ONLY_VISIBLE_MARKERS = (
    "先搭作答框架",
    "作答框架：",
    "考生版参考答案",
    "30秒输出",
    "参考句式",
    "审题关键：",
)

SPECIFICITY_MARKERS = (
    "适合",
    "迁移",
    "场景",
    "题",
    "开头",
    "结尾",
    "分点",
    "作答",
    "表达",
    "立意",
)


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strip_html(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _issue(severity: str, code: str, message: str, *, bad_text: str = "") -> dict[str, Any]:
    issue = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if bad_text:
        issue["bad_text"] = bad_text
    return issue


def _visible_paragraphs(plain_text: str, html_body: str) -> list[str]:
    html_text = _strip_html(html_body)
    candidates = [part.strip() for part in re.split(r"\n+", plain_text or "") if part.strip()]
    candidates.extend(part.strip() for part in re.split(r"[。！？]\s*", html_text) if len(part.strip()) >= 40)
    seen: set[str] = set()
    paragraphs: list[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        paragraphs.append(item)
    return paragraphs


def _looks_too_generic(hook: str) -> bool:
    if not hook:
        return True
    benefit_hits = sum(1 for word in GENERIC_BENEFIT_WORDS if word in hook)
    if hook == SAFE_LITE_CTA_FALLBACK:
        return False
    if benefit_hits >= 2:
        return False
    if benefit_hits >= 3 and not any(marker in hook for marker in SPECIFICITY_MARKERS):
        return True
    return False


def _lite_content_text(visible_text: str) -> str:
    return re.split(r"今天完整版多讲了什么", visible_text, maxsplit=1)[0]


def _answer_framework_label_count(brief: dict[str, Any], visible_text: str) -> int:
    question = _ensure_dict(brief.get("daily_question"))
    labels: set[str] = set()
    raw_items = question.get("answer_framework") or question.get("answer_frame") or []
    if not isinstance(raw_items, list):
        raw_items = [raw_items]
    for item in raw_items:
        text = str(item or "").strip()
        if "：" in text:
            text = text.split("：", 1)[0]
        elif ":" in text:
            text = text.split(":", 1)[0]
        text = re.sub(r"^\s*\d+[\.、\)]\s*", "", text).strip("，。、：:； ")
        if len(text) >= 2:
            labels.add(text)
    return sum(1 for label in labels if label in visible_text)


def _visible_cta_texts(plain_text: str, html_body: str) -> list[str]:
    text = f"{plain_text}\n{_strip_html(html_body)}"
    candidates: list[str] = []
    for pattern in (
        r"今日完整版亮点[：:]\s*([^\n]+)",
        r"完整版会补充[：:]\s*([^\n]+)",
    ):
        candidates.extend(match.group(1).strip() for match in re.finditer(pattern, text) if match.group(1).strip())
    section_parts = re.split(r"今天完整版多讲了什么", text, maxsplit=1)
    if len(section_parts) == 2:
        candidates.extend(part.strip() for part in re.split(r"\n+", section_parts[1]) if len(part.strip()) >= 24)
    seen: set[str] = set()
    result: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def evaluate_lite_email_quality(
    latest_json: dict[str, Any],
    *,
    plain_text: str = "",
    html_body: str = "",
) -> dict[str, Any]:
    brief = _ensure_dict(latest_json.get("brief")) if isinstance(latest_json, dict) else {}
    payload = resolve_lite_paid_cta_payload(latest_json if isinstance(latest_json, dict) else {}, brief)
    hook = str(payload.get("hook") or "").strip()
    visible_text = f"{plain_text}\n{_strip_html(html_body)}"
    lite_body_text = _lite_content_text(visible_text)
    issues: list[dict[str, Any]] = []

    if hook and _looks_incomplete(hook):
        issues.append(_issue("high", "lite_cta_truncated", "简版 CTA 亮点句疑似半截句，需要回退到安全兜底。", bad_text=hook))

    truncated_visible_cta = next((item for item in _visible_cta_texts(plain_text, html_body) if _looks_incomplete(item)), "")
    if truncated_visible_cta:
        issues.append(_issue("high", "lite_cta_truncated", "简版 CTA 可见文案疑似半截句，需要回退到安全兜底。", bad_text=truncated_visible_cta))

    if hook and len(hook) > 160:
        issues.append(_issue("medium", "lite_cta_too_long", "简版 CTA 亮点句过长，移动端阅读压力较大。", bad_text=hook))

    if any(word in hook for word in BANNED_LITE_CTA_WORDS):
        issues.append(_issue("medium", "lite_cta_over_sales", "简版 CTA 出现过强销售话术，建议回退到更克制的文案。", bad_text=hook))

    marker = next((item for item in INTERNAL_MARKERS if item and item.lower() in visible_text.lower()), "")
    if marker:
        issues.append(_issue("high", "lite_internal_marker_leaked", f"简版邮件出现用户不可见的内部标记：{marker}。", bad_text=marker))

    full_marker = next((item for item in FULL_ONLY_VISIBLE_MARKERS if item in lite_body_text), "")
    if full_marker:
        issues.append(_issue("high", "lite_full_module_leaked", f"免费简版正文出现完整版独占模块：{full_marker}。", bad_text=full_marker))

    candidate_answer = str(_ensure_dict(brief.get("daily_question")).get("candidate_answer") or "").strip()
    if candidate_answer and candidate_answer in visible_text:
        issues.append(_issue("high", "lite_candidate_answer_leaked", "免费简版出现考生版参考答案，应只保留问题、方向和一个样例。", bad_text=candidate_answer[:120]))

    framework_label_count = _answer_framework_label_count(brief, lite_body_text)
    if framework_label_count >= 2:
        issues.append(_issue("high", "lite_answer_framework_leaked", "免费简版出现多条完整作答框架标签，应改为思考提示。"))

    dense_paragraph = next((item for item in _visible_paragraphs(plain_text, html_body) if len(item) > 220), "")
    if dense_paragraph:
        issues.append(_issue("medium", "lite_mobile_dense_paragraph", "简版邮件段落过密，移动端阅读体验较差。", bad_text=dense_paragraph[:160]))

    if _looks_too_generic(hook):
        issues.append(_issue("low", "lite_value_not_specific", "简版 CTA 没有充分说明今天完整版具体多讲了什么。", bad_text=hook))

    score = max(0, 100 - sum(18 if item["severity"] == "high" else 8 if item["severity"] == "medium" else 3 for item in issues))
    high_count = sum(1 for item in issues if item["severity"] == "high")
    if high_count:
        status = "fail"
    elif issues:
        status = "review"
    else:
        status = "ok"
    return {
        "ok": high_count == 0,
        "status": status,
        "score": score,
        "issues": issues,
        "hook": hook,
        "source_module": str(payload.get("source_module") or ""),
    }
