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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weekly review PDF from local daily JSON files.")
    parser.add_argument("json_files", nargs="+", help="Daily JSON files, ordered or unordered.")
    parser.add_argument("--output-dir", default="weekly_pdf_local_output", help="Directory for PDF, Typst and data JSON.")
    parser.add_argument("--start-date", default="", help="Override start date, e.g. 2026-05-25.")
    parser.add_argument("--end-date", default="", help="Override end date, e.g. 2026-05-29.")
    parser.add_argument("--api-key", default="", help="Optional DashScope API key. Prefer DASHSCOPE_API_KEY env var.")
    parser.add_argument("--model", default="", help="Optional primary model for weekly curation.")
    parser.add_argument("--fallback-model", default="", help="Optional fallback model for weekly curation.")
    parser.add_argument("--base-url", default="", help="Optional DashScope compatible-mode base URL.")
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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object.")
    payload.setdefault("date", path.stem)
    return payload


def _check_runtime_dependencies() -> None:
    missing: list[str] = []
    for module_name in ["requests"]:
        try:
            __import__(module_name)
        except ModuleNotFoundError:
            missing.append(module_name)
    if missing:
        raise RuntimeError(
            "Missing Python dependencies: "
            + ", ".join(missing)
            + ". Run: python -m pip install -r requirements.txt"
        )


def _date_from_payload(payload: dict[str, Any], fallback: str) -> str:
    brief = payload.get("brief") if isinstance(payload.get("brief"), dict) else {}
    for value in [payload.get("date"), payload.get("delivery_date"), brief.get("date"), fallback]:
        text = str(value or "").strip()
        if text:
            return text
    return fallback


def _resolve_date_range(payloads: list[dict[str, Any]], paths: list[Path], args: argparse.Namespace) -> tuple[str, str]:
    dates = [_date_from_payload(payload, path.stem) for payload, path in zip(payloads, paths)]
    parsed: list[dt.date] = []
    for value in dates:
        try:
            parsed.append(dt.date.fromisoformat(value[:10]))
        except ValueError:
            pass
    if args.start_date and args.end_date:
        return args.start_date, args.end_date
    if parsed:
        return args.start_date or min(parsed).isoformat(), args.end_date or max(parsed).isoformat()
    return args.start_date or paths[0].stem, args.end_date or paths[-1].stem


def main() -> int:
    args = _parse_args()
    _set_env_from_args(args)

    _check_runtime_dependencies()
    # Import after env setup because config.settings is created at import time.
    from weekly_typst_export import build_typst_weekly_pdf

    paths = [Path(item).expanduser().resolve() for item in args.json_files]
    pairs = [(path, _load_payload(path)) for path in paths]
    pairs.sort(key=lambda pair: _date_from_payload(pair[1], pair[0].stem))
    sorted_paths = [path for path, _payload in pairs]
    payloads = [payload for _path, payload in pairs]
    start_date, end_date = _resolve_date_range(payloads, sorted_paths, args)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"gongkao-weekly-{start_date}_to_{end_date}.pdf"
    meta = build_typst_weekly_pdf(payloads, [], pdf_path, start_date, end_date)

    data_path = pdf_path.with_suffix(".json")
    data = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else {}
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"PDF: {pdf_path}")
    print(f"DATA_JSON: {data_path}")
    print(f"TYPST: {pdf_path.with_suffix('.typ')}")
    print(
        "COUNTS: "
        f"days={len(data.get('days') or [])}, "
        f"exam_map_cards={len(data.get('exam_map_cards') or [])}, "
        f"selected_expression_rows={len(data.get('selected_expression_rows') or [])}, "
        f"material_cards={len(data.get('material_cards') or [])}, "
        f"practice_questions={len(data.get('practice_questions') or [])}"
    )
    if data.get("warnings"):
        print("WARNINGS:")
        for warning in data.get("warnings") or []:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
