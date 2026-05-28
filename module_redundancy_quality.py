from __future__ import annotations

import difflib
import re
from typing import Any


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
    return re.sub(r"[\s，。；：、,.!?！？;:\"'“”‘’（）()\[\]【】\-—_>→]+", "", value or "")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?；;\n\r]+", text or "")
    result: list[str] = []
    for part in parts:
        sentence = re.sub(r"\s+", "", part).strip("，、：: ")
        if len(_compact(sentence)) >= 12:
            result.append(sentence)
    return result


def _longest_common_substring_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    best = 0
    for i, left_char in enumerate(left, start=1):
        current = [0] * (len(right) + 1)
        for j, right_char in enumerate(right, start=1):
            if left_char == right_char:
                current[j] = previous[j - 1] + 1
                if current[j] > best:
                    best = current[j]
        previous = current
    return best


def _gold_sentence(item: Any) -> str:
    if isinstance(item, dict):
        return _text(item.get("sentence"))
    return _text(item)


def _step_text(item: Any) -> str:
    if isinstance(item, dict):
        return _text([item.get("label"), item.get("content")])
    return _text(item)


def _field_items(brief: dict[str, Any]) -> list[dict[str, str]]:
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    takeaway = brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    framework_map = featured.get("article_framework_map") if isinstance(featured.get("article_framework_map"), dict) else {}

    items: list[dict[str, str]] = []

    for idx, value in enumerate(_as_list(featured.get("exam_use") or featured.get("usable_for_exam")), start=1):
        text = _text(value)
        if text:
            items.append({"module": "featured_article.exam_use", "name": f"featured_article.exam_use[{idx}]", "role": "exam_use", "text": text})

    rewritable = _text(featured.get("rewritable_expression"))
    if rewritable:
        items.append({"module": "featured_article.rewritable_expression", "name": "featured_article.rewritable_expression", "role": "rewritable_expression", "text": rewritable})

    for idx, value in enumerate(_as_list(takeaway.get("golden_sentences")), start=1):
        text = _gold_sentence(value)
        if text:
            items.append({"module": "today_takeaway.golden_sentences", "name": f"today_takeaway.golden_sentences[{idx}]", "role": "golden_sentence", "text": text})

    takeaway_framework = _text(takeaway.get("framework"))
    if takeaway_framework:
        items.append({"module": "today_takeaway.framework", "name": "today_takeaway.framework", "role": "takeaway_framework", "text": takeaway_framework})

    for idx, value in enumerate(_as_list(question.get("answer_framework") or question.get("answer_frame")), start=1):
        text = _text(value)
        if text:
            items.append({"module": "daily_question.answer_framework", "name": f"daily_question.answer_framework[{idx}]", "role": "answer_framework", "text": text})

    candidate_answer = _text(question.get("candidate_answer"))
    if candidate_answer:
        items.append({"module": "daily_question.candidate_answer", "name": "daily_question.candidate_answer", "role": "candidate_answer", "text": candidate_answer})

    for idx, value in enumerate(_as_list(framework_map.get("steps")), start=1):
        text = _step_text(value)
        if text:
            items.append({"module": "article_framework_map.steps", "name": f"article_framework_map.steps[{idx}]", "role": "framework_step", "text": text})

    return items


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _sentence_records(items: list[dict[str, str]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for item in items:
        sentences = _sentences(item["text"]) or ([item["text"]] if len(_compact(item["text"])) >= 12 else [])
        for sentence in sentences:
            records.append({**item, "sentence": sentence, "compact": _compact(sentence)})
    return records


def _is_verbose_framework_item(text: str) -> bool:
    compact = _compact(text)
    if len(compact) > 35:
        return True
    answer_markers = ["我认为", "具体来说", "第一", "第二", "第三", "首先", "其次", "最后", "关键是", "不能只", "而要", "不是", "而是"]
    if any(marker in text for marker in answer_markers):
        return True
    if len(compact) >= 28 and len(re.findall(r"[，,；;]", text)) >= 2:
        return True
    return False


def _rhetorical_pattern_hits(text: str) -> list[str]:
    patterns = [
        r"不能只.{0,18}?而要",
        r"不能只.{0,18}?而是",
        r"不是.{0,18}?而是",
        r"不在于.{0,18}?而在于",
    ]
    hits: list[str] = []
    for pattern in patterns:
        hits.extend(re.findall(pattern, text or ""))
    return hits


def _preferred_rewrite_target(left: dict[str, str], right: dict[str, str]) -> str:
    roles = {left["role"], right["role"]}
    # 金句是最终摘抄区，尽量保留；撞车时改考场迁移或可用表达。
    if "exam_use" in roles:
        return left["name"] if left["role"] == "exam_use" else right["name"]
    if "rewritable_expression" in roles:
        return left["name"] if left["role"] == "rewritable_expression" else right["name"]
    return left["name"]


def _role_overlap_severity(common_len: int, ratio: float) -> str:
    # 模块角色重叠影响产品感，但一般不应直接阻断发送。
    # 完全复制或极高相似度才升到 medium；普通功能相似只作为 low/review。
    if ratio >= 0.92 or common_len >= 24:
        return "medium"
    return "low"


def evaluate_module_redundancy(brief: dict[str, Any]) -> dict[str, Any]:
    items = _field_items(brief)
    records = _sentence_records(items)
    issues: list[dict[str, str]] = []
    repeated: list[dict[str, str]] = []
    near_duplicates: list[dict[str, str]] = []
    role_overlaps: list[dict[str, str]] = []

    seen: dict[str, dict[str, str]] = {}
    for record in records:
        key = record["compact"]
        if len(key) < 12:
            continue
        previous = seen.get(key)
        if previous and previous["module"] != record["module"]:
            severity = "medium" if "golden_sentence" in {previous["role"], record["role"]} else "medium"
            repeated.append({
                "from": previous["name"],
                "to": record["name"],
                "sentence": record["sentence"][:90],
                "severity": severity,
            })
        else:
            seen[key] = record

    for i, left in enumerate(records):
        left_key = left["compact"]
        if len(left_key) < 18:
            continue
        for right in records[i + 1:]:
            if left["module"] == right["module"]:
                continue
            right_key = right["compact"]
            if len(right_key) < 18 or left_key == right_key:
                continue
            common_len = _longest_common_substring_length(left_key, right_key)
            ratio = difflib.SequenceMatcher(None, left_key, right_key).ratio()
            if common_len >= 12 or ratio >= 0.86:
                near_duplicates.append({
                    "from": left["name"],
                    "to": right["name"],
                    "sentence": left["sentence"][:90],
                    "common_chars": str(common_len),
                    "similarity": f"{ratio:.2f}",
                })
                break
        if len(near_duplicates) >= 12:
            break

    role_records = [record for record in records if record["role"] in {"exam_use", "rewritable_expression", "golden_sentence"}]
    for i, left in enumerate(role_records):
        left_key = left["compact"]
        if len(left_key) < 16:
            continue
        for right in role_records[i + 1:]:
            if left["role"] == right["role"]:
                continue
            right_key = right["compact"]
            if len(right_key) < 16:
                continue
            common_len = _longest_common_substring_length(left_key, right_key)
            ratio = difflib.SequenceMatcher(None, left_key, right_key).ratio()
            if common_len >= 12 or ratio >= 0.82:
                role_overlaps.append({
                    "from": left["name"],
                    "to": right["name"],
                    "sentence": left["sentence"][:90],
                    "common_chars": str(common_len),
                    "similarity": f"{ratio:.2f}",
                    "severity": _role_overlap_severity(common_len, ratio),
                    "rewrite_target": _preferred_rewrite_target(left, right),
                })

    for duplicate in repeated[:5]:
        issues.append({
            "severity": duplicate["severity"],
            "code": "repeated_expression_across_modules",
            "message": f"{duplicate['from']} 与 {duplicate['to']} 出现完全相同表达：{duplicate['sentence']}",
        })

    if near_duplicates:
        first = near_duplicates[0]
        issues.append({
            "severity": "medium",
            "code": "near_duplicate_expression",
            "message": f"{first['from']} 与 {first['to']} 表达高度相似或连续重复核心短语",
        })

    answer_framework_items = [item for item in items if item["role"] == "answer_framework"]
    verbose_items = [item for item in answer_framework_items if _is_verbose_framework_item(item["text"])]
    for item in verbose_items[:4]:
        issues.append({
            "severity": "medium",
            "code": "answer_framework_too_verbose",
            "message": f"{item['name']} 过长或写成完整答案句，作答框架应只保留关键词式骨架",
        })

    for overlap in role_overlaps[:4]:
        issues.append({
            "severity": overlap.get("severity", "low"),
            "code": "module_role_overlap",
            "message": (
                f"{overlap['from']} 与 {overlap['to']} 承担了相近表达功能。"
                f"建议优先改写 {overlap.get('rewrite_target') or overlap['from']}，让 exam_use 写考场迁移方法，"
                "rewritable_expression 写考场表达，golden_sentences 保留摘抄金句。"
            ),
            "rewrite_target": overlap.get("rewrite_target", ""),
        })

    all_text = " ".join(item["text"] for item in items)
    rhetorical_hits = _rhetorical_pattern_hits(all_text)
    if len(rhetorical_hits) > 3:
        issues.append({
            "severity": "medium" if len(rhetorical_hits) >= 6 else "low",
            "code": "rhetorical_pattern_repetition",
            "message": f"“不能只……而要……”或“不是……而是……”类句式重复 {len(rhetorical_hits)} 次，表达显得啰嗦",
        })

    score = 100
    for issue in issues:
        severity = issue.get("severity")
        if severity == "high":
            score -= 28
        elif severity == "medium":
            score -= 12
        else:
            score -= 5
    score = max(0, min(100, score))
    high_count = sum(1 for item in issues if item.get("severity") == "high")
    medium_count = sum(1 for item in issues if item.get("severity") == "medium")
    ok = high_count == 0 and medium_count <= 2
    status = "ok" if ok else ("review" if high_count == 0 else "fail")

    return {
        "ok": ok,
        "status": status,
        "score": score,
        "checks": {
            "field_count": len(items),
            "sentence_count": len(records),
            "repeated_count": len(repeated),
            "near_duplicate_count": len(near_duplicates),
            "module_role_overlap_count": len(role_overlaps),
            "verbose_answer_framework_count": len(verbose_items),
            "rhetorical_pattern_count": len(rhetorical_hits),
        },
        "examples": {
            "repeated": repeated[:5],
            "near_duplicates": near_duplicates[:5],
            "module_role_overlaps": role_overlaps[:5],
        },
        "issues": issues,
    }
