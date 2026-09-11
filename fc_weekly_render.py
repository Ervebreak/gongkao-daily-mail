from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from scripts.build_weekly_package import (
    EXPECTED_ENRICHMENT_KEYS,
    build_delivery_report,
    build_shared_data,
    evaluate_artifact_gate,
    evaluate_content_gate,
)


EXPECTED_REQUEST_KEYS = frozenset({"start_date", "end_date", "days", "enrichment"})
OPTIONAL_ENRICHMENT_KEYS = frozenset({"warnings"})
DEFAULT_MAX_ZIP_BYTES = 4_000_000


class WeeklyRenderError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _json_response(status_code: int, code: str, message: str) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"},
        "isBase64Encoded": False,
        "body": json.dumps(
            {"status": "blocked", "issue_code": code, "message": message},
            ensure_ascii=False,
        ),
    }


def _headers(event: Any) -> dict[str, str]:
    if not isinstance(event, dict) or not isinstance(event.get("headers"), dict):
        return {}
    return {str(key).lower(): str(value) for key, value in event["headers"].items()}


def _authorized(event: Any) -> bool:
    expected = os.environ.get("WEEKLY_RENDER_TOKEN", "")
    if not expected:
        return False
    authorization = _headers(event).get("authorization", "")
    scheme, separator, supplied = authorization.partition(" ")
    return bool(
        separator
        and scheme.lower() == "bearer"
        and supplied
        and hmac.compare_digest(supplied, expected)
    )


def _request_payload(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise WeeklyRenderError("weekly_render_input_invalid", "Request event must be an object.")
    raw: Any = event.get("body", event)
    if event.get("isBase64Encoded") is True:
        if not isinstance(raw, str):
            raise WeeklyRenderError("weekly_render_input_invalid", "Base64 request body must be a string.")
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except Exception as exc:
            raise WeeklyRenderError("weekly_render_input_invalid", "Request body is not valid base64 UTF-8.") from exc
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WeeklyRenderError("weekly_render_input_invalid", "Request body must be UTF-8.") from exc
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WeeklyRenderError("weekly_render_input_invalid", "Request body is not valid JSON.") from exc
    if not isinstance(raw, dict):
        raise WeeklyRenderError("weekly_render_input_invalid", "Request body must be a JSON object.")
    return raw


def _iso_date(value: Any, label: str) -> dt.date:
    if not isinstance(value, str) or len(value) != 10:
        raise WeeklyRenderError("weekly_render_date_invalid", f"{label} must use YYYY-MM-DD.")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise WeeklyRenderError("weekly_render_date_invalid", f"{label} must be a valid date.") from exc
    if parsed.isoformat() != value:
        raise WeeklyRenderError("weekly_render_date_invalid", f"{label} must use YYYY-MM-DD.")
    return parsed


def _daily_date(day: dict[str, Any], index: int) -> str:
    brief = day.get("brief") if isinstance(day.get("brief"), dict) else {}
    values = [
        value
        for value in (day.get("date"), day.get("delivery_date"), brief.get("date"))
        if value not in (None, "")
    ]
    if not values:
        raise WeeklyRenderError(
            "weekly_render_date_invalid",
            f"days[{index}] has no date, delivery_date or brief.date.",
        )
    normalized = []
    for value in values:
        parsed = _iso_date(value, f"days[{index}] date")
        normalized.append(parsed.isoformat())
    if len(set(normalized)) != 1:
        raise WeeklyRenderError(
            "weekly_render_date_invalid",
            f"days[{index}] contains conflicting internal dates.",
        )
    return normalized[0]


def _validate_request(payload: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], dict[str, Any]]:
    missing = sorted(EXPECTED_REQUEST_KEYS - payload.keys())
    unknown = sorted(payload.keys() - EXPECTED_REQUEST_KEYS)
    if missing or unknown:
        detail = []
        if missing:
            detail.append(f"missing keys: {', '.join(missing)}")
        if unknown:
            detail.append(f"unknown keys: {', '.join(unknown)}")
        raise WeeklyRenderError("weekly_render_input_invalid", "; ".join(detail))

    start = _iso_date(payload["start_date"], "start_date")
    end = _iso_date(payload["end_date"], "end_date")
    if start > end:
        raise WeeklyRenderError("weekly_render_date_invalid", "start_date must not be after end_date.")

    days = payload["days"]
    if not isinstance(days, list) or len(days) != 6:
        raise WeeklyRenderError("weekly_render_input_invalid", "days must contain exactly 6 JSON objects.")
    if any(not isinstance(day, dict) for day in days):
        raise WeeklyRenderError("weekly_render_input_invalid", "Every days item must be a JSON object.")

    dates = [_daily_date(day, index) for index, day in enumerate(days)]
    if len(set(dates)) != 6:
        raise WeeklyRenderError("weekly_render_date_invalid", "Daily JSON dates must be unique.")
    if dates != sorted(dates):
        raise WeeklyRenderError("weekly_render_date_invalid", "Daily JSON objects must be sorted by date.")
    outside = [value for value in dates if value < start.isoformat() or value > end.isoformat()]
    if outside:
        raise WeeklyRenderError(
            "weekly_render_date_invalid",
            f"Daily JSON date is outside the requested range: {', '.join(outside)}.",
        )

    enrichment = payload["enrichment"]
    if not isinstance(enrichment, dict):
        raise WeeklyRenderError("weekly_render_enrichment_invalid", "enrichment must be a JSON object.")
    expected = set(EXPECTED_ENRICHMENT_KEYS)
    enrichment_missing = sorted(expected - enrichment.keys())
    enrichment_unknown = sorted(enrichment.keys() - expected - OPTIONAL_ENRICHMENT_KEYS)
    if enrichment_missing or enrichment_unknown:
        detail = []
        if enrichment_missing:
            detail.append(f"missing keys: {', '.join(enrichment_missing)}")
        if enrichment_unknown:
            detail.append(f"unknown keys: {', '.join(enrichment_unknown)}")
        raise WeeklyRenderError("weekly_render_enrichment_invalid", "; ".join(detail))
    invalid = [key for key in EXPECTED_ENRICHMENT_KEYS if not isinstance(enrichment.get(key), list)]
    if invalid or ("warnings" in enrichment and not isinstance(enrichment["warnings"], list)):
        raise WeeklyRenderError(
            "weekly_render_enrichment_invalid",
            "Every enrichment field must be an array.",
        )
    normalized_enrichment = {
        key: enrichment[key]
        for key in EXPECTED_ENRICHMENT_KEYS
    }
    normalized_enrichment["warnings"] = enrichment.get("warnings", [])
    return start.isoformat(), end.isoformat(), days, normalized_enrichment


def _typst_version(binary: str) -> str:
    try:
        result = subprocess.run(
            [binary, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        raise WeeklyRenderError(
            "weekly_render_typst_unavailable",
            "Typst is installed but its version could not be read.",
            http_status=503,
        ) from exc
    return (result.stdout or result.stderr).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _max_zip_bytes() -> int:
    raw = os.environ.get("WEEKLY_RENDER_MAX_ZIP_BYTES", str(DEFAULT_MAX_ZIP_BYTES))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_ZIP_BYTES
    return max(1, value)


def _render(start_date: str, end_date: str, days: list[dict[str, Any]], enrichment: dict[str, Any]) -> tuple[bytes, str]:
    # The directory is deleted on every success and failure path. No production
    # archive, candidate, subscriber, OSS or mail module is imported here.
    with tempfile.TemporaryDirectory(prefix="weekly-render-", dir="/tmp") as temp_name:
        root = Path(temp_name)
        output_dir = root / "output"
        output_dir.mkdir()
        source_paths: list[Path] = []
        for day in days:
            date = _daily_date(day, len(source_paths))
            path = root / f"{date}.json"
            _write_json(path, day)
            source_paths.append(path)
        _write_json(root / "weekly_enrichment.json", enrichment)

        import weekly_typst_export as weekly_export

        typst = weekly_export.find_typst_binary()
        if not typst:
            raise WeeklyRenderError(
                "weekly_render_typst_unavailable",
                "Typst is not available in PATH, /opt/bin/typst or bin/typst.",
                http_status=503,
            )
        typst_version = _typst_version(typst)

        shared_data = build_shared_data(
            weekly_export,
            days,
            start_date,
            end_date,
            enrichment_override=enrichment,
        )
        content_issues = evaluate_content_gate(shared_data)
        if content_issues:
            codes = sorted({str(issue.get("code") or "") for issue in content_issues})
            raise WeeklyRenderError(
                "weekly_render_enrichment_invalid",
                f"Weekly content gate failed: {', '.join(codes)}.",
            )

        base_name = f"gongkao-weekly-{start_date}_to_{end_date}"
        full_pdf = output_dir / f"{base_name}.pdf"
        lite_pdf = output_dir / f"{base_name}-lite-preview.pdf"
        shared_data_path = output_dir / f"{base_name}-data.json"
        report_path = output_dir / "weekly_pdf_delivery_report.json"
        _write_json(shared_data_path, shared_data)

        try:
            full_meta = weekly_export.build_typst_weekly_pdf(
                days, [], full_pdf, start_date, end_date, data=shared_data
            )
            lite_meta = weekly_export.build_typst_weekly_preview_pdf(
                days, [], lite_pdf, start_date, end_date, data=shared_data
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise WeeklyRenderError(
                "weekly_render_compile_failed",
                "Typst compilation failed.",
                http_status=500,
            ) from exc
        except RuntimeError as exc:
            code = "weekly_render_typst_unavailable" if "typst" in str(exc).lower() and "未找到" in str(exc) else "weekly_render_compile_failed"
            raise WeeklyRenderError(code, "Typst rendering failed.", http_status=503 if code.endswith("unavailable") else 500) from exc

        full_typ = Path(str(full_meta.get("typ_path") or full_pdf.with_suffix(".typ")))
        lite_typ = Path(str(lite_meta.get("typ_path") or lite_pdf.with_suffix(".typ")))
        artifact_issues = evaluate_artifact_gate(
            full_pdf=full_pdf,
            preview_pdf=lite_pdf,
            full_typ=full_typ,
            preview_typ=lite_typ,
            shared_data_path=shared_data_path,
            report_path=report_path,
            start_date=start_date,
            end_date=end_date,
        )
        if artifact_issues:
            codes = sorted({str(issue.get("code") or "") for issue in artifact_issues})
            raise WeeklyRenderError(
                "weekly_render_compile_failed",
                f"Rendered artifact gate failed: {', '.join(codes)}.",
                http_status=500,
            )

        artifacts = {
            "full_pdf": full_pdf.name,
            "lite_preview_pdf": lite_pdf.name,
            "delivery_report": report_path.name,
            "pdf_engine": "typst",
            "sha256": {full_pdf.name: _sha256(full_pdf), lite_pdf.name: _sha256(lite_pdf)},
        }
        report = build_delivery_report(
            start_date=start_date,
            end_date=end_date,
            source_files=[Path(path.name) for path in source_paths],
            output_dir=Path("."),
            shared_data=shared_data,
            artifacts=artifacts,
            issues=[],
            generation_mode="offline_enrichment",
            enrichment_json="weekly_enrichment.json",
        )
        report.update(
            {
                "renderer": "typst",
                "typst_version": typst_version,
                "offline": True,
                "allow_incomplete": False,
                "model_enrichment_disabled": True,
                "model_api_call": False,
                "prohibited_actions": {
                    "oss_upload": False,
                    "email_send": False,
                    "candidate_write": False,
                    "archive_read": False,
                    "web_fetch": False,
                },
            }
        )
        _write_json(report_path, report)

        zip_path = root / f"{base_name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for artifact in (full_pdf, lite_pdf, report_path):
                archive.write(artifact, artifact.name)
        zip_bytes = zip_path.read_bytes()
        if len(zip_bytes) > _max_zip_bytes():
            raise WeeklyRenderError(
                "weekly_render_response_too_large",
                "Rendered ZIP exceeds the configured synchronous response limit.",
                http_status=413,
            )
        return zip_bytes, zip_path.name


def handler(event: Any, context: Any) -> dict[str, Any]:
    del context
    if not _authorized(event):
        return _json_response(401, "weekly_render_auth_failed", "Unauthorized.")
    try:
        payload = _request_payload(event)
        start_date, end_date, days, enrichment = _validate_request(payload)
        zip_bytes, filename = _render(start_date, end_date, days, enrichment)
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/zip",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
            "isBase64Encoded": True,
            "body": base64.b64encode(zip_bytes).decode("ascii"),
        }
    except WeeklyRenderError as exc:
        return _json_response(exc.http_status, exc.code, exc.message)
    except Exception:
        return _json_response(500, "weekly_render_compile_failed", "Weekly PDF rendering failed.")

