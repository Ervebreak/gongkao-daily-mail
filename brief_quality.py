from __future__ import annotations

import re
from typing import Any


DEV_MARKERS = [
    "待补充",
    "第X条",
    "None",
    "null",
    "not_found",
    "url_status",
    "fallback_search",
    "适用场景：适用场景：",
    "Traceback",
    "Exception",
]

TRUNCATION_MARKERS = ["标…", "同步培育…", "最后还要在机制"]
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


def _repeated_lines(text: str) -> list[str]:
    seen: set[str] = set()
    repeated: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 18:
            continue
        key = re.sub(r"\s+", "", line)
        if key in seen and line not in repeated:
            repeated.append(line[:80])
        seen.add(key)
    return repeated[:5]


def _last_clause(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[，,；;。！？]", text) if part.strip()]
    return parts[-1] if parts else text.strip()


def _looks_incomplete_line(text: str) -> bool:
    value = _text(text)
    if len(value) < 8:
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

def _has_visible_truncation_marker(text: str) -> bool:
    if any(marker in text for marker in TRUNCATION_MARKERS):
        return True
    for raw in text.splitlines():
        line = raw.strip()
        if re.search(r"(\.\.\.|…|……)\s*$", line):
            return True
    return False


def evaluate_brief_cleanliness(brief: dict[str, Any], plain_text: str = "", html_body: str = "") -> dict[str, Any]:
    text = "\n".join([plain_text or "", _text(brief)])
    visible_text = "\n".join([plain_text or "", html_body or ""])
    issues: list[dict[str, str]] = []

    if len((plain_text or "").strip()) < 800:
        issues.append({"severity": "high", "code": "email_too_short", "message": "整封邮件正文过短，可能生成不完整"})
    if not html_body or "<html" not in html_body.lower():
        issues.append({"severity": "high", "code": "missing_html", "message": "HTML 邮件正文缺失或结构异常"})

    for marker in DEV_MARKERS:
        if marker in text or marker in html_body:
            issues.append({"severity": "high", "code": "dev_marker_leaked", "message": f"出现开发态痕迹：{marker}"})
            break

    if re.search(r"\[[\"'][^\"']+[\"'](?:,\s*[\"'][^\"']+[\"'])+\]", text):
        issues.append({"severity": "high", "code": "python_list_leaked", "message": "出现 Python 列表格式内容"})

    if _has_visible_truncation_marker(visible_text):
        issues.append({"severity": "high", "code": "truncated_email", "message": "整封邮件存在省略号或疑似截断表达"})

    incomplete_lines = [
        line.strip()
        for line in (plain_text or "").splitlines()
        if _looks_incomplete_line(line.strip())
    ][:3]
    if incomplete_lines:
        issues.append({"severity": "high", "code": "incomplete_sentence_line", "message": "整封邮件存在疑似半截句：" + " / ".join(incomplete_lines[:2])})

    repeated = _repeated_lines(plain_text or "")
    if repeated:
        issues.append({"severity": "medium", "code": "duplicate_lines", "message": "整封邮件存在重复行：" + " / ".join(repeated[:2])})

    long_lines = [line.strip() for line in (plain_text or "").splitlines() if len(line.strip()) > 260]
    if long_lines:
        issues.append({"severity": "medium", "code": "long_mobile_paragraph", "message": "存在过长段落，手机阅读成本较高"})

    score = 100
    for issue in issues:
        severity = issue.get("severity")
        if severity == "high":
            score -= 28
        elif severity == "medium":
            score -= 12
        else:
            score -= 6
    score = max(0, min(100, score))
    high_count = sum(1 for item in issues if item.get("severity") == "high")
    medium_count = sum(1 for item in issues if item.get("severity") == "medium")
    ok = score >= 76 and high_count == 0 and medium_count <= 2
    status = "ok" if ok else ("review" if score >= 60 else "fail")

    return {
        "ok": ok,
        "status": status,
        "score": score,
        "checks": {
            "plain_text_length": len(plain_text or ""),
            "html_length": len(html_body or ""),
            "repeated_line_count": len(repeated),
            "long_line_count": len(long_lines),
        },
        "issues": issues,
    }
