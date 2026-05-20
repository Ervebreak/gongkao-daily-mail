from __future__ import annotations

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


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _compact(value: Any) -> str:
    return re.sub(r"[\s，。；;：:、,.!！?？‘’“”\"'（）()《》【】/\-]+", "", _text(value))


def evaluate_framework_map(brief: dict[str, Any]) -> dict[str, Any]:
    featured = brief.get("featured_article") or {}
    framework = (featured.get("article_framework_map") or {}) if isinstance(featured, dict) else {}
    if not isinstance(framework, dict):
        framework = {}
    steps = _as_list(framework.get("steps"))
    main_line = _text(framework.get("main_thread") or framework.get("main_line") or framework.get("overall_exam_value"))
    one_sentence = _text(featured.get("one_sentence") or featured.get("core_viewpoint") or featured.get("main_thread")) if isinstance(featured, dict) else ""

    issues: list[dict[str, str]] = []
    normalized = []
    for idx, step in enumerate(steps, start=1):
        if isinstance(step, dict):
            label = _text(step.get("label") or step.get("title") or step.get("name"))
            content = _text(step.get("content") or step.get("text") or step.get("desc") or step.get("summary"))
        else:
            text = _text(step)
            if "：" in text:
                label, content = text.split("：", 1)
            elif ":" in text:
                label, content = text.split(":", 1)
            else:
                label, content = f"节点{idx}", text
        normalized.append({"label": label, "content": content})

    if not main_line:
        issues.append({"severity": "high", "code": "missing_main_line", "message": "缺少文章主线"})
    if len(normalized) < 3:
        issues.append({"severity": "high", "code": "too_few_steps", "message": "框架图节点少于3个"})
    elif len(normalized) > 5:
        issues.append({"severity": "medium", "code": "too_many_steps", "message": "框架图节点多于5个"})

    broad_labels = {"背景", "问题", "原因", "对策", "启示", "背景分析", "问题呈现", "原因分析", "对策建议", "总结提升"}
    fixed_template_labels = {"文章主线", "现实矛盾", "具体路径", "总结落点", "材料主线", "结构主线", "考场落点"}
    truncated_endings = ("，", "、", "和", "并", "等", "但", "通过", "由于", "…", "……", ".", "..", "...", "：", ":")
    isolated_digit_re = re.compile(r"^(?:\d+(?:\.\d+)?(?:天|年|人|次|万|分钟|小时|元|家)?)$")
    labels = [item["label"] for item in normalized]
    if labels[:4] == ["文章主线", "现实矛盾", "具体路径", "总结落点"]:
        issues.append({"severity": "high", "code": "fixed_framework_template", "message": "框架图套用了固定四段式：文章主线/现实矛盾/具体路径/总结落点"})
    elif sum(1 for label in labels if label in fixed_template_labels) >= 3:
        issues.append({"severity": "high", "code": "fixed_framework_template", "message": "框架图大量使用固定模板标签，缺少原文展开逻辑"})
    universal_patterns = [
        re.compile(r"从问题识别、?责任分工和?长效反馈"),
        re.compile(r"把文章判断转化为可复述、?可作答"),
        re.compile(r"围绕今日主题提炼现实问题和作答主线"),
        re.compile(r"从具体事实中找到治理堵点和表达素材"),
        re.compile(r"提炼现实问题和治理方向"),
    ]
    main_compact = _compact(main_line)
    one_sentence_compact = _compact(one_sentence)
    for step in normalized:
        label = step["label"]
        content = step["content"]
        merged = f"{label} {content}".strip()
        if label.startswith("考场迁移") or "这类题怎么用" in label or "考场迁移" in merged:
            issues.append({"severity": "high", "code": "exam_migration_step", "message": f"框架图只展示文章结构，不应加入考场迁移节点：{merged}"})
        if label in broad_labels or label in fixed_template_labels:
            severity = "high" if label in {"具体路径", "总结落点"} else "medium"
            issues.append({"severity": severity, "code": "generic_label", "message": f"标签过于空泛或模板化：{label}"})
        if any(pattern.search(content) for pattern in universal_patterns):
            issues.append({"severity": "high", "code": "universal_framework_content", "message": f"节点内容是万能模板句，缺少本篇文章独有信息：{merged}"})
        content_compact = _compact(content)
        if content_compact and (content_compact == main_compact or content_compact == one_sentence_compact):
            issues.append({"severity": "medium", "code": "duplicate_framework_content", "message": f"节点内容与主线/一句话看懂重复：{merged}"})
        if isolated_digit_re.fullmatch(content) or isolated_digit_re.fullmatch(label):
            issues.append({"severity": "high", "code": "isolated_number", "message": f"出现孤立数字：{merged}"})
        if len(content) < 8:
            issues.append({"severity": "medium", "code": "too_short_step", "message": f"节点内容过短：{merged}"})
        if content.endswith(truncated_endings):
            issues.append({"severity": "high", "code": "incomplete_sentence", "message": f"节点可能是半句话：{merged}"})
        if label.endswith(truncated_endings):
            issues.append({"severity": "high", "code": "incomplete_label", "message": f"节点小标题可能是半句话：{merged}"})
        if not re.search(r"[。；;！？!?]$", content) and len(content) < 20:
            # 短句且无收束标点，更可能是残句/标签
            issues.append({"severity": "medium", "code": "possibly_fragment", "message": f"节点可能不完整：{merged}"})

    score = 100
    for issue in issues:
        severity = issue.get("severity")
        if severity == "high":
            score -= 24
        elif severity == "medium":
            score -= 12
        else:
            score -= 6
    score = max(0, min(100, score))
    high_count = sum(1 for item in issues if item.get("severity") == "high")
    medium_count = sum(1 for item in issues if item.get("severity") == "medium")
    ok = score >= 72 and high_count == 0 and medium_count <= 2
    status = "ok" if ok else ("review" if score >= 55 else "fail")
    hints = []
    if any(item.get("code") == "isolated_number" for item in issues):
        hints.append("数字必须带完整对象、单位和语境；无法确认时请删除。")
    if any(item.get("code") in {"generic_label", "possibly_fragment", "incomplete_sentence", "incomplete_label"} for item in issues):
        hints.append("优先用贴合原文展开逻辑的完整短句重写节点，不要只写抽象标签或半句话。")
    if any(item.get("code") == "exam_migration_step" for item in issues):
        hints.append("删除框架图中的考场迁移节点，迁移价值放到今日一题或今日可带走。")
    if any(item.get("code") in {"fixed_framework_template", "universal_framework_content"} for item in issues):
        hints.append("不要套文章主线/现实矛盾/具体路径/总结落点；每个节点必须有本篇文章独有信息。")
    if any(item.get("code") == "too_many_steps" for item in issues):
        hints.append("优先压缩为3-5个节点，并贴合原文小标题和段落顺序。")

    return {
        "ok": ok,
        "status": status,
        "score": score,
        "main_line": main_line,
        "step_count": len(normalized),
        "steps": normalized,
        "issues": issues,
        "hints": hints,
    }
