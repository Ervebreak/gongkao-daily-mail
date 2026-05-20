from __future__ import annotations

import datetime as dt
import email.utils
import hmac
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import requests


TZ = dt.timezone(dt.timedelta(hours=8))


def hash_text(value: str) -> str:
    return hashlib.sha1((value or "").strip().encode("utf-8")).hexdigest()[:12]


def normalize_title(title: str) -> str:
    text = (title or "").strip()
    text = re.sub(r"^(新华时评|人民时评|人民锐评|人民网评|评论员观察)[:：丨｜\s]+", "", text)
    text = text.replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'")
    text = re.sub(r"[\s　]+", "", text)
    text = re.sub(r"[，。、“”‘’\"'：:；;！!？?（）()\[\]【】《》<>]+", "", text)
    return text.lower()


def parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def oss_enabled() -> bool:
    return os.environ.get("HISTORY_STORAGE", "local").strip().lower() == "oss"


def oss_config() -> dict[str, str]:
    return {
        "endpoint": os.environ.get("OSS_ENDPOINT", "").strip().rstrip("/"),
        "bucket": os.environ.get("OSS_BUCKET", "").strip(),
        "access_key_id": os.environ.get("OSS_ACCESS_KEY_ID", "").strip(),
        "access_key_secret": os.environ.get("OSS_ACCESS_KEY_SECRET", "").strip(),
        "object_key": os.environ.get("OSS_OBJECT_KEY", "gongkao-morning-mailer/sent_history.json").strip().lstrip("/"),
    }


def oss_ready() -> bool:
    cfg = oss_config()
    return all(cfg.values())


def oss_url(cfg: dict[str, str]) -> str:
    endpoint = cfg["endpoint"]
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        scheme, rest = endpoint.split("://", 1)
        return f"{scheme}://{cfg['bucket']}.{rest}/{cfg['object_key']}"
    return f"https://{cfg['bucket']}.{endpoint}/{cfg['object_key']}"


def oss_headers(method: str, cfg: dict[str, str], content_type: str = "") -> dict[str, str]:
    date = email.utils.formatdate(usegmt=True)
    resource = f"/{cfg['bucket']}/{cfg['object_key']}"
    string_to_sign = f"{method}\n\n{content_type}\n{date}\n{resource}"
    signature = hmac.new(
        cfg["access_key_secret"].encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    import base64

    auth = base64.b64encode(signature).decode("ascii")
    headers = {
        "Date": date,
        "Authorization": f"OSS {cfg['access_key_id']}:{auth}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def load_history_from_oss() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cfg = oss_config()
    meta: dict[str, Any] = {
        "history_read_ok": True,
        "history_storage": "oss",
        "history_path": f"oss://{cfg.get('bucket')}/{cfg.get('object_key')}",
        "history_count": 0,
        "history_persistence_warning": "当前历史记录存储在 OSS，可跨 FC 冷启动和跨实例持久化。",
    }
    if not oss_ready():
        meta.update({
            "history_read_ok": False,
            "history_error": "HISTORY_STORAGE=oss 但 OSS_ENDPOINT/OSS_BUCKET/OSS_ACCESS_KEY_ID/OSS_ACCESS_KEY_SECRET/OSS_OBJECT_KEY 未配置完整，已回退空历史。",
        })
        return [], meta
    response = requests.get(oss_url(cfg), headers=oss_headers("GET", cfg), timeout=15)
    if response.status_code == 404:
        return [], meta
    try:
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("OSS history root is not list")
    except Exception as exc:
        meta.update({"history_read_ok": False, "history_error": str(exc)})
        return [], meta
    meta["history_count"] = len(data)
    return data, meta


def save_history_to_oss(history: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = oss_config()
    meta: dict[str, Any] = {
        "history_write_ok": False,
        "history_storage": "oss",
        "history_path": f"oss://{cfg.get('bucket')}/{cfg.get('object_key')}",
        "history_count": len(history),
    }
    if not oss_ready():
        meta["history_error"] = "OSS 配置不完整，未写入 OSS。"
        return meta
    body = json.dumps(history, ensure_ascii=False, indent=2).encode("utf-8")
    response = requests.put(
        oss_url(cfg),
        headers=oss_headers("PUT", cfg, "application/json; charset=utf-8"),
        data=body,
        timeout=15,
    )
    try:
        response.raise_for_status()
    except Exception as exc:
        meta["history_error"] = str(exc)
        return meta
    meta["history_write_ok"] = True
    return meta


def load_history(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if oss_enabled():
        return load_history_from_oss()
    meta: dict[str, Any] = {
        "history_read_ok": True,
        "history_path": str(path),
        "history_count": 0,
        "history_storage": "local",
        "history_persistence_warning": "当前历史记录存储在本地文件；如果路径位于 /tmp，在阿里云 FC 冷启动或跨实例时可能无法稳定持久化。后续可通过 HISTORY_STORAGE=oss 切换到 OSS。",
    }
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")
        return [], meta
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("history root is not list")
    except Exception as exc:
        meta.update({"history_read_ok": False, "history_error": str(exc)})
        path.write_text("[]", encoding="utf-8")
        return [], meta
    meta["history_count"] = len(data)
    return data, meta


def trim_history(history: list[dict[str, Any]], today: dt.date | None = None, keep_days: int = 30) -> list[dict[str, Any]]:
    today = today or dt.datetime.now(TZ).date()
    trimmed: list[dict[str, Any]] = []
    for item in history:
        item_date = parse_date(str(item.get("date", "")))
        if item_date and 0 <= (today - item_date).days <= keep_days:
            trimmed.append(item)
    return trimmed


def save_history(path: Path, history: list[dict[str, Any]]) -> dict[str, Any]:
    if oss_enabled():
        return save_history_to_oss(history)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"history_write_ok": True, "history_path": str(path), "history_count": len(history)}


def recent_history(history: list[dict[str, Any]], days: int, role: str | None = None) -> list[dict[str, Any]]:
    today = dt.datetime.now(TZ).date()
    rows: list[dict[str, Any]] = []
    for item in history:
        item_date = parse_date(str(item.get("date", "")))
        if not item_date:
            continue
        if 0 <= (today - item_date).days <= days and (role is None or item.get("role") == role):
            rows.append(item)
    return rows


def build_history_index(history: list[dict[str, Any]]) -> dict[str, Any]:
    recent_featured_7 = recent_history(history, 7, "featured")
    recent_quick_3 = recent_history(history, 3, "quick_read")
    recent_featured_3 = recent_history(history, 3, "featured")
    yesterday = dt.datetime.now(TZ).date() - dt.timedelta(days=1)
    yesterday_featured = [
        item for item in history
        if item.get("role") == "featured" and parse_date(str(item.get("date", ""))) == yesterday
    ]
    return {
        "featured_7_urls": {item.get("url") for item in recent_featured_7 if item.get("url")},
        "featured_7_titles": {normalize_title(str(item.get("title", ""))) for item in recent_featured_7},
        "quick_3_urls": {item.get("url") for item in recent_quick_3 if item.get("url")},
        "quick_3_titles": {normalize_title(str(item.get("title", ""))) for item in recent_quick_3},
        "yesterday_featured_titles": [item.get("title") for item in yesterday_featured],
        "recent_featured_themes_3d": [item.get("theme") for item in recent_featured_3 if item.get("theme")],
        "recent_featured_sources_3d": [item.get("source") for item in recent_featured_3 if item.get("source")],
        "recent_featured_items_7d": [
            {
                "date": item.get("date"),
                "title": item.get("title"),
                "source": item.get("source"),
                "theme": item.get("theme"),
            }
            for item in recent_featured_7
        ],
    }


def append_records(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    history, read_meta = load_history(path)
    today = dt.datetime.now(TZ).date()
    history = trim_history(history, today=today)
    existing_keys = {
        (item.get("date"), item.get("role"), item.get("url_hash"), item.get("title_hash"))
        for item in history
    }
    appended = 0
    for record in records:
        record["title_hash"] = hash_text(str(record.get("title", "")))
        record["url_hash"] = hash_text(str(record.get("url", "")))
        key = (record.get("date"), record.get("role"), record.get("url_hash"), record.get("title_hash"))
        if key in existing_keys:
            continue
        history.append(record)
        existing_keys.add(key)
        appended += 1
    write_meta = save_history(path, history)
    return {**read_meta, **write_meta, "history_appended": appended}
