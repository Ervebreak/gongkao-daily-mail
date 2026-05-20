from __future__ import annotations

import difflib
import re
from typing import Any


DEV_MARKERS = ["None", "null", "not_found", "待补充", "第X条", "TODO", "Traceback", "Exception"]


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


def _compact(value: str) -> str:
    return re.sub(r"[\s，。；：、,.!?！？;:\"'“”‘’（）()\[\]【】\-—_]+", "", value)


def _sentences(text: str) -> list[str]:
    pieces = re.split(r"[。！？!?；;\n\r]+", text)
    result: list[str] = []
    for piece in pieces:
        sentence = re.sub(r"\s+", "", piece).strip("，、：: ")
        if len(sentence) >= 18:
            result.append(sentence)
    return result


def _section_texts(brief: dict[str, Any]) -> dict[str, str]:
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    return {
        "featured_article": _text(
            [
                featured.get("one_sentence"),
                featured.get("core_viewpoint"),
                featured.get("exam_use") or featured.get("usable_for_exam"),
                featured.get("rewritable_expression"),
            ]
        ),
        "framework_map": _text(featured.get("article_framework_map")),
        "daily_question": _text(brief.get("daily_question")),
        "today_takeaway": _text(brief.get("today_takeaway")),
        "quick_reads": _text(brief.get("quick_reads")),
    }


def evaluate_duplication(brief: dict[str, Any]) -> dict[str, Any]:
    sections = _section_texts(brief)
    issues: list[dict[str, str]] = []
    repeated_pairs: list[dict[str, str]] = []
    near_duplicate_pairs: list[dict[str, str]] = []

    for name, text in sections.items():
        if any(marker in text for marker in DEV_MARKERS):
            issues.append({"severity": "high", "code": "dev_marker_repeated", "message": f"{name} 中出现开发态或异常复制字段"})

    sentence_index: dict[str, tuple[str, str]] = {}
    for section, text in sections.items():
        for sentence in _sentences(text):
            key = _compact(sentence)
            if len(key) < 18:
                continue
            previous = sentence_index.get(key)
            if previous and previous[0] != section:
                repeated_pairs.append({"from": previous[0], "to": section, "sentence": sentence[:80]})
            else:
                sentence_index[key] = (section, sentence)

    by_section = {name: _sentences(text)[:24] for name, text in sections.items()}
    section_names = list(by_section)
    for i, left_name in enumerate(section_names):
        for right_name in section_names[i + 1 :]:
            for left in by_section[left_name]:
                left_key = _compact(left)
                if len(left_key) < 24:
                    continue
                for right in by_section[right_name]:
                    right_key = _compact(right)
                    if len(right_key) < 24 or left_key == right_key:
                        continue
                    ratio = difflib.SequenceMatcher(None, left_key, right_key).ratio()
                    if ratio >= 0.88:
                        near_duplicate_pairs.append({"from": left_name, "to": right_name, "sentence": left[:80]})
                        break
                if len(near_duplicate_pairs) >= 8:
                    break

    if repeated_pairs:
        issues.append({"severity": "medium", "code": "cross_module_duplicate_sentence", "message": "跨模块存在完全重复句：" + repeated_pairs[0]["sentence"]})
    if len(repeated_pairs) >= 3 or len(near_duplicate_pairs) >= 4:
        issues.append({"severity": "medium", "code": "severe_cross_module_duplication", "message": "今日一题、精读、金句或速读之间重复较多，影响阅读价值"})
    if len(repeated_pairs) >= 6:
        issues.append({"severity": "high", "code": "abnormal_copy_duplication", "message": "跨模块出现异常大段复制，疑似生成结果粘连"})
    if near_duplicate_pairs:
        issues.append({"severity": "low", "code": "near_duplicate_viewpoint", "message": "跨模块存在相似观点重复，可压缩或改写"})

    score = 100
    for issue in issues:
        severity = issue.get("severity")
        if severity == "high":
            score -= 30
        elif severity == "medium":
            score -= 14
        else:
            score -= 6
    score = max(0, min(100, score))
    high_count = sum(1 for item in issues if item.get("severity") == "high")
    medium_count = sum(1 for item in issues if item.get("severity") == "medium")
    ok = score >= 78 and high_count == 0 and medium_count <= 1
    status = "ok" if ok else ("review" if score >= 60 else "fail")

    return {
        "ok": ok,
        "status": status,
        "score": score,
        "checks": {
            "repeated_pair_count": len(repeated_pairs),
            "near_duplicate_pair_count": len(near_duplicate_pairs),
            "sections_checked": list(sections),
        },
        "examples": {
            "repeated_pairs": repeated_pairs[:5],
            "near_duplicate_pairs": near_duplicate_pairs[:5],
        },
        "issues": issues,
    }
