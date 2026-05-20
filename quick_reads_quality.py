from __future__ import annotations

import re
from typing import Any


EXAM_VALUE_KEYWORDS = [
    "考点",
    "申论",
    "面试",
    "公基",
    "题型",
    "答题",
    "作答",
    "素材",
    "案例",
    "表达",
    "表述",
    "金句",
    "框架",
    "对策",
    "综合分析",
    "贯彻执行",
    "基层治理",
    "公共服务",
    "民生",
    "治理",
    "政策落实",
    "热点背景",
    "积累",
]

NEWS_SUMMARY_MARKERS = [
    "报道了",
    "介绍了",
    "讲述了",
    "指出了",
    "强调了",
    "展示了",
    "反映了",
    "体现了",
    "本文主要",
    "文章主要",
    "新闻主要",
]

GENERIC_VALUE_PHRASES = [
    "值得关注",
    "有一定价值",
    "可以了解",
    "有参考意义",
    "拓展视野",
    "补充阅读",
    "学习了解",
]

DEV_MARKERS = ["None", "null", "not_found", "待补充", "第X条", "TODO", "Traceback", "Exception"]
TRUNCATION_MARKERS = ["……", "...", "…", ".."]
DANGLING_ENDINGS = (
    "通过",
    "由于",
    "为了",
    "围绕",
    "依靠",
    "立足",
    "推动",
    "促进",
    "实现",
    "提升",
    "强化",
    "完善",
    "构建",
    "形成",
    "建立",
    "转向",
    "转为",
    "赋能",
    "配套",
    "让",
    "把",
    "与",
    "和",
    "及",
    "并",
    "但",
    "而",
    "在",
    "为",
    "的",
    "监",
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " / ".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        return " / ".join(_text(item) for item in value.values() if _text(item))
    return str(value).strip()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _quick_reason(item: Any) -> str:
    if isinstance(item, dict):
        return _text(
            item.get("reason")
            or item.get("exam_value")
            or item.get("usable_for_exam")
            or item.get("value")
            or item.get("summary")
        )
    return _text(item)


def _quick_title(item: Any) -> str:
    if isinstance(item, dict):
        return _text(item.get("title"))
    return ""


def _quick_one_sentence(item: Any) -> str:
    if isinstance(item, dict):
        return _text(item.get("one_sentence"))
    return ""


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def _last_clause(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[，,；;。！？]", text) if part.strip()]
    return parts[-1] if parts else text.strip()


def _looks_incomplete(text: str) -> bool:
    value = _text(text)
    if not value:
        return False
    if any(marker in value for marker in TRUNCATION_MARKERS):
        return True
    if value.endswith(DANGLING_ENDINGS):
        return True
    clause = _last_clause(value)
    if clause.startswith(("让", "把")) and len(clause) <= 10:
        return True
    if clause.startswith(("通过", "依靠", "围绕", "立足")) and len(clause) <= 14:
        return True
    if value.endswith(("，", "、", "：", "；", ",", ":", ";")):
        return True
    return False


def _looks_like_plain_news_summary(text: str) -> bool:
    if not text:
        return False
    compact = re.sub(r"\s+", "", text)
    news_hits = _keyword_hits(compact, NEWS_SUMMARY_MARKERS)
    exam_hits = _keyword_hits(compact, EXAM_VALUE_KEYWORDS)
    generic_hits = _keyword_hits(compact, GENERIC_VALUE_PHRASES)
    return bool(news_hits) and len(exam_hits) == 0 or (len(generic_hits) >= 1 and len(exam_hits) == 0)


def evaluate_quick_reads(brief: dict[str, Any]) -> dict[str, Any]:
    quick_reads = _as_list(brief.get("quick_reads"))
    issues: list[dict[str, str]] = []
    checks = {
        "quick_read_count": len(quick_reads),
        "items_with_exam_value": 0,
        "items_looking_like_news_summary": 0,
        "items_missing_reason": 0,
    }

    if len(quick_reads) > 2:
        issues.append({"severity": "low", "code": "too_many_quick_reads", "message": "速读文章超过2篇，手机阅读负担偏高"})

    for idx, item in enumerate(quick_reads[:3], start=1):
        title = _quick_title(item)
        reason = _quick_reason(item)
        one_sentence = _quick_one_sentence(item)
        combined = f"{title} {reason}"

        if any(marker in combined for marker in DEV_MARKERS):
            issues.append({"severity": "high", "code": "quick_read_dev_marker", "message": f"第{idx}篇速读含开发态占位或异常字段"})
            continue

        if not title and not reason:
            checks["items_missing_reason"] += 1
            issues.append({"severity": "high", "code": "empty_quick_read", "message": f"第{idx}篇速读标题和价值说明均为空"})
            continue

        if not reason:
            checks["items_missing_reason"] += 1
            issues.append({"severity": "medium", "code": "missing_quick_read_reason", "message": f"第{idx}篇速读缺少考试价值说明"})
            continue

        if not one_sentence:
            issues.append({"severity": "high", "code": "missing_quick_read_one_sentence", "message": f"第{idx}篇速读缺少一句话概括，邮件会退化为只展示考试价值"})
        elif _looks_incomplete(one_sentence):
            issues.append({"severity": "high", "code": "truncated_quick_read_one_sentence", "message": f"第{idx}篇速读一句话概括疑似半句话"})

        if isinstance(item, dict):
            url_status = _text(item.get("url_status")).lower()
            url_reason = _text(item.get("url_status_reason"))
            if url_status and url_status not in {"valid", "ok"}:
                issues.append({"severity": "high", "code": "quick_read_url_not_valid", "message": f"第{idx}篇速读链接状态异常：{url_status} {url_reason}"})

        exam_hits = _keyword_hits(reason, EXAM_VALUE_KEYWORDS)
        if exam_hits:
            checks["items_with_exam_value"] += 1
        else:
            issues.append({"severity": "medium", "code": "missing_exam_value", "message": f"第{idx}篇速读缺少明确考点、案例、表达或题型价值"})

        if _looks_like_plain_news_summary(reason):
            checks["items_looking_like_news_summary"] += 1
            issues.append({"severity": "medium", "code": "plain_news_summary", "message": f"第{idx}篇速读像普通新闻摘要，缺少考试转化"})

        if _looks_incomplete(reason):
            issues.append({"severity": "high", "code": "truncated_quick_read_exam_value", "message": f"第{idx}篇速读考试价值疑似半句话"})

        if len(reason) < 18:
            issues.append({"severity": "low", "code": "quick_read_reason_too_short", "message": f"第{idx}篇速读价值说明偏短"})

    if quick_reads and checks["items_with_exam_value"] == 0 and checks["items_looking_like_news_summary"] >= len(quick_reads):
        issues.append({"severity": "high", "code": "quick_reads_all_news_summary", "message": "速读整体退化为新闻摘要，没有体现考试转化价值"})

    score = 100
    for issue in issues:
        severity = issue.get("severity")
        if severity == "high":
            score -= 26
        elif severity == "medium":
            score -= 13
        else:
            score -= 6
    score = max(0, min(100, score))
    high_count = sum(1 for item in issues if item.get("severity") == "high")
    medium_count = sum(1 for item in issues if item.get("severity") == "medium")
    ok = score >= 76 and high_count == 0 and medium_count <= 1
    status = "ok" if ok else ("review" if score >= 58 else "fail")

    return {"ok": ok, "status": status, "score": score, "checks": checks, "issues": issues}
