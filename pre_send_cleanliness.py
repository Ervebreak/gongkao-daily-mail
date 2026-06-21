from __future__ import annotations

import copy
import difflib
import re
from typing import Any

from question_quality import _looks_incomplete


TITLE_PREFIX = "【公考晨读】"
DISPLAY_LABELS = ("可用表达", "作答主线", "审题关键", "如果点原文，重点看", "可迁移框架")
LEADING_RESIDUE = "：:·•・"
DISPLAY_PREFIX_RULES = {
    "brief.featured_article.rewritable_expression": ("可用表达",),
    "brief.featured_article.original_reading_focus": ("如果点原文，重点看",),
    "brief.featured_article.usable_for_exam": ("可用表达", "如果点原文，重点看", "换成考场话"),
    "brief.featured_article.exam_use[*]": ("换成考场话", "可用表达", "如果点原文，重点看"),
    "brief.daily_question.breaking_hint": ("作答主线", "破题关键"),
    "brief.daily_question.exam_focus": ("审题关键",),
    "brief.today_takeaway.framework": ("可迁移框架",),
}

SEMANTIC_TRUNCATION_FIELDS = {
    "brief.featured_article.original_reading_focus",
    "brief.featured_article.one_sentence",
    "brief.featured_article.rewritable_expression",
    "brief.today_takeaway.framework",
    "brief.quick_reads[*].one_sentence",
    "brief.quick_reads[*].exam_value",
    "brief.daily_question.exam_focus",
    "brief.daily_question.breaking_hint",
    "brief.daily_question.thirty_second_answer",
    "brief.daily_question.output_sentence_template",
    "brief.lite_paid_cta.hook",
    "brief.lite_paid_highlight",
}

TRUNCATION_ISSUE_CODES = {
    "semantic_truncation",
    "text_truncation",
    "truncated_takeaway",
    "expression_truncated",
    "visible_text_truncation",
}

KNOWN_TRUNCATION_REPAIRS = (
    ("避免答", "帮助作答避免空泛。"),
    ("供需矛", "供需矛盾。"),
    ("过错责任", "过错责任认定。"),
    ("和群", "和群众监督结合起来。"),
    ("拿高", "拿高分的关键。"),
)


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
            rows.extend(_walk_strings(item, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_walk_strings(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        rows.append((path, value))
    return rows


def _path_parts(path: str) -> list[str]:
    return re.findall(r"[^.\[\]]+|\[\d+\]", path)


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


def _has_semantic_truncation_issue(path: str, issues: list[dict[str, Any]]) -> bool:
    normalized_path = _normalized_body_path(path)
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("code") or "") not in TRUNCATION_ISSUE_CODES:
            continue
        issue_path = str(issue.get("path") or "")
        if issue_path == path or _normalized_body_path(issue_path) == normalized_path:
            return True
    return False


def _extract_quality_truncation_issues(data: dict[str, Any]) -> list[dict[str, Any]]:
    quality = data.get("quality") if isinstance(data.get("quality"), dict) else {}
    buckets: list[Any] = []
    final_quality = quality.get("final") if isinstance(quality.get("final"), dict) else {}
    if final_quality:
        buckets.extend(final_quality.values())
    for key in ("content_quality", "today_takeaway", "expression_quality", "quick_reads", "daily_question"):
        if isinstance(quality.get(key), dict):
            buckets.append(quality.get(key))
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        for issue in bucket.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "")
            if code not in {"text_truncation", "truncated_takeaway", "expression_truncated"}:
                continue
            field = str(issue.get("field") or "").strip()
            if field and not field.startswith("brief."):
                field = f"brief.{field}"
            bad_text = _text(issue.get("bad_text"))
            signature = (code, field, bad_text)
            if signature in seen:
                continue
            seen.add(signature)
            issues.append(
                {
                    "code": code,
                    "path": field,
                    "bad_text": bad_text,
                    "message": _text(issue.get("message")) or code,
                }
            )
    return issues


def _repair_known_truncated_tail(value: str) -> str:
    text = _text(value)
    if not text:
        return text
    for bad_tail, replacement in KNOWN_TRUNCATION_REPAIRS:
        if text.endswith(bad_tail):
            return text[: -len(bad_tail)] + replacement
    return text


def _looks_semantically_truncated(value: str) -> bool:
    text = _text(value)
    if not text:
        return False
    if _looks_incomplete(text):
        return True
    return any(text.endswith(bad_tail) for bad_tail, _replacement in KNOWN_TRUNCATION_REPAIRS)


def _repair_semantic_truncation(path: str, value: str) -> str:
    text = _repair_known_truncated_tail(value)
    normalized_path = _normalized_body_path(path)
    if not _looks_semantically_truncated(text):
        if not text.endswith(("。", "！", "？")) and normalized_path in SEMANTIC_TRUNCATION_FIELDS:
            return f"{text}。"
        return text
    if normalized_path == "brief.featured_article.original_reading_focus":
        return f"{text.rstrip('，,；;：:。!?！？') }，帮助作答避免空泛。".strip()
    if normalized_path == "brief.today_takeaway.framework":
        return f"{text.rstrip('，,；;：:。!?！？')}，形成完整闭环。"
    if normalized_path in {"brief.lite_paid_cta.hook", "brief.lite_paid_highlight"}:
        return f"{text.rstrip('，,；;：:。!?！？')}，适合迁移到类似场景题中。"
    if normalized_path.startswith("brief.quick_reads[*]."):
        return f"{text.rstrip('，,；;：:。!?！？')}。"
    if normalized_path.startswith("brief.daily_question."):
        return f"{text.rstrip('，,；;：:。!?！？')}。"
    return text


def _semantic_truncation_issues(data: dict[str, Any]) -> list[dict[str, Any]]:
    brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    issues: list[dict[str, Any]] = []
    for path, value in _walk_strings(brief, "brief"):
        if _normalized_body_path(path) not in SEMANTIC_TRUNCATION_FIELDS:
            continue
        if not _looks_semantically_truncated(value):
            continue
        issues.append(
            _issue(
                "high",
                "semantic_truncation",
                "字段存在疑似半截句，需在发送前自动修补或阻断。",
                path,
                auto_fixable=True,
                blocking=True,
            )
        )
    plain_text = _text(data.get("plain_text"))
    html_body = _text(data.get("html_body"))
    for issue in _extract_quality_truncation_issues(data):
        bad_text = _text(issue.get("bad_text"))
        issue_path = str(issue.get("path") or "")
        if issue_path:
            issues.append(
                _issue(
                    "high",
                    str(issue.get("code") or "semantic_truncation"),
                    _text(issue.get("message")) or "字段存在疑似半截句。",
                    issue_path,
                    auto_fixable=True,
                    blocking=True,
                )
            )
            continue
        if bad_text and (bad_text in plain_text or bad_text in html_body):
            issues.append(
                _issue(
                    "high",
                    "visible_text_truncation",
                    "最终成品中仍可见疑似半截句，发送前需阻断。",
                    "plain_text",
                    blocking=True,
                )
            )
    return issues


def _clean_text_field(path: str, value: str) -> str:
    normalized_path = _normalized_body_path(path)
    if path in {"subject", "brief.email_subject", "brief.subject"}:
        return _dedupe_subject_prefix(value)
    if normalized_path in DISPLAY_PREFIX_RULES:
        return _strip_labels(value, DISPLAY_PREFIX_RULES[normalized_path])
    return _strip_leading_colon(_collapse_repeated_label(value))


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


def _similarity_key(text: str) -> str:
    return re.sub(r"[\s，。；：:、,.!?！？“”\"'（）()《》<>【】\[\]-]+", "", text)


def _golden_sentence_text(item: Any) -> str:
    return _text(item.get("sentence") or item.get("text")) if isinstance(item, dict) else _text(item)


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
    if any(len(row.strip()) > 260 for row in re.split(r"\n+", candidate_answer)):
        issues.append(_issue("low", "candidate_answer_paragraph_too_long", "考生版答案存在偏长段落，手机阅读成本较高。", "brief.daily_question.candidate_answer"))
    return issues


def _daily_question_structure_issues(data: dict[str, Any]) -> list[dict[str, Any]]:
    brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    text = _text(question.get("question"))
    groups = {
        "identity": ("作为", "假如你是", "工作人员", "调研组", "负责人", "城管局", "街道", "社区"),
        "scene": ("某地", "某市", "某区", "近期", "群众", "基层", "社区", "学校", "企业", "辖区"),
        "conflict": ("问题", "困境", "被占", "缺乏", "争议", "抱怨", "难用", "反转", "风险", "短板"),
        "task": ("请", "提出", "建议", "对策", "工作思路", "怎么办", "如何", "破解"),
    }
    labels = {"identity": "身份", "scene": "场景", "conflict": "矛盾", "task": "任务"}
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


def check_cleanliness(data: dict[str, Any], *, enforce_daily_question_structure: bool = True) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    for path, value in _walk_strings(brief, "brief"):
        label = _contains_repeated_label(value)
        if label:
            issues.append(_issue("high", "duplicate_label_prefix", f"存在重复栏目标题：{label}", path, auto_fixable=True, blocking=True))
        if re.match(rf"^\s*[{re.escape(LEADING_RESIDUE)}]", value):
            issues.append(_issue("high", "leading_colon", "字段正文以冒号开头。", path, auto_fixable=True, blocking=True))
        normalized_path = _normalized_body_path(path)
        if normalized_path in DISPLAY_PREFIX_RULES:
            stripped = _strip_labels(value, DISPLAY_PREFIX_RULES[normalized_path])
            if stripped != _text(value):
                issues.append(_issue("high", "display_label_prefix", "字段值不应携带栏目标题前缀，标题由模板渲染。", path, auto_fixable=True, blocking=True))
    rewritable = _text((brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}).get("rewritable_expression"))
    if rewritable.startswith("可用表达") or rewritable.startswith("可用表达：") or rewritable.startswith("可用表达:"):
        issues.append(_issue("high", "rewritable_expression_label_prefix", "可用表达字段值不应包含可用表达前缀。", "brief.featured_article.rewritable_expression", auto_fixable=True, blocking=True))
    subject = _text(data.get("subject"))
    email_subject = _text(brief.get("email_subject"))
    html_body = _text(data.get("html_body"))
    plain_text = _text(data.get("plain_text"))
    if subject.count("【公考晨读】") >= 2:
        issues.append(_issue("high", "duplicate_subject_prefix", "subject 存在重复【公考晨读】前缀。", "subject", auto_fixable=True, blocking=True))
    if email_subject.count("【公考晨读】") >= 2:
        issues.append(_issue("high", "duplicate_subject_prefix", "brief.email_subject 存在重复【公考晨读】前缀。", "brief.email_subject", auto_fixable=True, blocking=True))
    if html_body.count("【公考晨读】") >= 2:
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
    if enforce_daily_question_structure:
        issues.extend(_daily_question_structure_issues(data))
    issues.extend(_semantic_truncation_issues(data))
    issues.extend(_nonblocking_issues(data))
    return {"issues": issues}


def _framework_action(item: Any) -> str:
    text = _text(item)
    if not text:
        return "抓住关键环节"
    text = text.split("：", 1)[0].split(":", 1)[0]
    return text.strip(" 。；;，,") or "抓住关键环节"


def _repair_thirty_second_answer_from_root(root: Any) -> str:
    try:
        question = root["brief"]["daily_question"]
    except Exception:
        return ""
    if not isinstance(question, dict):
        return ""
    current = _text(question.get("thirty_second_answer"))
    fallback = _text(question.get("output_sentence_template"))
    target_text = current or fallback
    if target_text:
        return ""
    framework = question.get("answer_framework") or question.get("answer_frame") or []
    if not isinstance(framework, list):
        framework = []
    actions = [_framework_action(item) for item in framework if _text(item)][:3]
    while len(actions) < 3:
        actions.append(("压实责任", "协同推进", "闭环落实")[len(actions)])
    repaired = "这道题的核心是把问题推进到治理闭环：" + f"一是{actions[0]}；二是{actions[1]}；三是{actions[2]}，" + "最终用责任、协同和长效机制把问题解决到位。"
    question["thirty_second_answer"] = repaired
    return repaired


def auto_fix_cleanliness(data: dict[str, Any], issues: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    fixed = copy.deepcopy(data)
    fixes: list[dict[str, str]] = []
    has_fixable = any(issue.get("auto_fixable") for issue in issues)
    if isinstance(fixed.get("brief"), dict):
        for path, before in _walk_strings(fixed["brief"], "brief"):
            after = _clean_text_field(path, before)
            if _has_semantic_truncation_issue(path, issues):
                after = _repair_semantic_truncation(path, after)
            if after != before:
                _set_path(fixed, path, after)
                fixes.append(_fix("clean_brief_field", path, before, after))
                has_fixable = True
        before_thirty = _text(((fixed.get("brief") or {}).get("daily_question") or {}).get("thirty_second_answer"))
        repaired = _repair_thirty_second_answer_from_root(fixed)
        if repaired and repaired != before_thirty:
            fixes.append(_fix("repair_thirty_second_answer", "brief.daily_question.thirty_second_answer", before_thirty, repaired))
            has_fixable = True
    if not has_fixable and not fixes:
        return fixed, fixes
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
    return {"ok": not unresolved, "status": status, "score": score, "fixes": fixes, "issues": issues_after, "unresolved_issues": unresolved}


def pre_send_cleanliness_guard(
    data: dict[str, Any],
    *,
    enforce_daily_question_structure: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    checked = check_cleanliness(data, enforce_daily_question_structure=enforce_daily_question_structure)
    fixed, fixes = auto_fix_cleanliness(data, checked.get("issues") or [])
    fixed = _sync_rendered_outputs(fixed)
    rechecked = check_cleanliness(fixed, enforce_daily_question_structure=enforce_daily_question_structure)
    residual_fixable = [issue for issue in rechecked.get("issues") or [] if issue.get("auto_fixable")]
    if residual_fixable:
        fixed, second_fixes = auto_fix_cleanliness(fixed, residual_fixable)
        fixes.extend(second_fixes)
        fixed = _sync_rendered_outputs(fixed)
        rechecked = check_cleanliness(fixed, enforce_daily_question_structure=enforce_daily_question_structure)
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
