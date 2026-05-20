from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import requests

from config import settings
from history import oss_config, oss_headers, oss_ready, oss_url


TZ = dt.timezone(dt.timedelta(hours=8))


def is_official_morning_run(now: dt.datetime | None = None) -> tuple[bool, dict[str, Any]]:
    now = now or dt.datetime.now(TZ)
    scheduled = now.replace(
        hour=settings.official_send_hour,
        minute=settings.official_send_minute,
        second=0,
        microsecond=0,
    )
    window_start = now.replace(
        hour=settings.official_archive_start_hour,
        minute=settings.official_archive_start_minute,
        second=0,
        microsecond=0,
    )
    window_end = now.replace(
        hour=settings.official_archive_end_hour,
        minute=settings.official_archive_end_minute,
        second=0,
        microsecond=0,
    )
    delta_minutes = abs((now - scheduled).total_seconds()) / 60
    ok = (
        settings.daily_archive_enabled
        and settings.run_mode == "prod"
        and settings.send_email
        and window_start <= now <= window_end
    )
    return ok, {
        "daily_archive_enabled": settings.daily_archive_enabled,
        "run_mode": settings.run_mode,
        "send_email": settings.send_email,
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "official_send_time": f"{settings.official_send_hour:02d}:{settings.official_send_minute:02d}",
        "official_archive_window": f"{settings.official_archive_start_hour:02d}:{settings.official_archive_start_minute:02d}-{settings.official_archive_end_hour:02d}:{settings.official_archive_end_minute:02d}",
        "archive_window_minutes": settings.official_archive_window_minutes,
        "delta_minutes": round(delta_minutes, 1),
    }


def put_oss_object(object_key: str, data: bytes, content_type: str) -> dict[str, Any]:
    cfg = oss_config()
    cfg["object_key"] = object_key.strip().lstrip("/")
    meta: dict[str, Any] = {
        "ok": False,
        "path": f"oss://{cfg.get('bucket')}/{cfg.get('object_key')}",
    }
    if not oss_ready():
        meta["error"] = "OSS 配置不完整，未写入每日归档。"
        return meta
    response = requests.put(
        oss_url(cfg),
        headers=oss_headers("PUT", cfg, content_type),
        data=data,
        timeout=20,
    )
    try:
        response.raise_for_status()
    except Exception as exc:
        meta["error"] = str(exc)
        return meta
    meta["ok"] = True
    return meta


def archive_daily_content(
    today: str,
    brief: dict[str, Any],
    html_body: str,
    plain_text: str,
    subject: str,
    send_success_count: int = 0,
) -> dict[str, Any]:
    should_archive, gate = is_official_morning_run()
    meta: dict[str, Any] = {
        "daily_archive_saved": False,
        "daily_archive_reason": "",
        **gate,
        "send_success_count": send_success_count,
    }
    if send_success_count <= 0:
        meta["daily_archive_reason"] = "邮件未成功发送，本次不保存到周报素材库。"
        return meta
    if not should_archive:
        meta["daily_archive_reason"] = "非正式晨发窗口或非真实发送，本次不保存到周报素材库。"
        return meta

    archive_payload = {
        "date": today,
        "subject": subject,
        "created_at": dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "brief": brief,
        "plain_text": plain_text,
    }
    json_bytes = json.dumps(archive_payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    html_bytes = html_body.encode("utf-8")

    local_dir = settings.output_dir / "daily"
    local_dir.mkdir(parents=True, exist_ok=True)
    local_json = local_dir / f"{today}.json"
    local_html = local_dir / f"{today}.html"
    local_json.write_bytes(json_bytes)
    local_html.write_bytes(html_bytes)

    meta.update({
        "daily_archive_saved": True,
        "daily_archive_local_json": str(local_json),
        "daily_archive_local_html": str(local_html),
    })

    if settings.history_storage == "oss":
        prefix = settings.daily_archive_prefix
        json_key = f"{prefix}/{today}.json"
        html_key = f"{prefix}/{today}.html"
        json_result = put_oss_object(json_key, json_bytes, "application/json; charset=utf-8")
        html_result = put_oss_object(html_key, html_bytes, "text/html; charset=utf-8")
        meta.update({
            "daily_archive_oss_json": json_result,
            "daily_archive_oss_html": html_result,
            "daily_archive_oss_ok": bool(json_result.get("ok") and html_result.get("ok")),
        })
    else:
        meta["daily_archive_oss_ok"] = False
        meta["daily_archive_reason"] = "当前 HISTORY_STORAGE 不是 oss，仅保存本地归档；FC /tmp 不适合周报长期读取。"
    return meta
