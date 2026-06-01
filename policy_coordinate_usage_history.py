from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


TZ = dt.timezone(dt.timedelta(hours=8))
DEFAULT_USAGE_HISTORY_PATH = Path(__file__).resolve().parent / "data" / "policy_coordinate_usage_history.jsonl"


def parse_usage_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def resolve_usage_history_path(path: str | Path | None = None) -> Path:
    if path is None:
        return DEFAULT_USAGE_HISTORY_PATH
    resolved = Path(path)
    return resolved if resolved.is_absolute() else Path(__file__).resolve().parent / resolved


def load_policy_coordinate_usage_history(path: str | Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    file_path = resolve_usage_history_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {
        "usage_history_path": str(file_path),
        "usage_history_read_ok": True,
        "usage_history_count": 0,
        "usage_history_bad_lines": 0,
        "usage_history_warning": "",
    }
    if not file_path.exists():
        meta["usage_history_warning"] = "usage history file missing; using empty history."
        return [], meta

    rows: list[dict[str, Any]] = []
    bad_lines = 0
    try:
        for index, raw_line in enumerate(file_path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                bad_lines += 1
                continue
            if isinstance(payload, dict):
                payload.setdefault("_line_number", index)
                rows.append(payload)
            else:
                bad_lines += 1
    except Exception as exc:
        meta.update({
            "usage_history_read_ok": False,
            "usage_history_warning": f"usage history read failed: {exc}",
        })
        return [], meta

    meta["usage_history_count"] = len(rows)
    meta["usage_history_bad_lines"] = bad_lines
    if bad_lines:
        meta["usage_history_warning"] = f"usage history skipped {bad_lines} invalid jsonl lines."
    return rows, meta


def recent_policy_coordinate_usage(
    history: list[dict[str, Any]] | None = None,
    *,
    days: int = 14,
    today: dt.date | None = None,
) -> list[dict[str, Any]]:
    today = today or dt.datetime.now(TZ).date()
    rows: list[dict[str, Any]] = []
    for item in history or []:
        item_date = parse_usage_date(str(item.get("date", "")))
        if not item_date:
            continue
        delta = (today - item_date).days
        if 0 <= delta <= days:
            rows.append({**item, "_parsed_date": item_date})
    rows.sort(key=lambda item: (item.get("_parsed_date"), str(item.get("matched_policy_id") or "")), reverse=True)
    return rows


def append_policy_coordinate_usage(
    record: dict[str, Any],
    path: str | Path | None = None,
) -> dict[str, Any]:
    file_path = resolve_usage_history_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    existing_rows, read_meta = load_policy_coordinate_usage_history(file_path)
    dedupe_key = (
        str(record.get("date") or ""),
        str(record.get("matched_policy_id") or ""),
        str(record.get("matched_qiushi_quote_id") or ""),
        str(record.get("matched_framework_id") or ""),
    )
    existing_keys = {
        (
            str(item.get("date") or ""),
            str(item.get("matched_policy_id") or ""),
            str(item.get("matched_qiushi_quote_id") or ""),
            str(item.get("matched_framework_id") or ""),
        )
        for item in existing_rows
    }
    if dedupe_key in existing_keys:
        return {
            **read_meta,
            "usage_history_write_ok": True,
            "usage_history_appended": 0,
            "usage_history_skip_reason": "duplicate_usage_record",
        }

    try:
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        return {
            **read_meta,
            "usage_history_write_ok": False,
            "usage_history_appended": 0,
            "usage_history_warning": f"usage history append failed: {exc}",
        }
    return {
        **read_meta,
        "usage_history_write_ok": True,
        "usage_history_appended": 1,
        "usage_history_skip_reason": "",
        "usage_history_warning": read_meta.get("usage_history_warning")
        if read_meta.get("usage_history_bad_lines")
        else "",
    }
