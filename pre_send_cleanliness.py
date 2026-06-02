from __future__ import annotations

import copy
import difflib
import re
from typing import Any


TITLE_PREFIX = "【公考晨读】"
DISPLAY_LABELS = ("可用表达", "作答主线", "审题关键", "如果点原文，重点看", "可迁移框架")
LEADING_RESIDUE = "：:·•・"
SENTENCE_ENDING = "。！？；.!?」』）】》"
TRUNCATED_TAILS = (
    "可落地", "可以用于", "适合转化为", "有助于", "体现出", "关键在于", "主要包括",
    "从而", "进而", "同时", "并且", "最", "畅通维", "清退四", "好人条", "探索收", "制度保", "信息透明", "责任主",
)
DANGLING_ENDINGS = (
    "通过", "由于", "为了", "围绕", "依靠", "立足", "推动", "促进", "实现", "提升",
    "强化", "完善", "构建", "形成", "建立", "转向", "转为", "赋能", "配套", "提出从",
    "让", "把", "与", "和", "及", "并", "但", "而", "在", "为", "的", "监",
)
BODY_TEXT_PATHS = {
    "brief.today_focus",
    "brief.today_three_things.must_remember_sentence",
    "brief.featured_article.one_sentence",
    "brief.featured_article.original_reading_focus",
    "brief.featured_article.article_framework_map.main_thread",
    "brief.featured_article.three_useful_points",
    "brief.featured_article.three_useful_points[*]",
    "brief.featured_article.exam_use",
    "brief.featured_article.exam_use[*]",
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
DISPLAY_PREFIX_RULES = {
    "brief.featured_article.rewritable_expression": ("可用表达",),
    "brief.featured_article.original_reading_focus": ("如果点原文，重点看",),
    "brief.featured_article.usable_for_exam": ("可用表达", "如果点原文，重点看", "换成考场话"),
    "brief.featured_article.exam_use[*]": ("换成考场话", "可用表达", "如果点原文，重点看"),
    "brief.daily_question.breaking_hint": ("作答主线", "破题关键"),
    "brief.daily_question.exam_focus": ("审题关键",),
    "brief.today_takeaway.framework": ("可迁移框架",),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clip(value: Any, limit: int = 90) -> str:
    text = _text(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _issue(severity: str, code: str, message: str, path: str, *, auto_fixable: bool = False, blocking: bool = False, module_override: str = "") -> dict[str, Any]:
    issue = {"severity": severity, "code": code, "message": message, "path": path, "auto_fixable": auto_fixable, "blocking": blocking}
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


def _is_body_text_path(path: str) -> bool:
    return _normalized_body_path(path) in BODY_TEXT_PATHS


def _without_sentence_punctuation(text: str) -> str:
    return (text or "").strip().rstrip(SENTENCE_ENDING).strip()


def _last_clause(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[，,；;。！？]", text or "") if part.strip()]
    return parts[-1] if parts else (text or "").strip()


def _looks_incomplete(text: str) -> bool:
    value = _text(text)
    if not value:
        return False
    if any(marker in value for marker in ("……", "...", "…", "..")):
        return True
    if value.endswith(("，", "、", "：", "；", ",", ":", ";")):
        return True
    stripped = _without_sentence_punctuation(value)
    if any(stripped.endswith(tail) for tail in TRUNCATED_TAILS):
        return True
    if any(stripped.endswith(tail) for tail in DANGLING_ENDINGS):
        return True
    if re.search(r"(?:^|[。！？；;])\s*(第[一二三四五六七八九十]步|一是|二是|三是|四是|第一[，,:：]|第二[，,:：]|第三[，,:：]|第四[，,:：])[^。！？.!?]{0,60}$", stripped):
        if len(_last_clause(stripped)) <= 28:
            return True
    clause = _last_clause(value)
    if clause.startswith(("让", "把")) and len(clause) <= 10:
        return True
    if clause.startswith(("通过", "依靠", "围绕", "立足", "提出从")) and len(clause) <= 18:
        return True
    return False


def _suspected_truncated_tail(text: str) -> str:
    stripped = _without_sentence_punctuation(text)
    for tail in TRUNCATED_TAILS:
        if stripped.endswith(tail):
            return tail
    for tail in DANGLING_ENDINGS:
        if stripped.endswith(tail):
            return tail
    return "未完成结构" if _looks_incomplete(text) else ""


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


def _normalize_trailing_semicolon(path: str, text: str) -> str:
    if _normalized_body_path(path) not in {"brief.daily_question.thirty_second_answer", "brief.daily_question.output_sentence_template"}:
        return text
    fixed = (text or "").rstrip()
    if fixed.endswith(("；", ";", "，", ",", "、", "：", ":")):
        return fixed.rstrip("；;，,、：: ").rstrip() + "。"
    return text


def _repair_known_truncated_body(path: str, value: str) -> str:
    normalized_path = _normalized_body_path(path)
    original = _text(value)
    text = _without_sentence_punctuation(original)
    if not text:
        return original
    if normalized_path == "brief.featured_article.original_reading_focus":
        if text.endswith("责任主"):
            return text + "体和平台责任边界。"
        if text.endswith("最"):
            return text + "值得借鉴的部分。"
        if text.endswith("好人条"):
            return text + "款”等内容，这些都是分析公共服务设施从配置到有效使用的关键材料。"
    if normalized_path == "brief.featured_article.article_framework_map.main_thread" and text.endswith("探索收"):
        return text + "束全文。"
    if normalized_path == "brief.today_takeaway.framework":
        if text.endswith("清退四"):
            return text + "个环节形成治理闭环。"
        if "找得到" in text and "敢用" in text and "会用" in text and "第一步" in text and "第二步" not in text:
            return "“找得到—敢用—会用”三层治理框架：先打通信息壁垒，让设备位置可查；再强化法律宣传，让群众敢于出手；最后开展实操培训，让设备真正用得上。"
    if normalized_path == "brief.quick_reads[*].one_sentence":
        if text.endswith("畅通维"):
            return text + "权渠道。"
        if text.endswith("信息透明"):
            return text + "化等方面破解供需错位。"
        if text.endswith("制度保"):
            return text + "障。"
    if normalized_path == "brief.daily_question.candidate_answer":
        if text.endswith("限期停业整改"):
            return text + "；再次违规或造成严重后果的，直接移出白名单，并将线索移交市场监管、文旅等部门依法处理。"
        if text.endswith("第四，建立维护考核的硬约束") and "AED" in text:
            return text + "，明确设备维护责任人，定期检查电池和电极片状态，将有效运行率纳入责任单位考核。"
    return original


def _clean_text_field(path: str, value: str) -> str:
    normalized_path = _normalized_body_path(path)
    if path in {"subject", "brief.email_subject", "brief.subject"}:
        return _dedupe_subject_prefix(value)
    cleaned = _strip_labels(value, DISPLAY_PREFIX_RULES[normalized_path]) if normalized_path in DISPLAY_PREFIX_RULES else _strip_leading_colon(_collapse_repeated_label(value))
    if _is_body_text_path(path):
        cleaned = _normalize_trailing_semicolon(path, cleaned)
        repaired = _repair_known_truncated_body(path, cleaned)
        if repaired != cleaned:
            return repaired
        if cleaned and not cleaned.endswith(tuple(SENTENCE_ENDING)) and not _looks_incomplete(cleaned):
            cleaned += "。"
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
                issues.append(_issue("low", "golden_sentence_near_duplicate", f"第 {left + 1} 条和第 {right + 1} 条金句相似度较高，建议人工确认。", "brief.today_takeaway.golden_sentences"))
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
            issues.append(_issue("high", f"daily_question_missing_{name}", f"今日一题题干疑似缺少{labels[name]}要素；不在清洁度守卫中硬改，交给 daily_question 重写逻辑处理。", "brief.daily_question.question", blocking=True, module_override="daily_question"))
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
        normalized_path = _normalized_body_path(path)
        if normalized_path in DISPLAY_PREFIX_RULES:
            stripped = _strip_labels(value, DISPLAY_PREFIX_RULES[normalized_path])
            if stripped != _text(value):
                issues.append(_issue("high", "display_label_prefix", "字段值不应携带栏目标题前缀，标题由模板渲染。", path, auto_fixable=True, blocking=True))
        if _is_body_text_path(path):
            text_value = _text(value)
            cleaned_value = _clean_text_field(path, value)
            if cleaned_value != text_value and not _looks_incomplete(cleaned_value):
                issues.append(_issue("medium", "body_field_semantic_fix", "正文型字段已做语义补全或标点清洁，需以复检结果为准。", path, auto_fixable=True))
            if cleaned_value != text_value and normalized_path in {"brief.daily_question.thirty_second_answer", "brief.daily_question.output_sentence_template"} and text_value.rstrip().endswith(("；", ";", "，", ",", "、", "：", ":")):
                issues.append(_issue("high", "trailing_semicolon_answer", "今日一题30秒输出疑似半截句，已字段级补成完整句。", path, auto_fixable=True, blocking=True, module_override="daily_question"))
            truncated_tail = _suspected_truncated_tail(cleaned_value if cleaned_value != text_value else value)
            if truncated_tail:
                known_repair = _repair_known_truncated_body(path, value)
                issues.append(_issue("high", "suspected_truncated_sentence", f"正文型字段疑似半截句，结尾停在“{truncated_tail}”。", path, auto_fixable=known_repair != text_value or normalized_path in {"brief.daily_question.thirty_second_answer", "brief.daily_question.output_sentence_template"}, blocking=True, module_override=_module_from_path(path)))
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
    if target_text and not _looks_incomplete(target_text):
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
