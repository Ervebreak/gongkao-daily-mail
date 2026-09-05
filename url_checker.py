from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests
from config import settings


RISKY_HOSTS = {
    "opinion.people.com.cn",
}


def classify_url(url: str) -> dict[str, str]:
    url = (url or "").strip()
    if not url:
        return {"url_status": "missing", "url_status_reason": "missing url"}

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not parsed.scheme or not host:
        return {"url_status": "invalid", "url_status_reason": "invalid url format"}

    if settings.run_mode == "test":
        return {"url_status": "valid", "url_status_reason": "network check skipped in RUN_MODE=test"}

    try:
        response = requests.head(
            url,
            timeout=4,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
            verify=True,
        )
        if response.status_code in {403, 405}:
            response = requests.get(
                url,
                timeout=5,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
                stream=True,
                verify=True,
            )
        if response.status_code >= 400:
            return {"url_status": "invalid", "url_status_reason": f"http {response.status_code}"}
    except requests.exceptions.SSLError as exc:
        return {"url_status": "warning", "url_status_reason": f"ssl warning: {exc.__class__.__name__}"}
    except requests.exceptions.RequestException as exc:
        return {"url_status": "invalid", "url_status_reason": f"request failed: {exc.__class__.__name__}"}

    if host in RISKY_HOSTS:
        return {"url_status": "warning", "url_status_reason": "known risky host in mobile mail clients"}
    return {"url_status": "valid", "url_status_reason": "ok"}


def annotate_brief_urls(brief: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    targets: list[tuple[str, dict[str, Any]]] = []
    featured = brief.get("featured_article")
    if isinstance(featured, dict):
        targets.append(("featured", featured))
    for idx, item in enumerate(brief.get("quick_reads", []) or [], start=1):
        if isinstance(item, dict):
            targets.append((f"quick_read_{idx}", item))

    for role, item in targets:
        result = classify_url(str(item.get("url") or ""))
        item.update(result)
        rows.append(
            {
                "role": role,
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "url_status": result["url_status"],
                "url_status_reason": result["url_status_reason"],
            }
        )
    return brief, rows
