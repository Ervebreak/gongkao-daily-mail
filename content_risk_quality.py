from __future__ import annotations

import re
from html import unescape
from typing import Any

from quality_issue_schema import normalize_issue


REPEATED_TOKENS = {
    "以以": "以",
    "将将": "将",
    "对对": "对",
    "在在": "在",
    "为为": "为",
    "把把": "把",
    "从从": "从",
    "被被": "被",
    "与与": "与",
    "及及": "及",
    "由由": "由",
    "并并": "并",
}

AUTHORITY_REPLACEMENTS = {
    "收回水域管理权限": "会同有关部门依法核查并重新厘清水域管理、生态治理和经营服务边界",
    "收回企业管理权限": "对企业越权收费、违规经营行为依法核查并分类处置",
    "收回企业越权权限": "对企业越权收费、违规经营行为依法核查并分类处置",
    "全面取缔": "依法核查后分类处置",
    "一律禁止": "依法规范和审慎限制",
    "彻底整治": "依法核查、分类处置、限期整改",
    "依法严惩": "依法查处",
    "严厉打击": "依法查处和规范",
}

LEGAL_REPLACEMENTS = {
    "严禁企业商业化运作": "企业可以依法参与服务承接，但不得借公共治理名义越权定价、违规收费或转嫁治理成本",
    "绝不允许": "不得违规",
    "一律不得": "原则上不得违规",
    "必须全部": "应依法分类",
    "全部退还": "依法核查后分类处理",
    "彻底禁止": "依法规范和审慎限制",
}

POLICY_TONE_PHRASES = (
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


def _strip_html(value: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", value or "", flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _iter_brief_fields(brief: dict[str, Any]) -> list[tuple[str, str, str]]:
    fields: list[tuple[str, str, str]] = []

    def add(path: str, value: Any, module: str) -> None:
        text = _text(value)
        if text:
            fields.append((path, text, module))

    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    takeaway = brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}
    three = brief.get("today_three_things") if isinstance(brief.get("today_three_things"), dict) else {}

    add("brief.email_subject", brief.get("email_subject"), "brief")
    add("brief.today_theme", brief.get("today_theme"), "brief")
    add("brief.today_three_things", three, "brief")
    for key in ("one_sentence", "core_viewpoint", "rewritable_expression", "exam_use", "usable_for_exam", "article_framework_map"):
        add(f"brief.featured_article.{key}", featured.get(key), "featured_article")
    for key in ("question", "candidate_answer", "answer_framework", "output_sentence_template", "thirty_second_answer"):
        add(f"brief.daily_question.{key}", question.get(key), "daily_question")
    for key in ("framework", "golden_sentences", "common_knowledge_points"):
        add(f"brief.today_takeaway.{key}", takeaway.get(key), "today_takeaway")
    add("brief.quick_reads", brief.get("quick_reads"), "quick_reads")
    return fields


def _find_phrase(text: str, phrases: dict[str, str]) -> tuple[str, str] | None:
    for phrase, replacement in phrases.items():
        if phrase in text:
            return phrase, replacement
    return None


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (str(issue.get("code")), str(issue.get("field")), str(issue.get("bad_text")))
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def evaluate_content_risks(brief: dict[str, Any], plain_text: str = "", html_body: str = "") -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    fields = _iter_brief_fields(brief)

    for path, text, module in fields:
        for token, replacement in REPEATED_TOKENS.items():
            if token in text:
                issues.append(normalize_issue(
                    code="repeated_word",
                    message=f"疑似重复词：{token}",
                    severity="medium",
                    module=module,
                    field=path,
                    bad_text=token,
                    suggestion=replacement,
                    auto_fixable=True,
                ))
                break

        for bad, suggestion in AUTHORITY_REPLACEMENTS.items():
            if bad not in text:
                continue
            issues.append(normalize_issue(
                code="authority_overclaim",
                message=f"权限或治理表述过满：{bad}",
                severity="medium",
                module=module,
                field=path,
                bad_text=bad,
                suggestion=suggestion,
                auto_fixable=True,
            ))

        for bad, suggestion in LEGAL_REPLACEMENTS.items():
            if bad not in text:
                continue
            issues.append(normalize_issue(
                code="legal_overstatement",
                message=f"法律或政策表述过绝对：{bad}",
                severity="medium",
                module=module,
                field=path,
                bad_text=bad,
                suggestion=suggestion,
                auto_fixable=True,
            ))

        policy_hits = [phrase for phrase in POLICY_TONE_PHRASES if phrase in text]
        if len(policy_hits) >= 4:
            issues.append(normalize_issue(
                code="policy_tone_too_heavy",
                message="表达偏政策报告腔，建议改成考生可复述的话",
                severity="low",
                module=module,
                field=path,
                bad_text="、".join(policy_hits[:4]),
                suggestion="减少套话，改成谁来做、做什么、怎么落地",
                auto_fixable=False,
            ))

    for idx, line in enumerate((plain_text or "").splitlines(), start=1):
        text = line.strip()
        if len(text) > 260:
            issues.append(normalize_issue(
                code="mobile_paragraph_too_long",
                message="移动端段落过长，阅读压力较高",
                severity="low",
                module="plain_text",
                field=f"plain_text.line[{idx}]",
                bad_text=text[:80],
                suggestion="拆成两到三句，优先前置结论",
                auto_fixable=False,
            ))
            break

    html_text = _strip_html(html_body)
    if plain_text and html_text:
        plain_tokens = [
            token for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{4,24}", plain_text)
            if token not in {"plain", "text", "html", "body"}
        ][:24]
        html_probe = re.sub(r"\s+", "", html_text)
        hits = sum(1 for token in plain_tokens if token in html_probe)
        if len(plain_tokens) >= 6 and hits < 2:
            issues.append(normalize_issue(
                code="html_plain_mismatch",
                message="plain_text 与 html_body 可能不是同一版内容",
                severity="medium",
                module="render",
                field="html_body/plain_text",
                suggestion="修复后必须重新渲染 html_body 和 plain_text",
                auto_fixable=False,
                extra={"plain_token_count": len(plain_tokens), "html_token_hits": hits},
            ))

    issues = _dedupe_issues(issues)
    score = 100
    for issue in issues:
        if issue.get("severity") == "medium":
            score -= 12
        elif issue.get("severity") == "low":
            score -= 5
        else:
            score -= 25
    score = max(0, min(100, score))
    medium_count = sum(1 for issue in issues if issue.get("severity") == "medium")
    low_count = sum(1 for issue in issues if issue.get("severity") == "low")
    ok = medium_count == 0 and low_count <= 3
    return {
        "ok": ok,
        "status": "ok" if ok else "review",
        "score": score,
        "checks": {
            "field_count": len(fields),
            "p1_count": medium_count,
            "p2_count": low_count,
        },
        "issues": issues,
    }
