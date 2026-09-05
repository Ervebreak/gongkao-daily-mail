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


def evaluate_brief_cleanliness(brief: dict[str, Any], plain_text: str = "", html_body: str = "") -> dict[str, Any]:
    # Development metadata intentionally lives in the structured brief. A leak
    # exists only when it reaches a rendered user-visible output.
    text = plain_text or ""
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
