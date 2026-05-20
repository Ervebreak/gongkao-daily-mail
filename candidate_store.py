from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import requests

from config import settings
from history import oss_config, oss_headers, oss_ready, oss_url


TZ = dt.timezone(dt.timedelta(hours=8))


def candidate_dir() -> Path:
    return settings.output_dir / "candidates"


def candidate_local_path(delivery_date: str) -> Path:
    return candidate_dir() / f"{delivery_date}.json"


def latest_local_path() -> Path:
    return candidate_dir() / "latest.json"


def bundled_candidate_dir() -> Path:
    return Path(__file__).with_name("candidates")


def bundled_candidate_path(delivery_date: str) -> Path:
    return bundled_candidate_dir() / f"{delivery_date}.json"


def bundled_latest_path() -> Path:
    return bundled_candidate_dir() / "latest.json"


def candidate_object_key(delivery_date: str) -> str:
    return f"{settings.candidate_prefix}/{delivery_date}.json".strip("/")


def latest_object_key() -> str:
    return f"{settings.candidate_prefix}/latest.json".strip("/")


def _oss_candidate_config(object_key: str) -> dict[str, str]:
    cfg = oss_config()
    cfg["object_key"] = object_key
    return cfg


def _put_oss_json(object_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    meta = {
        "candidate_oss_write_ok": False,
        "candidate_oss_path": f"oss://{settings.oss_bucket}/{object_key}",
    }
    if not oss_ready():
        meta["candidate_oss_error"] = "OSS config is incomplete."
        return meta
    cfg = _oss_candidate_config(object_key)
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    response = requests.put(
        oss_url(cfg),
        headers=oss_headers("PUT", cfg, "application/json; charset=utf-8"),
        data=body,
        timeout=15,
    )
    try:
        response.raise_for_status()
    except Exception as exc:
        meta["candidate_oss_error"] = str(exc)
        return meta
    meta["candidate_oss_write_ok"] = True
    return meta


def _get_oss_json(object_key: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    meta = {
        "candidate_oss_read_ok": False,
        "candidate_oss_path": f"oss://{settings.oss_bucket}/{object_key}",
    }
    if not oss_ready():
        meta["candidate_oss_error"] = "OSS config is incomplete."
        return None, meta
    cfg = _oss_candidate_config(object_key)
    response = requests.get(oss_url(cfg), headers=oss_headers("GET", cfg), timeout=15)
    if response.status_code == 404:
        meta["candidate_oss_error"] = "candidate not found."
        return None, meta
    try:
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("candidate root is not object")
    except Exception as exc:
        meta["candidate_oss_error"] = str(exc)
        return None, meta
    meta["candidate_oss_read_ok"] = True
    return data, meta


def build_candidate_payload(
    *,
    delivery_date: str,
    subject: str,
    brief: dict[str, Any],
    plain_text: str,
    html_body: str,
    quality: dict[str, Any],
    quality_gate: dict[str, Any],
    article_stats: dict[str, Any],
    final_selection: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(TZ).isoformat(),
        "delivery_date": delivery_date,
        "subject": subject,
        "brief": brief,
        "plain_text": plain_text,
        "html_body": html_body,
        "quality": quality,
        "quality_gate": quality_gate,
        "article_stats": article_stats,
        "final_selection": final_selection,
    }


def save_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    delivery_date = str(payload.get("delivery_date") or "")
    if not delivery_date:
        raise ValueError("delivery_date is required.")
    candidate_dir().mkdir(parents=True, exist_ok=True)
    daily_path = candidate_local_path(delivery_date)
    latest_path = latest_local_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    daily_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    meta: dict[str, Any] = {
        "candidate_saved": True,
        "candidate_storage": settings.candidate_storage,
        "candidate_local_path": str(daily_path),
        "candidate_latest_local_path": str(latest_path),
    }
    if settings.candidate_storage == "oss":
        daily_meta = _put_oss_json(candidate_object_key(delivery_date), payload)
        latest_meta = _put_oss_json(latest_object_key(), payload)
        meta.update(daily_meta)
        meta["candidate_oss_latest_write_ok"] = latest_meta.get("candidate_oss_write_ok", False)
        if latest_meta.get("candidate_oss_error"):
            meta["candidate_oss_latest_error"] = latest_meta.get("candidate_oss_error")
    return meta


def load_candidate(delivery_date: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    delivery_date = (delivery_date or "").strip()
    if settings.candidate_storage == "oss":
        object_key = candidate_object_key(delivery_date) if delivery_date else latest_object_key()
        payload, meta = _get_oss_json(object_key)
        if payload:
            meta["candidate_storage"] = "oss"
            return payload, meta
    path = candidate_local_path(delivery_date) if delivery_date else latest_local_path()
    meta: dict[str, Any] = {
        "candidate_storage": "local",
        "candidate_local_path": str(path),
        "candidate_local_read_ok": False,
    }
    if not path.exists():
        bundled_path = bundled_candidate_path(delivery_date) if delivery_date else bundled_latest_path()
        meta["candidate_local_error"] = "candidate not found."
        meta["candidate_bundled_path"] = str(bundled_path)
        meta["candidate_bundled_read_ok"] = False
        if not bundled_path.exists():
            meta["candidate_bundled_error"] = "candidate not found."
            return None, meta
        path = bundled_path
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("candidate root is not object")
    except Exception as exc:
        if path.parent == bundled_candidate_dir():
            meta["candidate_bundled_error"] = str(exc)
        else:
            meta["candidate_local_error"] = str(exc)
        return None, meta
    if path.parent == bundled_candidate_dir():
        meta["candidate_storage"] = "bundled"
        meta["candidate_bundled_read_ok"] = True
    else:
        meta["candidate_local_read_ok"] = True
    return data, meta
