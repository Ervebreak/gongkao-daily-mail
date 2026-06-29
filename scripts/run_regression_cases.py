from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from expression_quality import evaluate_expression_quality
from lite_email_quality import evaluate_lite_email_quality
from lite_paid_cta import BANNED_LITE_CTA_WORDS
from policy_coordinate_quality import evaluate_policy_coordinate_quality
from question_quality import evaluate_daily_question
from weekly_pdf_quality import evaluate_weekly_pdf_quality


CheckerFn = Callable[[dict[str, Any]], dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return data


def _issue_codes(review: dict[str, Any]) -> list[str]:
    return [
        str(issue.get("code") or "")
        for issue in review.get("issues") or []
        if isinstance(issue, dict) and issue.get("code")
    ]


def _pass_rate(passed: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(passed / total, 4)


def _run_expression_quality(case: dict[str, Any]) -> dict[str, Any]:
    return evaluate_expression_quality(case.get("brief") if isinstance(case.get("brief"), dict) else {})


def _run_policy_coordinate_quality(case: dict[str, Any]) -> dict[str, Any]:
    return evaluate_policy_coordinate_quality(
        case.get("brief") if isinstance(case.get("brief"), dict) else {},
        plain_text=str(case.get("plain_text") or ""),
        html_body=str(case.get("html_body") or ""),
    )


def _run_lite_email_quality(case: dict[str, Any]) -> dict[str, Any]:
    return evaluate_lite_email_quality(
        case.get("latest_json") if isinstance(case.get("latest_json"), dict) else {},
        plain_text=str(case.get("plain_text") or ""),
        html_body=str(case.get("html_body") or ""),
    )


def _raw_lite_hook(latest_json: dict[str, Any]) -> str:
    brief = latest_json.get("brief") if isinstance(latest_json.get("brief"), dict) else {}
    brief_cta = brief.get("lite_paid_cta") if isinstance(brief.get("lite_paid_cta"), dict) else {}
    latest_cta = latest_json.get("lite_paid_cta") if isinstance(latest_json.get("lite_paid_cta"), dict) else {}
    for value in (
        brief_cta.get("hook"),
        latest_cta.get("hook"),
        brief.get("lite_paid_highlight"),
        latest_json.get("lite_paid_highlight"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _run_lite_cta_regression(case: dict[str, Any]) -> dict[str, Any]:
    latest_json = case.get("latest_json") if isinstance(case.get("latest_json"), dict) else {}
    raw_hook = _raw_lite_hook(latest_json)
    if any(word in raw_hook for word in BANNED_LITE_CTA_WORDS):
        return {
            "ok": False,
            "status": "review",
            "score": 70,
            "issues": [
                {
                    "severity": "medium",
                    "code": "lite_cta_over_sales",
                    "message": "raw lite CTA hook contains banned sales wording before fallback",
                }
            ],
        }
    return _run_lite_email_quality(case)


def _run_weekly_pdf_quality(case: dict[str, Any]) -> dict[str, Any]:
    return evaluate_weekly_pdf_quality(
        case.get("candidate_or_weekly_pdf") if isinstance(case.get("candidate_or_weekly_pdf"), dict) else {},
        delivery_date=str(case.get("delivery_date") or ""),
    )


def _run_question_quality(case: dict[str, Any]) -> dict[str, Any]:
    return evaluate_daily_question(case.get("brief") if isinstance(case.get("brief"), dict) else {})


CHECKERS: dict[str, CheckerFn] = {
    "expression_quality": _run_expression_quality,
    "policy_coordinate_quality": _run_policy_coordinate_quality,
    "lite_email_quality": _run_lite_email_quality,
    "lite_cta_regression": _run_lite_cta_regression,
    "weekly_pdf_quality": _run_weekly_pdf_quality,
    "question_quality": _run_question_quality,
}


def _discover_case_dirs(cases_root: Path) -> list[Path]:
    case_dirs: list[Path] = []
    seen: set[Path] = set()
    for input_path in list(cases_root.glob("*/input.json")) + list(cases_root.glob("*/*/input.json")):
        case_dir = input_path.parent
        if case_dir in seen:
            continue
        seen.add(case_dir)
        case_dirs.append(case_dir)
    return sorted(case_dirs)


def run_case(case_dir: Path) -> dict[str, Any]:
    input_path = case_dir / "input.json"
    expected_path = case_dir / "expected.json"
    case = _read_json(input_path)
    expected = _read_json(expected_path)
    checker_name = str(case.get("checker") or "").strip()
    if checker_name not in CHECKERS:
        raise ValueError(f"unsupported checker `{checker_name}` for {case_dir}")

    review = CHECKERS[checker_name](case)
    codes = _issue_codes(review)
    status = str(review.get("status") or "")

    failures: list[str] = []
    for code in expected.get("must_include_issue_codes") or []:
        if str(code) not in codes:
            failures.append(f"missing expected issue code: {code}")
    for code in expected.get("must_not_include_issue_codes") or []:
        if str(code) in codes:
            failures.append(f"unexpected issue code: {code}")
    if "expected_status" in expected and str(expected.get("expected_status")) != status:
        failures.append(f"expected status={expected.get('expected_status')} but got {status}")
    if "expected_ok" in expected and bool(expected.get("expected_ok")) != bool(review.get("ok")):
        failures.append(f"expected ok={expected.get('expected_ok')} but got {review.get('ok')}")

    try:
        relative_parts = case_dir.relative_to(ROOT / "knowledge" / "regression_cases").parts
    except ValueError:
        relative_parts = case_dir.parts
    category = relative_parts[0] if relative_parts else case_dir.name

    return {
        "case_id": str(case.get("case_id") or case_dir.name),
        "category": category,
        "checker": checker_name,
        "path": str(case_dir),
        "ok": not failures,
        "failures": failures,
        "issue_codes": codes,
        "status": status,
        "score": review.get("score"),
    }


def build_report(cases_root: Path) -> dict[str, Any]:
    case_dirs = _discover_case_dirs(cases_root)
    if not case_dirs:
        raise FileNotFoundError(f"no regression cases found under {cases_root}")

    results = [run_case(case_dir) for case_dir in case_dirs]
    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    grouped: dict[str, dict[str, int]] = {}
    for item in results:
        bucket = grouped.setdefault(item["category"], {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        if item["ok"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1

    return {
        "schema_version": 1,
        "cases_root": str(cases_root),
        "case_count": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": _pass_rate(passed, len(results)),
        "results": results,
        "categories": grouped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight regression cases for known historical quality issues.")
    parser.add_argument("--cases-root", type=Path, default=ROOT / "knowledge" / "regression_cases")
    parser.add_argument("--out", type=Path, default=ROOT / "output" / "latest_regression_cases.json")
    args = parser.parse_args()

    report = build_report(args.cases_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    for item in report["results"]:
        marker = "PASS" if item["ok"] else "FAIL"
        print(f"{marker} {item['category']}/{item['case_id']} checker={item['checker']} codes={item['issue_codes']}")
        for failure in item["failures"]:
            print(f"  - {failure}")
    print(f"summary: {report['passed']}/{report['case_count']} passed")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
