from __future__ import annotations

import re
from typing import Any


POLICY_TONE_PHRASES = [
    "持续完善",
    "切实提升",
    "不断夯实",
    "形成合力",
    "强化保障",
    "推动形成",
    "建立健全",
    "扎实推进",
    "全面提升",
    "系统推进",
    "长效机制",
    "统筹推进",
    "赋能增效",
]

STUDENT_TONE_MARKERS = [
    "我认为",
    "具体来说",
    "一方面",
    "另一方面",
    "首先",
    "其次",
    "最后",
    "关键是",
    "不能只",
    "要把",
    "落到",
    "群众",
    "问题",
    "实际",
    "基层",
]

INSTRUCTION_MARKERS = [
    "复述本题",
    "口头复述",
    "训练你的表达",
    "请用30秒",
    "重点练习",
    "逻辑串联",
    "核心对策框架",
]

LABEL_LEAK_MARKERS = [
    "换成考场话：",
    "换成考场话:",
    "考场话：",
    "考场话:",
    "可用表达：",
    "可用表达:",
    "必备金句：",
    "必备金句:",
    "参考句式：",
    "参考句式:",
    "适用场景：",
    "适用场景:",
]

DEV_MARKERS = ["None", "null", "not_found", "待补充", "第X条", "TODO", "Traceback", "Exception"]
TRUNCATION_MARKERS = ["...", "…", "……", ".."]
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


def _gold_sentence(item: Any) -> str:
    if isinstance(item, dict):
        return _text(item.get("sentence"))
    return _text(item)


def _last_clause(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[，,；;。！？]", text) if part.strip()]
    return parts[-1] if parts else text.strip()


def _looks_incomplete(text: str) -> bool:
    value = _text(text)
    if not value:
        return False
    if value.endswith(("?", ";")):
        return False
    if any(marker in value for marker in TRUNCATION_MARKERS):
        return True
    if value.endswith(DANGLING_ENDINGS):
        return True
    clause = _last_clause(value)
    if clause.startswith(("?", "?")) and len(clause) <= 10:
        return True
    if clause.startswith(("??", "??", "??", "??")) and len(clause) <= 14:
        return True
    if value.endswith(("?", "?", "?", "?", ",", ":", "?")):
        return True
    return False

def _expression_fields(brief: dict[str, Any]) -> list[dict[str, str]]:
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    takeaway = brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}
    fields: list[dict[str, str]] = []

    fields.append({"name": "featured_article.rewritable_expression", "text": _text(featured.get("rewritable_expression")), "required": "true"})
    for idx, item in enumerate(_as_list(featured.get("exam_use") or featured.get("usable_for_exam"))[:3], start=1):
        fields.append({"name": f"featured_article.exam_use[{idx}]", "text": _text(item), "required": "false"})

    fields.append({"name": "daily_question.candidate_answer", "text": _text(question.get("candidate_answer")), "required": "true"})
    fields.append({"name": "daily_question.output_sentence_template", "text": _text(question.get("output_sentence_template")), "required": "false"})
    fields.append({"name": "daily_question.thirty_second_answer", "text": _text(question.get("thirty_second_answer")), "required": "false"})

    for idx, item in enumerate(_as_list(takeaway.get("golden_sentences"))[:3], start=1):
        fields.append({"name": f"today_takeaway.golden_sentences[{idx}]", "text": _gold_sentence(item), "required": "true"})
    fields.append({"name": "today_takeaway.framework", "text": _text(takeaway.get("framework")), "required": "false"})
    return fields


def _hit_count(text: str, phrases: list[str]) -> int:
    return sum(1 for phrase in phrases if phrase and phrase in text)


def evaluate_expression_quality(brief: dict[str, Any]) -> dict[str, Any]:
    fields = _expression_fields(brief)
    issues: list[dict[str, str]] = []
    weak_fields: list[str] = []
    policy_tone_fields: list[str] = []
    instruction_fields: list[str] = []

    for field in fields:
        name = field["name"]
        text = field["text"]
        required = field["required"] == "true"
        if not text:
            if required:
                issues.append({"severity": "medium", "code": "missing_expression_field", "message": f"{name} 缺少可供考生模仿的表达"})
            continue

        if any(marker in text for marker in DEV_MARKERS):
            issues.append({"severity": "high", "code": "expression_dev_marker", "message": f"{name} 出现开发态占位或异常字段"})
            continue
        if _looks_incomplete(text):
            issues.append({"severity": "high", "code": "expression_truncated", "message": f"{name} 存在省略号或疑似截断"})

        leaked_labels = [marker for marker in LABEL_LEAK_MARKERS if marker in text]
        if leaked_labels:
            issues.append({"severity": "medium", "code": "label_leaked_in_expression", "message": f"{name} 泄露栏目标签：{'、'.join(leaked_labels[:3])}"})

        policy_hits = _hit_count(text, POLICY_TONE_PHRASES)
        student_hits = _hit_count(text, STUDENT_TONE_MARKERS)
        if policy_hits >= 4 and student_hits <= 2:
            policy_tone_fields.append(name)

        if _hit_count(text, INSTRUCTION_MARKERS) > 0:
            instruction_fields.append(name)

        compact = re.sub(r"\s+", "", text)
        if len(compact) >= 50 and student_hits == 0:
            weak_fields.append(name)

        if name.endswith("candidate_answer") and len(compact) < 160:
            issues.append({"severity": "medium", "code": "candidate_answer_not_enough", "message": "考生版答案偏短，不足以作为可模仿表达"})
        if name.endswith("rewritable_expression") and len(compact) > 90:
            issues.append({"severity": "low", "code": "rewritable_expression_too_long", "message": "可用表达偏长，不利于背诵和迁移"})

    if policy_tone_fields:
        issues.append({"severity": "medium", "code": "policy_report_tone", "message": "部分考生表达像政策报告或机关材料，不像普通优秀考生能说的话：" + " / ".join(policy_tone_fields[:3])})
    if instruction_fields:
        issues.append({"severity": "medium", "code": "instruction_instead_of_expression", "message": "部分字段写成训练指令，而不是可直接模仿的表达：" + " / ".join(instruction_fields[:3])})
    if len(weak_fields) >= 3:
        issues.append({"severity": "medium", "code": "weak_student_voice", "message": "多处表达缺少自然考生口吻，建议改成可复述、可仿写的话"})

    score = 100
    for issue in issues:
        severity = issue.get("severity")
        if severity == "high":
            score -= 26
        elif severity == "medium":
            score -= 12
        else:
            score -= 6
    score = max(0, min(100, score))
    high_count = sum(1 for item in issues if item.get("severity") == "high")
    medium_count = sum(1 for item in issues if item.get("severity") == "medium")
    ok = score >= 76 and high_count == 0 and medium_count <= 2
    status = "ok" if ok else ("review" if score >= 58 else "fail")

    return {
        "ok": ok,
        "status": status,
        "score": score,
        "checks": {
            "expression_field_count": len([field for field in fields if field["text"]]),
            "policy_tone_field_count": len(policy_tone_fields),
            "instruction_field_count": len(instruction_fields),
            "weak_student_voice_count": len(weak_fields),
        },
        "issues": issues,
    }
