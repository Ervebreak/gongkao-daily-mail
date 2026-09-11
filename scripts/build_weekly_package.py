from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


EXPECTED_PRACTICE_TYPES = (
    "面试综合分析题",
    "对策建议题",
    "申论作文分论点展开题",
)

INTERNAL_MARKERS = (
    "不新增精读文章",
    "周日复盘版",
    "宁缺毋滥",
    "不为凑数补卡",
    "内部测试",
    "debug",
    "candidate",
    "quality gate",
    "P0",
    "后台字段",
    "JSON",
    "TODO",
    "待优化",
    "修改痕迹",
    "划线",
)


class PackageBlocked(RuntimeError):
    """Raised when the generated package does not satisfy delivery requirements."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a complete weekly review package from local daily JSON files. "
            "This command is side-effect-free: it never uploads OSS objects, sends email, "
            "or writes a candidate record."
        )
    )
    parser.add_argument("json_files", nargs="+", help="Daily JSON files, ordered or unordered.")
    parser.add_argument(
        "--output-dir",
        default="weekly_package_output",
        help="Directory for PDFs, Typst sources, data JSON and delivery report.",
    )
    parser.add_argument("--start-date", default="", help="Override start date, e.g. 2026-09-07.")
    parser.add_argument("--end-date", default="", help="Override end date, e.g. 2026-09-12.")
    parser.add_argument("--api-key", default="", help="Optional DashScope API key. Prefer DASHSCOPE_API_KEY env var.")
    parser.add_argument("--model", default="", help="Optional primary model for weekly curation.")
    parser.add_argument("--fallback-model", default="", help="Optional fallback model for weekly curation.")
    parser.add_argument("--base-url", default="", help="Optional DashScope compatible-mode base URL.")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help=(
            "Generate debug artifacts even when weekly enrichment is incomplete. "
            "The delivery report will still be marked blocked; this option only prevents a non-zero exit code."
        ),
    )
    return parser.parse_args()


def _set_env_from_args(args: argparse.Namespace) -> None:
    if args.api_key:
        os.environ["DASHSCOPE_API_KEY"] = args.api_key
    if args.model:
        os.environ["CONTENT_QUALITY_LLM_MODEL"] = args.model
    if args.fallback_model:
        os.environ["CONTENT_QUALITY_LLM_FALLBACK_MODEL"] = args.fallback_model
    if args.base_url:
        os.environ["DASHSCOPE_BASE_URL"] = args.base_url


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object.")
    payload.setdefault("date", path.stem)
    return payload


def _date_from_payload(payload: dict[str, Any], fallback: str) -> str:
    brief = payload.get("brief") if isinstance(payload.get("brief"), dict) else {}
    for value in [payload.get("date"), payload.get("delivery_date"), brief.get("date"), fallback]:
        text = str(value or "").strip()
        if text:
            return text[:10]
    return fallback[:10]


def _parse_iso_date(value: str, label: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value[:10])
    except Exception as exc:
        raise ValueError(f"Invalid {label}: {value!r}") from exc


def _resolve_date_range(
    payloads: list[dict[str, Any]],
    paths: list[Path],
    args: argparse.Namespace,
) -> tuple[str, str, list[str]]:
    dates = [_date_from_payload(payload, path.stem) for payload, path in zip(payloads, paths)]
    parsed = [_parse_iso_date(value, "daily delivery date") for value in dates]
    start = _parse_iso_date(args.start_date, "start date") if args.start_date else min(parsed)
    end = _parse_iso_date(args.end_date, "end date") if args.end_date else max(parsed)
    if start > end:
        raise ValueError(f"Invalid date range: {start.isoformat()} > {end.isoformat()}")
    outside = [value for value, day in zip(dates, parsed) if day < start or day > end]
    if outside:
        raise ValueError(f"Daily JSON date outside requested range: {', '.join(outside)}")
    return start.isoformat(), end.isoformat(), dates


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        code = str(issue.get("code") or "")
        message = str(issue.get("message") or "")
        key = (code, message)
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def _issue(code: str, message: str, *, severity: str = "high", detail: Any = None) -> dict[str, Any]:
    row: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if detail not in (None, "", [], {}):
        row["detail"] = detail
    return row


def evaluate_input_gate(
    dates: list[str],
    *,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    duplicates = sorted({value for value in dates if dates.count(value) > 1})
    if duplicates:
        issues.append(_issue("weekly_package_duplicate_dates", "Daily JSON contains duplicate delivery dates.", detail=duplicates))
    if not dates:
        issues.append(_issue("weekly_package_no_daily_json", "No daily JSON files were loaded."))
    if start_date and end_date and start_date > end_date:
        issues.append(_issue("weekly_package_invalid_date_range", "Weekly package date range is invalid."))
    return issues


def evaluate_content_gate(data: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    days = data.get("days") if isinstance(data.get("days"), list) else []
    exam_map_cards = data.get("exam_map_cards") if isinstance(data.get("exam_map_cards"), list) else []
    expressions = data.get("selected_expression_rows") if isinstance(data.get("selected_expression_rows"), list) else []
    material_cards = data.get("material_cards") if isinstance(data.get("material_cards"), list) else []
    questions = data.get("practice_questions") if isinstance(data.get("practice_questions"), list) else []

    if not days:
        issues.append(_issue("weekly_package_no_days", "Shared weekly data contains no normalized daily content."))
    if not 4 <= len(exam_map_cards) <= 6:
        issues.append(
            _issue(
                "weekly_package_exam_map_count",
                "Weekly package must contain 4 to 6 exam map cards.",
                detail=len(exam_map_cards),
            )
        )
    if not 8 <= len(expressions) <= 15:
        issues.append(
            _issue(
                "weekly_package_expression_count",
                "Weekly package must contain 8 to 15 selected expression rows.",
                detail=len(expressions),
            )
        )
    if len(material_cards) > 3:
        issues.append(
            _issue(
                "weekly_package_material_count",
                "Weekly package may contain at most 3 material cards.",
                detail=len(material_cards),
            )
        )
    if len(questions) != 3:
        issues.append(
            _issue(
                "weekly_package_practice_count",
                "Weekly package must contain exactly 3 practice questions.",
                detail=len(questions),
            )
        )
    question_types = [str(row.get("question_type") or "").strip() for row in questions if isinstance(row, dict)]
    if len(questions) == 3 and tuple(sorted(question_types)) != tuple(sorted(EXPECTED_PRACTICE_TYPES)):
        issues.append(
            _issue(
                "weekly_package_practice_types",
                "Practice questions must contain exactly one of each required question type.",
                detail=question_types,
            )
        )

    for index, card in enumerate(material_cards, start=1):
        if not isinstance(card, dict):
            issues.append(_issue("weekly_package_material_invalid", f"Material card {index} is not an object."))
            continue
        required = {
            "material_summary": card.get("material_summary"),
            "usage_examples": card.get("usage_examples"),
            "use_boundary": card.get("use_boundary") or card.get("usage_boundary"),
            "source_articles": card.get("source_articles") or card.get("source_article"),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            issues.append(
                _issue(
                    "weekly_package_material_incomplete",
                    f"Material card {index} is missing required delivery fields.",
                    detail=missing,
                )
            )
        examples = card.get("usage_examples") if isinstance(card.get("usage_examples"), list) else []
        if len(examples) < 2:
            issues.append(
                _issue(
                    "weekly_package_material_examples",
                    f"Material card {index} must contain at least 2 usage examples.",
                    detail=len(examples),
                )
            )

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            issues.append(_issue("weekly_package_practice_invalid", f"Practice question {index} is not an object."))
            continue
        missing = [
            key
            for key in ("question_type", "question", "answer_hint", "mini_reference_answer", "suggested_golden_sentences")
            if not question.get(key)
        ]
        if missing:
            issues.append(
                _issue(
                    "weekly_package_practice_incomplete",
                    f"Practice question {index} is missing required delivery fields.",
                    detail=missing,
                )
            )

    return issues


def _read_text(path: str | Path | None) -> str:
    if not path:
        return ""
    target = Path(path)
    if not target.exists() or not target.is_file():
        return ""
    try:
        return target.read_text(encoding="utf-8")
    except Exception:
        return ""


def _pdf_looks_valid(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.stat().st_size < 32:
        return False
    try:
        return path.read_bytes()[:5] == b"%PDF-"
    except Exception:
        return False


def evaluate_artifact_gate(
    *,
    full_pdf: Path,
    preview_pdf: Path,
    full_typ: Path,
    preview_typ: Path,
    shared_data_path: Path,
    report_path: Path,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expected_full = f"gongkao-weekly-{start_date}_to_{end_date}.pdf"
    expected_preview = f"gongkao-weekly-{start_date}_to_{end_date}-lite-preview.pdf"
    if full_pdf.name != expected_full:
        issues.append(_issue("weekly_package_full_filename", "Full PDF filename does not match date range.", detail=full_pdf.name))
    if preview_pdf.name != expected_preview:
        issues.append(_issue("weekly_package_preview_filename", "Preview PDF filename does not match date range.", detail=preview_pdf.name))
    if not _pdf_looks_valid(full_pdf):
        issues.append(_issue("weekly_package_full_pdf_invalid", "Full weekly PDF is missing or invalid."))
    if not _pdf_looks_valid(preview_pdf):
        issues.append(_issue("weekly_package_preview_pdf_invalid", "Lite preview PDF is missing or invalid."))
    for label, path in (("full Typst", full_typ), ("preview Typst", preview_typ), ("shared data JSON", shared_data_path)):
        if not path.exists() or not path.is_file() or path.stat().st_size == 0:
            issues.append(_issue("weekly_package_artifact_missing", f"Required {label} artifact is missing.", detail=str(path)))

    visible_text = "\n".join([_read_text(full_typ), _read_text(preview_typ)])
    marker = next((item for item in INTERNAL_MARKERS if item.lower() in visible_text.lower()), "")
    if marker:
        issues.append(
            _issue(
                "weekly_package_internal_marker_leaked",
                f"Generated Typst contains an internal-only marker: {marker}.",
                detail=marker,
            )
        )
    preview_text = _read_text(preview_typ)
    if "考生版参考答案" in preview_text or "mini_reference_answer" in preview_text:
        issues.append(
            _issue(
                "weekly_package_preview_answer_leak",
                "Lite preview contains a full-answer marker that should not be exposed.",
            )
        )
    if report_path.suffix.lower() != ".json":
        issues.append(_issue("weekly_package_report_filename", "Delivery report must be a JSON file."))
    return issues


def build_delivery_report(
    *,
    start_date: str,
    end_date: str,
    source_files: list[Path],
    output_dir: Path,
    shared_data: dict[str, Any] | None,
    artifacts: dict[str, Any],
    issues: list[dict[str, Any]],
    runtime_error: str = "",
) -> dict[str, Any]:
    data = shared_data or {}
    warnings = [str(item) for item in data.get("warnings") or []]
    high_count = sum(1 for item in issues if str(item.get("severity") or "").lower() == "high")
    status = "blocked" if runtime_error or high_count else "pass"
    return {
        "schema_version": 1,
        "status": status,
        "side_effect_free": True,
        "start_date": start_date,
        "end_date": end_date,
        "source_files": [str(path) for path in source_files],
        "output_dir": str(output_dir),
        "counts": {
            "days": len(data.get("days") or []),
            "exam_map_cards": len(data.get("exam_map_cards") or []),
            "selected_expression_rows": len(data.get("selected_expression_rows") or []),
            "material_cards": len(data.get("material_cards") or []),
            "practice_questions": len(data.get("practice_questions") or []),
        },
        "warnings": warnings,
        "issues": _dedupe_issues(issues),
        "runtime_error": runtime_error,
        "artifacts": artifacts,
        "prohibited_actions": {
            "oss_upload": False,
            "email_send": False,
            "candidate_write": False,
        },
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    _set_env_from_args(args)

    source_paths = [Path(item).expanduser().resolve() for item in args.json_files]
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "weekly_pdf_delivery_report.json"

    start_date = args.start_date[:10] if args.start_date else ""
    end_date = args.end_date[:10] if args.end_date else ""
    shared_data: dict[str, Any] | None = None
    artifacts: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []
    runtime_error = ""

    try:
        pairs = [(path, _load_payload(path)) for path in source_paths]
        pairs.sort(key=lambda pair: _date_from_payload(pair[1], pair[0].stem))
        sorted_paths = [path for path, _payload in pairs]
        payloads = [payload for _path, payload in pairs]
        start_date, end_date, dates = _resolve_date_range(payloads, sorted_paths, args)
        issues.extend(evaluate_input_gate(dates, start_date=start_date, end_date=end_date))

        # Import only after environment overrides are applied because config.settings
        # is instantiated at import time. These modules build local data and files;
        # this entrypoint deliberately does not import weekly_report, candidate_store,
        # email_sender or OSS upload helpers.
        from weekly_typst_export import (
            build_data,
            build_typst_weekly_pdf,
            build_typst_weekly_preview_pdf,
        )

        shared_data = build_data(payloads, start_date, end_date, [])
        issues.extend(evaluate_content_gate(shared_data))

        base_name = f"gongkao-weekly-{start_date}_to_{end_date}"
        full_pdf = output_dir / f"{base_name}.pdf"
        preview_pdf = output_dir / f"{base_name}-lite-preview.pdf"
        shared_data_path = output_dir / f"{base_name}-data.json"
        _write_json(shared_data_path, shared_data)

        full_meta = build_typst_weekly_pdf(
            payloads,
            [],
            full_pdf,
            start_date,
            end_date,
            data=shared_data,
        )
        preview_meta = build_typst_weekly_preview_pdf(
            payloads,
            [],
            preview_pdf,
            start_date,
            end_date,
            data=shared_data,
        )

        full_typ = Path(str(full_meta.get("typ_path") or full_pdf.with_suffix(".typ")))
        preview_typ = Path(str(preview_meta.get("typ_path") or preview_pdf.with_suffix(".typ")))
        artifacts = {
            "full_pdf": str(full_pdf),
            "lite_preview_pdf": str(preview_pdf),
            "shared_data_json": str(shared_data_path),
            "full_typst": str(full_typ),
            "lite_preview_typst": str(preview_typ),
            "full_renderer_data_json": str(full_meta.get("data_path") or ""),
            "lite_preview_renderer_data_json": str(preview_meta.get("data_path") or ""),
            "delivery_report": str(report_path),
            "pdf_engine": "typst",
        }
        issues.extend(
            evaluate_artifact_gate(
                full_pdf=full_pdf,
                preview_pdf=preview_pdf,
                full_typ=full_typ,
                preview_typ=preview_typ,
                shared_data_path=shared_data_path,
                report_path=report_path,
                start_date=start_date,
                end_date=end_date,
            )
        )
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
        issues.append(_issue("weekly_package_runtime_error", "Weekly package generation failed.", detail=runtime_error))

    report = build_delivery_report(
        start_date=start_date,
        end_date=end_date,
        source_files=source_paths,
        output_dir=output_dir,
        shared_data=shared_data,
        artifacts=artifacts,
        issues=issues,
        runtime_error=runtime_error,
    )
    _write_json(report_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] == "pass":
        return 0
    return 0 if args.allow_incomplete else 2


if __name__ == "__main__":
    raise SystemExit(main())
