from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from quality_gate import read_text_if_exists


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


def _issue(severity: str, code: str, message: str, *, bad_text: str = "") -> dict[str, Any]:
    issue = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if bad_text:
        issue["bad_text"] = bad_text
    return issue


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _basename(path_value: Any) -> str:
    text = str(path_value or "").strip()
    return Path(text).name if text else ""


def _parse_date(value: Any) -> dt.date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text)
    except Exception:
        return None


def _visible_text(candidate: dict[str, Any], weekly_pdf: dict[str, Any], preview: dict[str, Any]) -> str:
    parts = [
        str(candidate.get("plain_text") or ""),
        str(candidate.get("html_body") or ""),
        read_text_if_exists(weekly_pdf.get("local_md")),
        read_text_if_exists(weekly_pdf.get("local_html")),
        read_text_if_exists(_ensure_dict(weekly_pdf.get("typst_meta")).get("typ_path")),
        read_text_if_exists(_ensure_dict(weekly_pdf.get("typst_meta")).get("data_path")),
        read_text_if_exists(_ensure_dict(preview.get("typst_meta")).get("typ_path")),
        read_text_if_exists(_ensure_dict(preview.get("typst_meta")).get("data_path")),
    ]
    return "\n".join(part for part in parts if part)


def evaluate_weekly_pdf_quality(candidate_or_weekly_pdf: dict[str, Any], *, delivery_date: str = "") -> dict[str, Any]:
    candidate = candidate_or_weekly_pdf if isinstance(candidate_or_weekly_pdf.get("weekly_pdf"), dict) else {}
    weekly_pdf = _ensure_dict(candidate_or_weekly_pdf.get("weekly_pdf")) if candidate else candidate_or_weekly_pdf
    preview = _ensure_dict(weekly_pdf.get("lite_preview"))
    issues: list[dict[str, Any]] = []

    start_date = str(weekly_pdf.get("start_date") or "").strip()
    end_date = str(weekly_pdf.get("end_date") or "").strip()
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if not start or not end or start > end:
        issues.append(_issue("high", "weekly_pdf_invalid_date_range", "周 PDF 日期区间无效或前后颠倒。", bad_text=f"{start_date} -> {end_date}"))

    expected_full_name = f"gongkao-weekly-{start_date}_to_{end_date}.pdf" if start_date and end_date else ""
    expected_preview_name = f"gongkao-weekly-{start_date}_to_{end_date}-lite-preview.pdf" if start_date and end_date else ""

    full_local = str(weekly_pdf.get("local_pdf") or "").strip()
    full_oss = str(weekly_pdf.get("oss_pdf_path") or "").strip()
    if full_local and not full_oss:
        issues.append(_issue("high", "weekly_pdf_missing_oss_path", "完整版周 PDF 已生成，但 OSS 路径为空。"))
    if full_oss and "lite-preview" in _basename(full_oss):
        issues.append(_issue("high", "weekly_pdf_full_path_wrong_variant", "完整版周 PDF 的 OSS 文件名错误地带有 lite-preview 标识。", bad_text=_basename(full_oss)))
    if expected_full_name and full_oss and _basename(full_oss) != expected_full_name:
        issues.append(_issue("high", "weekly_pdf_date_range_mismatch", "完整版周 PDF 的 OSS 文件名与日期区间不一致。", bad_text=_basename(full_oss)))

    preview_local = str(preview.get("local_pdf") or "").strip()
    preview_oss = str(preview.get("oss_pdf_path") or "").strip()
    if preview_local and not preview_oss:
        issues.append(_issue("high", "weekly_pdf_lite_preview_missing_oss_path", "免费预览周 PDF 已生成，但 OSS 路径为空。"))
    if preview_oss and "lite-preview" not in _basename(preview_oss):
        issues.append(_issue("high", "weekly_pdf_lite_path_wrong_variant", "免费预览周 PDF 的 OSS 文件名缺少 lite-preview 标识。", bad_text=_basename(preview_oss)))
    if expected_preview_name and preview_oss and _basename(preview_oss) != expected_preview_name:
        issues.append(_issue("high", "weekly_pdf_date_range_mismatch", "免费预览周 PDF 的 OSS 文件名与日期区间不一致。", bad_text=_basename(preview_oss)))

    if delivery_date and end and _parse_date(delivery_date) and _parse_date(delivery_date) < end:
        issues.append(_issue("medium", "weekly_pdf_delivery_before_range_end", "发送日期早于周报结束日期，请确认候选件是否使用了错误的日期区间。", bad_text=f"{delivery_date} < {end_date}"))

    visible_text = _visible_text(candidate, weekly_pdf, preview)
    marker = next((item for item in INTERNAL_MARKERS if item and item.lower() in visible_text.lower()), "")
    if marker:
        issues.append(_issue("high", "weekly_pdf_internal_marker_leaked", f"周 PDF 前台内容出现内部标记：{marker}。", bad_text=marker))

    high_count = sum(1 for item in issues if item["severity"] == "high")
    status = "fail" if high_count else ("review" if issues else "ok")
    score = max(0, 100 - sum(18 if item["severity"] == "high" else 8 for item in issues))
    return {
        "ok": high_count == 0,
        "status": status,
        "score": score,
        "issues": issues,
        "start_date": start_date,
        "end_date": end_date,
    }
