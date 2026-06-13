from __future__ import annotations

import sys
import types
from pathlib import Path

sys.modules.setdefault("requests", types.SimpleNamespace())

from config import settings
from email_sender import send_segmented_email
from main import build_weekly_pdf_preview_candidate_message, send_weekly_pdf_candidate
from weekly_typst_export import render_preview_typst


def _preview_data() -> dict:
    return {
        "start_date": "2026-06-08",
        "end_date": "2026-06-14",
        "period": "2026.06.08 - 2026.06.14",
        "theme_overview": "这份周复盘预览覆盖 2026-06-08 至 2026-06-14 的内容，本周主要围绕基层治理闭环办理、公共服务精准抵达、协同治理责任分工展开，帮助你快速知道这一周重点学了什么。",
        "focus_points": [
            "基层治理要把群众诉求转化为闭环办理机制",
            "公共服务要从平均供给转向精准抵达",
            "协同治理要解决多主体责任分散问题",
        ],
        "full_modules": [
            "本周高频考点地图",
            "作文素材积累·一例多用",
            "本周金句表达库",
            "本周 3 道考场迁移训练",
            "每日内容压缩回看",
            "精读文章和延伸阅读索引",
        ],
        "expression_preview": "把群众诉求接住、办实、反馈清楚，治理共识才有现实基础。",
        "material_preview": {
            "title": "平台投诉治理片段",
            "source": "平台投诉治理",
            "summary": "这条素材来自平台投诉治理场景，能说明公共服务既要有入口，也要有责任分派和结果反馈。",
        },
        "practice_preview": {
            "title": "本周训练题片段",
            "question": "如果你负责推进一项群众争议较大的公共项目，请谈谈工作思路。",
            "direction": "先摸清诉求，再回应急事，最后公开协商。",
        },
        "cta_url": "https://example.com/paid",
    }


def _candidate(tmp_path: Path, *, full_ok: bool = True, lite_ok: bool = True) -> dict:
    full_path = tmp_path / "full.pdf"
    lite_path = tmp_path / "lite-preview.pdf"
    if full_ok:
        full_path.write_bytes(b"%PDF-full")
    if lite_ok:
        lite_path.write_bytes(b"%PDF-lite")
    return {
        "subject": "公考晨读｜本周复盘资料包",
        "plain_text": "完整版周复盘正文",
        "html_body": "<html><body>完整版周复盘正文</body></html>",
        "weekly_pdf": {
            "start_date": "2026-06-08",
            "end_date": "2026-06-14",
            "local_pdf": str(full_path),
            "attachment_filename": "full-weekly.pdf",
            "lite_preview": {
                "status": "ok" if lite_ok else "failed",
                "local_pdf": str(lite_path),
                "attachment_filename": "lite-weekly-preview.pdf",
                "error": "" if lite_ok else "preview failed",
            },
        },
        "quality_gate": {"overall": "ok"},
    }


def _weekly_archive_payload() -> dict:
    return {
        "delivery_date": "2026-06-14",
        "brief": {
            "today_theme": "基层治理闭环办理",
            "today_focus": "把群众诉求转成闭环办理机制",
            "featured_article": {
                "title": "把诉求办到底",
                "source": "人民日报",
                "published_at": "2026-06-14",
                "theme": "基层治理",
                "url": "https://example.com/a",
                "one_sentence": "把群众诉求接住、办实、反馈清楚。",
                "original_reading_focus": "围绕闭环办理机制展开。",
                "three_useful_points": ["统一入口", "分类流转", "结果反馈"],
                "exam_use": ["基层治理要形成闭环办理"],
                "rewritable_expression": "把群众诉求接住、办实、反馈清楚。",
                "article_framework_map": {
                    "steps": [
                        {"label": "发现问题", "content": "先摸清诉求来源。"},
                        {"label": "分类处置", "content": "按问题类型分流。"},
                        {"label": "结果反馈", "content": "及时回告群众。"},
                    ]
                },
            },
            "daily_question": {
                "question_type": "综合分析",
                "question": "请谈谈基层治理如何形成闭环办理机制。",
                "answer_framework": ["统一入口：先接住诉求", "分类流转：明确责任链条", "结果反馈：公开回应群众"],
                "candidate_answer": "要先接住诉求，再分类流转，最后反馈结果。",
            },
            "today_takeaway": {
                "keywords": ["基层治理", "闭环办理"],
                "golden_sentences": [{"sentence": "把群众诉求接住、办实、反馈清楚。", "scenario": "基层治理"}],
                "framework": "统一入口-分类流转-结果反馈",
            },
            "quick_reads": [
                {"title": "精准服务", "source": "光明日报", "theme": "公共服务", "one_sentence": "公共服务要从平均供给转向精准抵达。"},
                {"title": "协同治理", "source": "求是", "theme": "协同治理", "one_sentence": "协同治理要解决多主体责任分散问题。"},
            ],
        },
    }


def test_render_preview_typst_contains_preview_sections() -> None:
    text = render_preview_typst(_preview_data())

    assert "本周主题速览" in text
    assert "本周 3 个高频考点方向" in text
    assert "完整版 PDF 目录预览" in text
    assert "免费内容片段" in text
    assert "获取完整版" in text
    assert "本周 3 道考场迁移训练" in text
    assert "每日内容压缩回看" in text
    assert "考生版参考答案" not in text
    assert "candidate" not in text.lower()
    assert "debug" not in text.lower()
    assert "quality gate" not in text.lower()


def test_send_segmented_email_uses_distinct_attachments_for_full_and_lite(monkeypatch, tmp_path) -> None:
    original_output_dir = settings.output_dir
    object.__setattr__(settings, "output_dir", tmp_path)
    captured: list[dict[str, object]] = []

    def fake_send(subject, plain_text, html_body, recipients, *, recipient_source, attachments=None):
        captured.append(
            {
                "recipient_source": recipient_source,
                "attachments": [item["filename"] for item in (attachments or [])],
                "emails": [item["email"] for item in recipients],
            }
        )
        return {"success_count": len(recipients), "fail_count": 0, "recipient_status": [], "failures": []}

    monkeypatch.setattr("email_sender._send_email_to_records", fake_send)
    try:
        result = send_segmented_email(
            "周复盘",
            "full",
            "<html>full</html>",
            "lite",
            "<html>lite</html>",
            delivery_date="2026-06-15",
            attachments=[{"filename": "full-weekly.pdf", "content": b"1", "content_type": "application/pdf"}],
            lite_attachments=[{"filename": "lite-weekly-preview.pdf", "content": b"2", "content_type": "application/pdf"}],
            segments={
                "full": [{"email": "paid@example.com"}],
                "lite": [{"email": "free@example.com"}],
                "skipped": [],
            },
            recipient_source="test",
        )
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)

    assert result["full_count"] == 1
    assert result["lite_count"] == 1
    assert captured[0]["recipient_source"] == "test:full"
    assert captured[0]["attachments"] == ["full-weekly.pdf"]
    assert captured[1]["recipient_source"] == "test:lite"
    assert captured[1]["attachments"] == ["lite-weekly-preview.pdf"]


def test_send_weekly_pdf_candidate_full_and_free_split_attachments(monkeypatch, tmp_path) -> None:
    import email_sender
    import harness_metrics

    original_output_dir = settings.output_dir
    original_send_email = settings.send_email
    object.__setattr__(settings, "output_dir", tmp_path)
    object.__setattr__(settings, "send_email", True)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        email_sender,
        "split_effective_recipient_records",
        lambda **kwargs: (
            {
                "full": [{"email": "paid@example.com"}],
                "lite": [{"email": "free@example.com"}],
                "skipped": [],
            },
            "test-source",
        ),
    )

    def fake_send_segmented_email(*args, **kwargs):
        captured["attachments"] = [item["filename"] for item in (kwargs.get("attachments") or [])]
        captured["lite_attachments"] = [item["filename"] for item in (kwargs.get("lite_attachments") or [])]
        return {
            "success_count": 2,
            "fail_count": 0,
            "full_count": 1,
            "lite_count": 1,
            "skipped_count": 0,
        }

    monkeypatch.setattr(email_sender, "send_segmented_email", fake_send_segmented_email)
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: {"ok": True})
    try:
        result = send_weekly_pdf_candidate(
            candidate=_candidate(tmp_path, full_ok=True, lite_ok=True),
            delivery_date="2026-06-15",
            test_invocation=False,
            load_meta={},
            logger=__import__("logger").RunLogger(tmp_path),
        )
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)
        object.__setattr__(settings, "send_email", original_send_email)

    assert result["status"] == "ok"
    assert captured["attachments"] == ["full-weekly.pdf"]
    assert captured["lite_attachments"] == ["lite-weekly-preview.pdf"]


def test_send_weekly_pdf_candidate_preview_failure_degrades_to_email_only(monkeypatch, tmp_path) -> None:
    import email_sender
    import harness_metrics

    original_output_dir = settings.output_dir
    original_send_email = settings.send_email
    object.__setattr__(settings, "output_dir", tmp_path)
    object.__setattr__(settings, "send_email", True)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        email_sender,
        "split_effective_recipient_records",
        lambda **kwargs: (
            {
                "full": [],
                "lite": [{"email": "free@example.com"}],
                "skipped": [],
            },
            "test-source",
        ),
    )

    def fake_send_segmented_email(*args, **kwargs):
        captured["attachments"] = [item["filename"] for item in (kwargs.get("attachments") or [])]
        captured["lite_attachments"] = [item["filename"] for item in (kwargs.get("lite_attachments") or [])]
        return {
            "success_count": 1,
            "fail_count": 0,
            "full_count": 0,
            "lite_count": 1,
            "skipped_count": 0,
        }

    monkeypatch.setattr(email_sender, "send_segmented_email", fake_send_segmented_email)
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: {"ok": True})
    try:
        result = send_weekly_pdf_candidate(
            candidate=_candidate(tmp_path, full_ok=True, lite_ok=False),
            delivery_date="2026-06-15",
            test_invocation=False,
            load_meta={},
            logger=__import__("logger").RunLogger(tmp_path),
        )
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)
        object.__setattr__(settings, "send_email", original_send_email)

    assert result["status"] == "ok"
    assert captured["attachments"] == ["full-weekly.pdf"]
    assert captured["lite_attachments"] == []


def test_send_weekly_pdf_candidate_missing_full_attachment_blocks_full_users(monkeypatch, tmp_path) -> None:
    import email_sender
    import harness_metrics

    original_output_dir = settings.output_dir
    object.__setattr__(settings, "output_dir", tmp_path)
    monkeypatch.setattr(
        email_sender,
        "split_effective_recipient_records",
        lambda **kwargs: (
            {
                "full": [{"email": "paid@example.com"}],
                "lite": [],
                "skipped": [],
            },
            "test-source",
        ),
    )
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: {"ok": True})
    try:
        result = send_weekly_pdf_candidate(
            candidate=_candidate(tmp_path, full_ok=False, lite_ok=True),
            delivery_date="2026-06-15",
            test_invocation=False,
            load_meta={},
            logger=__import__("logger").RunLogger(tmp_path),
        )
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)

    assert result["status"] == "blocked"
    assert result["reason"] == "weekly_pdf_attachment_missing"


def test_send_weekly_pdf_candidate_lite_only_can_send_without_full_pdf(monkeypatch, tmp_path) -> None:
    import email_sender
    import harness_metrics

    original_output_dir = settings.output_dir
    original_send_email = settings.send_email
    object.__setattr__(settings, "output_dir", tmp_path)
    object.__setattr__(settings, "send_email", True)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        email_sender,
        "split_effective_recipient_records",
        lambda **kwargs: (
            {
                "full": [],
                "lite": [{"email": "free@example.com"}],
                "skipped": [],
            },
            "test-source",
        ),
    )

    def fake_send_segmented_email(*args, **kwargs):
        captured["attachments"] = [item["filename"] for item in (kwargs.get("attachments") or [])]
        captured["lite_attachments"] = [item["filename"] for item in (kwargs.get("lite_attachments") or [])]
        return {
            "success_count": 1,
            "fail_count": 0,
            "full_count": 0,
            "lite_count": 1,
            "skipped_count": 0,
        }

    monkeypatch.setattr(email_sender, "send_segmented_email", fake_send_segmented_email)
    monkeypatch.setattr(harness_metrics, "append_morning_metrics", lambda **kwargs: {"ok": True})
    try:
        result = send_weekly_pdf_candidate(
            candidate=_candidate(tmp_path, full_ok=False, lite_ok=True),
            delivery_date="2026-06-15",
            test_invocation=False,
            load_meta={},
            logger=__import__("logger").RunLogger(tmp_path),
        )
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)
        object.__setattr__(settings, "send_email", original_send_email)

    assert result["status"] == "ok"
    assert captured["attachments"] == []
    assert captured["lite_attachments"] == ["lite-weekly-preview.pdf"]


def test_build_weekly_assets_reuses_shared_enrichment_for_full_and_preview(monkeypatch, tmp_path) -> None:
    import weekly_report
    import weekly_typst_export

    original_output_dir = settings.output_dir
    original_history_storage = settings.history_storage
    object.__setattr__(settings, "output_dir", tmp_path)
    object.__setattr__(settings, "history_storage", "local")

    enrichment_calls = {"count": 0}

    def fake_enrichment(days):
        enrichment_calls["count"] += 1
        return {
            "exam_map_cards": [{"title": "基层治理闭环办理"}],
            "selected_expression_rows": [{"sentence": "把群众诉求接住、办实、反馈清楚。"}],
            "material_cards": [{
                "title": "闭环办理素材",
                "source_articles": ["把诉求办到底"],
                "material_summary": "从统一入口到结果反馈，形成群众诉求闭环办理。",
                "usage_examples": [{"theme": "基层治理要形成闭环办理", "example": "可用于说明治理不能止于受理，还要形成责任链条和反馈机制。"}],
                "use_boundary": "适合基层治理场景，不替代专业执法结论。",
            }],
            "practice_questions": [{"title": "本周训练题", "question": "如何形成闭环办理？", "use_boundary": "仅作思路训练。"}],
            "warnings": [],
        }

    def fake_compile(cmd, check=True):
        Path(cmd[-1]).write_bytes(b"%PDF-test")
        return None

    monkeypatch.setattr(weekly_report, "load_daily_archives", lambda **kwargs: ([_weekly_archive_payload()], []))
    monkeypatch.setattr(weekly_report, "build_weekly_markdown", lambda *args, **kwargs: "weekly markdown")
    monkeypatch.setattr(weekly_report, "build_weekly_html", lambda *args, **kwargs: "<html><body>weekly html</body></html>")
    monkeypatch.setattr(weekly_typst_export, "build_weekly_enrichment", fake_enrichment)
    monkeypatch.setattr(weekly_typst_export, "find_typst_binary", lambda: "typst")
    monkeypatch.setattr(weekly_typst_export.subprocess, "run", fake_compile)

    try:
        assets = weekly_report.build_weekly_assets({"end_date": "2026-06-14", "days": 7})
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)
        object.__setattr__(settings, "history_storage", original_history_storage)

    assert enrichment_calls["count"] == 1
    assert assets["status"] == "ok"
    assert assets["attachment"]["filename"]
    assert assets["lite_preview"]["status"] == "ok"
    assert assets["lite_preview"]["attachment_filename"]


def test_build_weekly_pdf_preview_candidate_message_marks_preview_as_free_preview() -> None:
    plain_text, html_body = build_weekly_pdf_preview_candidate_message(
        {
            "start_date": "2026-06-08",
            "end_date": "2026-06-14",
            "lite_preview": {
                "status": "ok",
                "attachment_filename": "lite-weekly-preview.pdf",
            },
        }
    )

    body = plain_text + html_body
    assert "免费预览版" in body
    assert "完整版用户会收到更完整的周 PDF" in body
    assert "candidate" not in body.lower()
    assert "debug" not in body.lower()
    assert "quality gate" not in body.lower()
