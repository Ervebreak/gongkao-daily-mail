from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brief_quality import evaluate_brief_cleanliness
from brief_schema import ensure_brief_schema
from email_renderer import render_email_html, render_plain_text
from duplication_quality import evaluate_duplication
from expression_quality import evaluate_expression_quality
from framework_quality import evaluate_framework_map
from question_quality import evaluate_daily_question
from quick_reads_quality import evaluate_quick_reads
from takeaway_quality import evaluate_takeaway


P0_CODES = {
    "missing_question",
    "missing_task",
    "too_broad",
    "missing_candidate_answer",
    "truncated_answer",
    "isolated_number",
    "incomplete_sentence",
    "incomplete_label",
    "exam_migration_step",
    "missing_main_line",
    "too_few_steps",
    "empty_golden_sentence",
    "truncated_takeaway",
    "email_too_short",
    "missing_html",
    "dev_marker_leaked",
    "python_list_leaked",
    "truncated_email",
    "quick_read_dev_marker",
    "empty_quick_read",
    "quick_reads_all_news_summary",
    "dev_marker_repeated",
    "abnormal_copy_duplication",
    "expression_dev_marker",
    "expression_truncated",
}


MODULE_LABELS = {
    "daily_question": "今日一题",
    "framework_map": "框架图",
    "today_takeaway": "今日可带走",
    "brief_cleanliness": "整封邮件清洁度",
    "quick_reads": "速读考试价值",
    "duplication": "跨模块重复",
    "expression_quality": "考生表达质感",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def issue_level(module: str, issue: dict[str, Any]) -> str:
    severity = str(issue.get("severity") or "").lower()
    code = str(issue.get("code") or "")
    if severity == "high" and code in P0_CODES:
        return "P0"
    if severity in {"high", "medium"}:
        return "P1"
    return "P2"


def normalize_module_result(module: str, result: dict[str, Any]) -> dict[str, Any]:
    issues = []
    for issue in result.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        level = issue_level(module, issue)
        issues.append(
            {
                "level": level,
                "severity": issue.get("severity"),
                "code": issue.get("code"),
                "message": issue.get("message"),
            }
        )
    p0_count = sum(1 for item in issues if item.get("level") == "P0")
    p1_count = sum(1 for item in issues if item.get("level") == "P1")
    p2_count = sum(1 for item in issues if item.get("level") == "P2")
    if p0_count:
        status = "block"
    elif p1_count:
        status = "review"
    else:
        status = "pass"
    return {
        "label": MODULE_LABELS.get(module, module),
        "status": status,
        "ok": bool(result.get("ok")),
        "score": result.get("score"),
        "p0_count": p0_count,
        "p1_count": p1_count,
        "p2_count": p2_count,
        "issues": issues,
        "raw": result,
    }


def summarize_report(modules: dict[str, dict[str, Any]]) -> dict[str, Any]:
    p0_count = sum(item.get("p0_count", 0) for item in modules.values())
    p1_count = sum(item.get("p1_count", 0) for item in modules.values())
    p2_count = sum(item.get("p2_count", 0) for item in modules.values())
    p0_issues = []
    rewrite_required_modules = []
    for module, result in modules.items():
        if result.get("status") in {"block", "review"} and module != "brief_cleanliness":
            rewrite_required_modules.append(module)
        for issue in result.get("issues") or []:
            if issue.get("level") == "P0":
                p0_issues.append(
                    {
                        "module": module,
                        "code": issue.get("code"),
                        "message": issue.get("message"),
                    }
                )
    if p0_count:
        overall = "block"
        send_decision = "block"
    elif p1_count:
        overall = "review"
        send_decision = "allow_after_rewrite"
    else:
        overall = "pass"
        send_decision = "allow"
    return {
        "overall": overall,
        "p0_count": p0_count,
        "p1_count": p1_count,
        "p2_count": p2_count,
        "p0_issues": p0_issues[:12],
        "send_decision": send_decision,
        "rewrite_required_modules": rewrite_required_modules,
    }


def build_report(brief: dict[str, Any], plain_text: str | None = None, html_body: str | None = None, today: str | None = None) -> dict[str, Any]:
    today = today or str(brief.get("date") or dt.datetime.now().date())
    brief, schema_warnings = ensure_brief_schema(brief, today)
    if plain_text is None:
        plain_text = render_plain_text(brief)
    if html_body is None:
        html_body = render_email_html(brief)

    raw_results = {
        "daily_question": evaluate_daily_question(brief),
        "framework_map": evaluate_framework_map(brief),
        "today_takeaway": evaluate_takeaway(brief),
        "brief_cleanliness": evaluate_brief_cleanliness(brief, plain_text, html_body),
        "quick_reads": evaluate_quick_reads(brief),
        "duplication": evaluate_duplication(brief),
        "expression_quality": evaluate_expression_quality(brief),
    }
    modules = {
        module: normalize_module_result(module, result)
        for module, result in raw_results.items()
    }
    summary = summarize_report(modules)
    return {
        "schema_version": 1,
        **summary,
        "schema_warnings": schema_warnings,
        "modules": modules,
        "rendered": {
            "plain_text_length": len(plain_text or ""),
            "html_length": len(html_body or ""),
        },
    }


def unwrap_input_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None, str | None, str | None, str]:
    """Accept either a raw brief JSON or a full candidate JSON wrapper."""
    if isinstance(payload.get("brief"), dict):
        return (
            payload["brief"],
            str(payload.get("plain_text") or "") or None,
            str(payload.get("html_body") or "") or None,
            str(payload.get("delivery_date") or payload.get("date") or "") or None,
            "candidate",
        )
    return payload, None, None, str(payload.get("date") or "") or None, "brief"


def default_input_path() -> Path:
    try:
        from config import settings

        return settings.output_dir / "latest_brief.json"
    except Exception:
        return ROOT / "output" / "latest_brief.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a daily brief and output the unified Harness quality gate report.")
    parser.add_argument("--input", "-i", type=Path, default=default_input_path(), help="Path to brief JSON. Defaults to OUTPUT_DIR/latest_brief.json.")
    parser.add_argument("--plain-text", type=Path, help="Optional pre-rendered plain text email body.")
    parser.add_argument("--html", type=Path, help="Optional pre-rendered HTML email body.")
    parser.add_argument("--output", "-o", type=Path, help="Path to write JSON report. Defaults to input directory/latest_quality.json.")
    parser.add_argument("--date", help="Date used when normalizing an incomplete brief. Defaults to brief.date or today.")
    parser.add_argument("--no-exit-code", action="store_true", help="Always exit 0 after writing the report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        print(f"brief input not found: {args.input}", file=sys.stderr)
        return 2

    payload = load_json(args.input)
    if not isinstance(payload, dict):
        print("brief input root must be a JSON object.", file=sys.stderr)
        return 2

    brief, embedded_plain_text, embedded_html_body, embedded_date, input_type = unwrap_input_payload(payload)
    plain_text = args.plain_text.read_text(encoding="utf-8") if args.plain_text else embedded_plain_text
    html_body = args.html.read_text(encoding="utf-8") if args.html else embedded_html_body
    report = build_report(brief, plain_text=plain_text, html_body=html_body, today=args.date or embedded_date)
    report["input_type"] = input_type
    output = args.output or (args.input.parent / "latest_quality.json")
    write_json(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    if args.no_exit_code:
        return 0
    if report["overall"] == "block":
        return 2
    if report["overall"] == "review":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
