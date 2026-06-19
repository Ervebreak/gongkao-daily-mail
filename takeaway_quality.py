from __future__ import annotations

import re
from typing import Any


GENERIC_KEYWORDS = {
    "高质量发展", "基层治理", "民生保障", "科技创新", "中国式现代化", "新质生产力", "社会治理",
}
TRUNCATION_MARKERS = ["……", "...", "…", ".."]
GOLDEN_LABEL_LEAK_MARKERS = ("可用表达：", "换成考场话：", "必备金句：", "参考句式：")
GENERIC_SCENARIOS = {"适用场景", "申论", "面试", "公基", "综合分析", "对策题"}
TRUNCATED_TAILS = ("最", "畅通维", "清退四", "好人条", "探索收", "制度保", "信息透明")
DANGLING_ENDINGS = (
    "通过", "由于", "为了", "围绕", "依靠", "立足", "推动", "促进", "实现", "提升", "强化", "完善", "构建", "形成",
    "建立", "转向", "转为", "赋能", "让", "把", "更需", "更要", "成为", "重塑", "补齐", "配套", "提出从",
    "监", "重", "与", "和", "及", "并", "而", "在", "的", "为",
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


def _gold_scenario(item: Any) -> str:
    if isinstance(item, dict):
        return _text(item.get("scenario") or item.get("usage") or item.get("use_scenario"))
    return ""


def _without_sentence_punctuation(text: str) -> str:
    return _text(text).rstrip("。！？；.!?」』）】》").strip()


def _last_clause(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[，,；;。！？]", text) if part.strip()]
    return parts[-1] if parts else text.strip()


def _looks_incomplete(text: str) -> bool:
    value = _text(text)
    if not value:
        return False
    if any(marker in value for marker in TRUNCATION_MARKERS):
        return True
    if len(value) in {35, 48, 50} and not value.endswith(("。", "！", "？", "；")):
        return True
    stripped = _without_sentence_punctuation(value)
    if stripped.endswith(TRUNCATED_TAILS):
        return True
    if stripped.endswith(DANGLING_ENDINGS):
        return True
    clause = _last_clause(value)
    if clause.startswith(("让", "把")) and len(clause) <= 10:
        return True
    if clause.startswith(("通过", "依靠", "围绕", "立足", "提出从")) and len(clause) <= 18:
        return True
    if value.endswith(("，", "、", "：", "；", ",", ":", ";")):
        return True
    return False


def evaluate_takeaway(brief: dict[str, Any]) -> dict[str, Any]:
    takeaway = brief.get("today_takeaway") or {}
    if not isinstance(takeaway, dict):
        takeaway = {}

    issues: list[dict[str, str]] = []
    keywords = [_text(item) for item in _as_list(takeaway.get("keywords")) if _text(item)]
    common_points = [_text(item) for item in _as_list(takeaway.get("common_knowledge_points")) if _text(item)]
    golden = _as_list(takeaway.get("golden_sentences"))
    framework = _text(takeaway.get("framework"))

    if len(keywords) < 1:
        issues.append({"severity": "medium", "code": "missing_keywords", "message": "今日可带走缺少关键词"})
    if keywords and all(item in GENERIC_KEYWORDS or len(item) <= 2 for item in keywords):
        issues.append({"severity": "medium", "code": "generic_keywords", "message": "关键词偏泛，缺少具体考点词"})

    if not common_points:
        issues.append({"severity": "medium", "code": "missing_common_knowledge", "message": "缺少时政常识点"})
    elif len(common_points[0]) < 10:
        issues.append({"severity": "low", "code": "thin_common_knowledge", "message": "时政常识点偏短，可能不够可复述"})
    elif _looks_incomplete(common_points[0]):
        issues.append({"severity": "high", "code": "truncated_common_knowledge", "message": "时政常识点疑似半句话，需要改成完整说明", "field": "brief.today_takeaway.common_knowledge_points", "bad_text": common_points[0]})

    if len(golden) < 2:
        issues.append({"severity": "medium", "code": "too_few_golden_sentences", "message": "必备金句少于2条"})

    seen_sentences: set[str] = set()
    for idx, item in enumerate(golden[:3], start=1):
        sentence = _gold_sentence(item)
        scenario = _gold_scenario(item)
        if not sentence:
            issues.append({"severity": "high", "code": "empty_golden_sentence", "message": f"第{idx}条金句为空"})
            continue
        leaked_labels = [marker for marker in GOLDEN_LABEL_LEAK_MARKERS if marker in sentence]
        if leaked_labels:
            issues.append({"severity": "high", "code": "label_leaked_in_golden_sentence", "message": f"第{idx}条金句泄露栏目标签：{'、'.join(leaked_labels)}"})
        if _looks_incomplete(sentence):
            issues.append({"severity": "high", "code": "truncated_takeaway", "message": f"第{idx}条金句存在省略号或疑似半句话，需要重写为更短的完整句", "field": "brief.today_takeaway.golden_sentences", "bad_text": sentence})
        if len(sentence) > 45:
            issues.append({"severity": "low", "code": "golden_sentence_too_long", "message": f"第{idx}条金句偏长，不利于记忆"})
        key = sentence.replace("，", "").replace("。", "")[:30]
        if key in seen_sentences:
            issues.append({"severity": "medium", "code": "duplicate_golden_sentence", "message": "必备金句之间存在重复"})
        seen_sentences.add(key)
        if not scenario or scenario in GENERIC_SCENARIOS:
            issues.append({"severity": "medium", "code": "missing_golden_usage", "message": f"第{idx}条金句缺少具体适用题型、位置或用法"})
        elif _looks_incomplete(scenario):
            issues.append({"severity": "high", "code": "truncated_golden_usage", "message": f"第{idx}条金句适用场景疑似半句话，需要改成更短的完整说明", "field": "brief.today_takeaway.golden_sentences", "bad_text": scenario})

    if not framework:
        issues.append({"severity": "medium", "code": "missing_framework", "message": "缺少可迁移框架"})
    elif _looks_incomplete(framework):
        issues.append({"severity": "high", "code": "truncated_takeaway", "message": "可迁移框架存在省略号或疑似截断", "field": "brief.today_takeaway.framework", "bad_text": framework})

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

    return {
        "ok": ok,
        "status": status,
        "score": score,
        "checks": {
            "keyword_count": len(keywords),
            "common_knowledge_count": len(common_points),
            "golden_sentence_count": len(golden),
            "has_framework": bool(framework),
        },
        "issues": issues,
    }
