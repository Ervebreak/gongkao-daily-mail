from __future__ import annotations

import copy
import difflib
import re
from typing import Any


TITLE_PREFIX = "【公考晨读】"
DISPLAY_LABELS = (
    "可用表达",
    "作答主线",
    "审题关键",
    "如果点原文，重点看",
)
LEADING_RESIDUE = "：:·•・"
SENTENCE_ENDING = "。！？；.!?」』）】》"
TRUNCATED_TAILS = (
    "可落地",
    "可以用于",
    "适合转化为",
    "有助于",
    "体现出",
    "关键在于",
    "主要包括",
    "从而",
    "进而",
    "同时",
    "并且",
)
BODY_TEXT_PATHS = {
    "brief.today_focus",
    "brief.today_three_things.must_remember_sentence",
    "brief.featured_article.one_sentence",
    "brief.featured_article.original_reading_focus",
    "brief.featured_article.three_useful_points",
    "brief.featured_article.three_useful_points[*]",
    "brief.featured_article.exam_use",
    "brief.featured_article.usable_for_exam",
    "brief.featured_article.rewritable_expression",
    "brief.daily_question.exam_focus",
    "brief.daily_question.breaking_hint",
    "brief.daily_question.candidate_answer",
    "brief.daily_question.output_sentence_template",
    "brief.daily_question.thirty_second_answer",
    "brief.today_takeaway.framework",
    "brief.today_takeaway.common_knowledge_points",
    "brief.today_takeaway.common_knowledge_points[*]",
    "brief.today_takeaway.golden_sentences[*].sentence",
    "brief.quick_reads[*].one_sentence",
    "brief.quick_reads[*].exam_value",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clip(value: Any, limit: int = 90) -> str:
    text = _text(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _issue(
    severity: str,
    code: str,
    message: str,
    path: str,
    *,
    auto_fixable: bool = False,
    blocking: bool = False,
    module_override: str = "",
) -> dict[str, Any]:
    issue = {
        "severity": severity,
        "code": code,
        "message": message,
        "path": path,
        "auto_fixable": auto_fixable,
        "blocking": blocking,
    }
    if module_override:
        issue["module_override"] = module_override
    return issue


def _fix(code: str, path: str, before: Any, after: Any) -> dict[str, str]:
    return {"code": code, "path": path, "before": _clip(before), "after": _clip(after)}


def _walk_strings(value: Any, path: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            rows.extend(_walk_strings(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_walk_strings(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        rows.append((path, value))
    return rows


def _path_parts(path: str) -> list[str]:
    return re.findall(r"[^.\[\]]+|\[\d+\]", path)


def _get_path(root: Any, path: str) -> Any:
    current = root
    for part in _path_parts(path):
        if part.startswith("["):
            current = current[int(part.strip("[]"))]
        else:
            current = current[part]
    return current


def _set_path(root: Any, path: str, value: Any) -> None:
    current = root
    parts = _path_parts(path)
    for part in parts[:-1]:
        current = current[int(part.strip("[]"))] if part.startswith("[") else current[part]
    last = parts[-1]
    if last.startswith("["):
        current[int(last.strip("[]"))] = value
    else:
        current[last] = value


def _dedupe_subject_prefix(text: str) -> str:
    return re.sub(r"(【公考晨读】\s*){2,}", TITLE_PREFIX, text or "").strip()


def _collapse_repeated_label(text: str) -> str:
    fixed = text or ""
    for label in DISPLAY_LABELS:
        fixed = re.sub(rf"({re.escape(label)}\s*[：:]\s*){{2,}}", f"{label}：", fixed)
        fixed = re.sub(rf"^{re.escape(label)}\s*[：:]\s*{re.escape(label)}", label, fixed)
        fixed = re.sub(rf"({re.escape(label)}\s*[：:]\s*)[{re.escape(LEADING_RESIDUE)}]\s*", r"\1", fixed)
    return fixed.strip()


def _strip_leading_colon(text: str) -> str:
    return re.sub(rf"^\s*[{re.escape(LEADING_RESIDUE)}]\s*", "", text or "").strip()


def _strip_labels(text: str, labels: tuple[str, ...]) -> str:
    fixed = _collapse_repeated_label(text)
    changed = True
    while changed:
        changed = False
        for label in labels:
            next_value = re.sub(rf"^\s*{re.escape(label)}\s*[：:]?\s*", "", fixed, count=1).strip()
            if next_value != fixed:
                fixed = next_value
                changed = True
    return _strip_leading_colon(fixed)


def _normalized_body_path(path: str) -> str:
    return re.sub(r"\[\d+\]", "[*]", path or "")


def _is_body_text_path(path: str) -> bool:
    return _normalized_body_path(path) in BODY_TEXT_PATHS


def _ensure_sentence_punctuation(text: str) -> str:
    fixed = (text or "").rstrip()
    if not fixed or fixed.endswith(tuple(SENTENCE_ENDING)):
        return fixed
    return fixed + "。"


def _normalize_trailing_semicolon(path: str, text: str) -> str:
    if _normalized_body_path(path) not in {
        "brief.daily_question.thirty_second_answer",
        "brief.daily_question.output_sentence_template",
    }:
        return text
    fixed = (text or "").rstrip()
    if fixed.endswith(("；", ";")):
        return fixed.rstrip("；; ").rstrip() + "。"
    return text


def _without_sentence_punctuation(text: str) -> str:
    return (text or "").strip().rstrip(SENTENCE_ENDING).strip()


def _suspected_truncated_tail(text: str) -> str:
    stripped = _without_sentence_punctuation(text)
    for tail in TRUNCATED_TAILS:
        if stripped.endswith(tail):
            return tail
    return ""


def _module_from_path(path: str) -> str:
    if ".daily_question." in path:
        return "daily_question"
    if ".featured_article." in path:
        return "featured_article"
    if ".today_takeaway." in path:
        return "today_takeaway"
    if ".quick_reads" in path:
        return "quick_reads"
    return "brief"


def _clean_text_field(path: str, value: str) -> str:
    field_labels = {
        "brief.featured_article.rewritable_expression": ("可用表达",),
        "brief.featured_article.original_reading_focus": ("如果点原文，重点看",),
        "brief.daily_question.breaking_hint": ("作答主线",),
        "brief.daily_question.exam_focus": ("审题关键",),
    }
    if path in {"subject", "brief.email_subject", "brief.subject"}:
        return _dedupe_subject_prefix(value)
    if path in field_labels:
        cleaned = _strip_labels(value, field_labels[path])
    else:
        cleaned = _strip_leading_colon(_collapse_repeated_label(value))
    if _is_body_text_path(path):
        cleaned = _normalize_trailing_semicolon(path, cleaned)
        cleaned = _ensure_sentence_punctuation(cleaned)
    return cleaned


def _clean_html(html: str) -> str:
    fixed = _dedupe_subject_prefix(html or "")
    fixed = re.sub(rf"(>\s*)[{re.escape(LEADING_RESIDUE)}]\s*", r"\1", fixed)
    for label in DISPLAY_LABELS:
        fixed = re.sub(rf"({re.escape(label)}\s*[：:]\s*){{2,}}", f"{label}：", fixed)
    return fixed


def _plain_lines_have_leading_colon(text: str) -> bool:
    return any(re.match(rf"^\s*[{re.escape(LEADING_RESIDUE)}]", line) for line in (text or "").splitlines() if line.strip())


def _contains_repeated_label(text: str) -> str:
    for label in DISPLAY_LABELS:
        if re.search(rf"({re.escape(label)}\s*[：:]\s*){{2,}}", text or ""):
            return label
    return ""


def _golden_sentence_text(item: Any) -> str:
    if isinstance(item, dict):
        return _text(item.get("sentence") or item.get("text"))
    return _text(item)


def _similarity_key(text: str) -> str:
    return re.sub(r"[\s，。；：:、,.!?！？“”\"'（）()《》<>【】\[\]-]+", "", text)


def _nonblocking_issues(data: dict[str, Any]) -> list[dict[str, Any]]:
    brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    issues: list[dict[str, Any]] = []

    takeaway = brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}
    sentences = [_golden_sentence_text(item) for item in takeaway.get("golden_sentences") or []]
    sentences = [item for item in sentences if item]
    for left in range(len(sentences)):
        for right in range(left + 1, len(sentences)):
            left_key = _similarity_key(sentences[left])
            right_key = _similarity_key(sentences[right])
            if not left_key or not right_key:
                continue
            ratio = difflib.SequenceMatcher(None, left_key, right_key).ratio()
            contained = left_key in right_key or right_key in left_key
            if ratio >= 0.86 or (contained and min(len(left_key), len(right_key)) >= 18):
                issues.append(
                    _issue(
                        "low",
                        "golden_sentence_near_duplicate",
                        f"第 {left + 1} 条和第 {right + 1} 条金句相似度较高，建议人工确认。",
                        "brief.today_takeaway.golden_sentences",
                    )
                )

    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    thirty_second = _text(question.get("thirty_second_answer") or question.get("output_sentence_template"))
    if len(thirty_second) > 120:
        issues.append(_issue("low", "thirty_second_answer_too_long", "30秒输出句式偏长，建议后续压缩。", "brief.daily_question.thirty_second_answer"))
    candidate_answer = _text(question.get("candidate_answer"))
    long_paragraphs = [row for row in re.split(r"\n+", candidate_answer) if len(row.strip()) > 260]
    if long_paragraphs:
        issues.append(_issue("low", "candidate_answer_paragraph_too_long", "考生版答案存在偏长段落，手机阅读成本较高。", "brief.daily_question.candidate_answer"))

    return issues


def _daily_question_structure_issues(data: dict[str, Any]) -> list[dict[str, Any]]:
    brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    text = _text(question.get("question"))
    groups = {
        "identity": ("作为", "假如你是", "工作人员", "调研组", "负责人", "城管局", "街道", "社区"),
        "scene": ("某地", "某市", "某区", "近期", "群众", "基层", "社区", "学校", "企业"),
        "conflict": ("问题", "困境", "被占", "缺乏", "争议", "抱怨", "难用", "反转", "风险"),
        "task": ("请", "提出", "建议", "对策", "工作思路", "怎么办", "如何"),
    }
    labels = {
        "identity": "身份",
        "scene": "场景",
        "conflict": "矛盾",
        "task": "任务",
    }
    issues: list[dict[str, Any]] = []
    for name, keywords in groups.items():
        if not any(keyword in text for keyword in keywords):
            issues.append(
                _issue(
                    "high",
                    f"daily_question_missing_{name}",
                    f"今日一题题干疑似缺少{labels[name]}要素；不在清洁度守卫中硬改，交给 daily_question 重写逻辑处理。",
                    "brief.daily_question.question",
                    blocking=True,
                    module_override="daily_question",
                )
            )
    return issues


def check_cleanliness(data: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    for path, value in _walk_strings(brief, "brief"):
        label = _contains_repeated_label(value)
        if label:
            issues.append(_issue("high", "duplicate_label_prefix", f"存在重复栏目标题：{label}", path, auto_fixable=True, blocking=True))
        if re.match(rf"^\s*[{re.escape(LEADING_RESIDUE)}]", value):
            issues.append(_issue("high", "leading_colon", "字段正文以冒号开头。", path, auto_fixable=True, blocking=True))
        if _is_body_text_path(path):
            text_value = _text(value)
            cleaned_value = _clean_text_field(path, value)
            if cleaned_value != text_value and cleaned_value.endswith("。") and not text_value.rstrip().endswith(tuple(SENTENCE_ENDING)):
                issues.append(_issue("medium", "missing_sentence_punctuation", "正文型字段缺少句末标点，已自动补中文句号。", path, auto_fixable=True))
            if cleaned_value != text_value and _normalized_body_path(path) in {
                "brief.daily_question.thirty_second_answer",
                "brief.daily_question.output_sentence_template",
            } and text_value.rstrip().endswith(("；", ";")):
                issues.append(_issue("medium", "trailing_semicolon_answer", "今日一题参考句式以分号结尾，已字段级改为完整句号。", path, auto_fixable=True))
            truncated_tail = _suspected_truncated_tail(value)
            if truncated_tail:
                issues.append(
                    _issue(
                        "high",
                        "suspected_truncated_sentence",
                        f"正文型字段疑似半截句，结尾停在“{truncated_tail}”。",
                        path,
                        blocking=True,
                        module_override=_module_from_path(path),
                    )
                )
    rewritable = _text((brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}).get("rewritable_expression"))
    if re.match(r"^\s*可用表达\s*[：:]?", rewritable):
        issues.append(_issue("high", "rewritable_expression_label_prefix", "可用表达字段值不应包含可用表达前缀。", "brief.featured_article.rewritable_expression", auto_fixable=True, blocking=True))

    subject = _text(data.get("subject"))
    email_subject = _text(brief.get("email_subject"))
    html_body = _text(data.get("html_body"))
    plain_text = _text(data.get("plain_text"))
    if re.search(r"(【公考晨读】\s*){2,}", subject):
        issues.append(_issue("high", "duplicate_subject_prefix", "subject 存在重复【公考晨读】前缀。", "subject", auto_fixable=True, blocking=True))
    if re.search(r"(【公考晨读】\s*){2,}", email_subject):
        issues.append(_issue("high", "duplicate_subject_prefix", "brief.email_subject 存在重复【公考晨读】前缀。", "brief.email_subject", auto_fixable=True, blocking=True))
    if re.search(r"(【公考晨读】\s*){2,}", html_body):
        issues.append(_issue("high", "duplicate_subject_prefix", "HTML 顶部标题疑似存在重复【公考晨读】前缀。", "html_body", auto_fixable=True, blocking=True))
    label = _contains_repeated_label(plain_text)
    if label:
        issues.append(_issue("high", "duplicate_label_prefix", f"纯文本存在重复栏目标题：{label}", "plain_text", auto_fixable=True, blocking=True))
    label = _contains_repeated_label(html_body)
    if label:
        issues.append(_issue("high", "duplicate_label_prefix", f"HTML 存在重复栏目标题：{label}", "html_body", auto_fixable=True, blocking=True))
    if _plain_lines_have_leading_colon(plain_text):
        issues.append(_issue("high", "leading_colon", "纯文本正文存在以冒号开头的行。", "plain_text", auto_fixable=True, blocking=True))
    if re.search(rf">\s*[{re.escape(LEADING_RESIDUE)}]", html_body):
        issues.append(_issue("high", "leading_colon", "HTML 模块正文存在以冒号开头的内容。", "html_body", auto_fixable=True, blocking=True))

    issues.extend(_daily_question_structure_issues(data))
    issues.extend(_nonblocking_issues(data))
    return {"issues": issues}


def auto_fix_cleanliness(data: dict[str, Any], issues: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    fixed = copy.deepcopy(data)
    fixes: list[dict[str, str]] = []
    if not any(issue.get("auto_fixable") for issue in issues):
        return fixed, fixes

    if isinstance(fixed.get("brief"), dict):
        for path, before in _walk_strings(fixed["brief"], "brief"):
            after = _clean_text_field(path, before)
            if after != before:
                _set_path(fixed, path, after)
                fixes.append(_fix("clean_brief_field", path, before, after))

    for path in ("subject", "plain_text", "html_body"):
        before = _text(fixed.get(path))
        if path == "html_body":
            after = _clean_html(before)
        elif path == "plain_text":
            after = "\n".join(_clean_text_field(path, line) for line in before.splitlines())
        else:
            after = _clean_text_field(path, before)
        if after != before:
            fixed[path] = after
            fixes.append(_fix(f"clean_{path}", path, before, after))
    return fixed, fixes


def _sync_rendered_outputs(data: dict[str, Any]) -> dict[str, Any]:
    fixed = copy.deepcopy(data)
    brief = fixed.get("brief") if isinstance(fixed.get("brief"), dict) else {}
    if not brief:
        return fixed
    try:
        from email_renderer import render_email_html, render_plain_text

        fixed["plain_text"] = render_plain_text(brief)
        fixed["html_body"] = render_email_html(brief)
    except Exception:
        fixed["plain_text"] = "\n".join(_clean_text_field("plain_text", line) for line in _text(fixed.get("plain_text")).splitlines())
        fixed["html_body"] = _clean_html(_text(fixed.get("html_body")))
    return fixed


def decide_gate_status(data: dict[str, Any], issues_after: list[dict[str, Any]], fixes: list[dict[str, str]]) -> dict[str, Any]:
    unresolved = [issue for issue in issues_after if issue.get("blocking")]
    high_count = sum(1 for issue in issues_after if str(issue.get("severity")).lower() == "high")
    low_count = sum(1 for issue in issues_after if str(issue.get("severity")).lower() == "low")
    score = max(0, 100 - len(unresolved) * 35 - (high_count - len(unresolved)) * 20 - low_count * 3 - max(0, len(fixes) - 2))
    status = "fail" if unresolved else ("review" if issues_after else "ok")
    return {
        "ok": not unresolved,
        "status": status,
        "score": score,
        "fixes": fixes,
        "issues": issues_after,
        "unresolved_issues": unresolved,
    }


def pre_send_cleanliness_guard(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    checked = check_cleanliness(data)
    fixed, fixes = auto_fix_cleanliness(data, checked.get("issues") or [])
    fixed = _sync_rendered_outputs(fixed)
    rechecked = check_cleanliness(fixed)
    residual_fixable = [issue for issue in rechecked.get("issues") or [] if issue.get("auto_fixable")]
    if residual_fixable:
        fixed, second_fixes = auto_fix_cleanliness(fixed, residual_fixable)
        fixes.extend(second_fixes)
        fixed = _sync_rendered_outputs(fixed)
        rechecked = check_cleanliness(fixed)
    report = decide_gate_status(fixed, rechecked.get("issues") or [], fixes)

    quality = fixed.get("quality") if isinstance(fixed.get("quality"), dict) else {}
    final = quality.get("final") if isinstance(quality.get("final"), dict) else {}
    final["cleanliness"] = report
    quality["final"] = final
    quality["cleanliness"] = report
    fixed["quality"] = quality
    fixed["cleanliness_report"] = report
    return fixed, report


def check_pre_send_cleanliness(data: dict[str, Any]) -> dict[str, Any]:
    fixed, _report = pre_send_cleanliness_guard(data)
    return fixed
