from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import settings


def clone_jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def module_snapshot(brief: dict[str, Any], module: str) -> Any:
    if module == "daily_question":
        return brief.get("daily_question") or {}
    if module == "article_framework_map":
        featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
        return featured.get("article_framework_map") or {}
    if module == "today_takeaway":
        return brief.get("today_takeaway") or {}
    return {}


def build_rewrite_comparison(
    initial_brief: dict[str, Any],
    final_brief: dict[str, Any],
    quality_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    rewrite = quality_payload.get("rewrite") if isinstance(quality_payload.get("rewrite"), dict) else {}
    modules = rewrite.get("rewritten_modules") if isinstance(rewrite.get("rewritten_modules"), list) else []
    details = rewrite.get("details") if isinstance(rewrite.get("details"), dict) else {}
    initial_quality = quality_payload.get("initial") if isinstance(quality_payload.get("initial"), dict) else {}
    final_quality = quality_payload.get("final") if isinstance(quality_payload.get("final"), dict) else {}
    rows: list[dict[str, Any]] = []
    quality_key_by_module = {
        "daily_question": "daily_question",
        "article_framework_map": "framework_map",
        "today_takeaway": "today_takeaway",
    }
    for fix in details.get("minor_auto_fixes") or []:
        if not isinstance(fix, dict):
            continue
        rows.append(
            {
                "module": "minor_auto_fix",
                "changed": True,
                "before": {fix.get("field") or "field": fix.get("bad_text") or ""},
                "after": {fix.get("field") or "field": fix.get("replacement") or ""},
                "issues_before": [
                    {
                        "level": fix.get("level") or "P1",
                        "severity": "medium",
                        "code": fix.get("code") or "minor_auto_fix",
                        "message": fix.get("message") or "minor auto fix",
                    }
                ],
                "quality_after": final_quality.get("content_risk") or {},
                "rewrite_detail": fix,
            }
        )
    for module in modules:
        module_name = str(module)
        if module_name.startswith("minor_fix:"):
            continue
        quality_key = quality_key_by_module.get(module_name, module_name)
        before = module_snapshot(initial_brief, module_name)
        after = module_snapshot(final_brief, module_name)
        module_details = details.get(module_name) or {
            key: value
            for key, value in details.items()
            if str(key).endswith(f":{module_name}")
        }
        rows.append(
            {
                "module": module_name,
                "changed": before != after,
                "before": before,
                "after": after,
                "issues_before": (initial_quality.get(quality_key) or {}).get("issues", []),
                "quality_after": final_quality.get(quality_key) or {},
                "rewrite_detail": module_details,
            }
        )
    return rows


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def save_blocked_run(
    *,
    delivery_date: str,
    articles: list[Any],
    initial_brief: dict[str, Any],
    final_brief: dict[str, Any],
    quality_payload: dict[str, Any],
    html_body: str,
    plain_text: str,
    subject: str,
    final_selection: dict[str, Any],
    candidate_save_result: dict[str, Any] | None = None,
    rewrite_comparison: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    safe_date = "".join(ch for ch in delivery_date if ch.isdigit() or ch == "-") or "unknown-date"
    root = settings.output_dir / "blocked_runs" / safe_date
    root.mkdir(parents=True, exist_ok=True)
    article_rows = [item.to_log_dict() if hasattr(item, "to_log_dict") else item for item in articles]
    rewrite_comparison = rewrite_comparison or build_rewrite_comparison(initial_brief, final_brief, quality_payload)
    save_json(root / "articles.json", article_rows)
    save_json(root / "brief_initial.json", initial_brief)
    save_json(root / "brief_final.json", final_brief)
    save_json(root / "quality_initial.json", quality_payload.get("initial") or {})
    save_json(root / "quality_final.json", quality_payload.get("final") or {})
    save_json(root / "latest_quality.json", quality_payload)
    save_json(root / "rewrite_comparison.json", rewrite_comparison)
    save_json(
        root / "run_meta.json",
        {
            "delivery_date": delivery_date,
            "subject": subject,
            "quality_gate": quality_payload.get("gate") or {},
            "candidate_save_result": candidate_save_result or {},
            "final_selection": final_selection,
            "plain_text_length": len(plain_text or ""),
            "html_length": len(html_body or ""),
        },
    )
    (root / "latest_email.html").write_text(html_body or "", encoding="utf-8")
    (root / "latest_email.txt").write_text(plain_text or "", encoding="utf-8")
    return {
        "blocked_archive_saved": True,
        "blocked_archive_path": str(root),
        "blocked_archive_files": [
            "articles.json",
            "brief_initial.json",
            "brief_final.json",
            "quality_initial.json",
            "quality_final.json",
            "latest_quality.json",
            "rewrite_comparison.json",
            "run_meta.json",
            "latest_email.html",
            "latest_email.txt",
        ],
    }
