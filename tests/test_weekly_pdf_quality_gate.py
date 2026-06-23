from __future__ import annotations

from weekly_pdf_quality import evaluate_weekly_pdf_quality


def test_weekly_pdf_quality_blocks_missing_oss_paths(tmp_path) -> None:
    full_pdf = tmp_path / "gongkao-weekly-2026-06-08_to_2026-06-14.pdf"
    preview_pdf = tmp_path / "gongkao-weekly-2026-06-08_to_2026-06-14-lite-preview.pdf"
    full_pdf.write_bytes(b"%PDF-full")
    preview_pdf.write_bytes(b"%PDF-lite")

    result = evaluate_weekly_pdf_quality(
        {
            "weekly_pdf": {
                "start_date": "2026-06-08",
                "end_date": "2026-06-14",
                "local_pdf": str(full_pdf),
                "oss_pdf_path": "",
                "lite_preview": {
                    "status": "ok",
                    "local_pdf": str(preview_pdf),
                    "oss_pdf_path": "",
                },
            },
            "plain_text": "本周复盘资料包",
            "html_body": "<p>本周复盘资料包</p>",
        },
        delivery_date="2026-06-15",
    )

    assert result["status"] == "fail"
    assert {item["code"] for item in result["issues"]} >= {
        "weekly_pdf_missing_oss_path",
        "weekly_pdf_lite_preview_missing_oss_path",
    }


def test_weekly_pdf_quality_flags_internal_marker_and_variant_name(tmp_path) -> None:
    typ_path = tmp_path / "weekly.typ"
    typ_path.write_text("debug candidate quality gate JSON", encoding="utf-8")

    result = evaluate_weekly_pdf_quality(
        {
            "weekly_pdf": {
                "start_date": "2026-06-08",
                "end_date": "2026-06-14",
                "local_pdf": str(tmp_path / "full.pdf"),
                "oss_pdf_path": "oss://bucket/gongkao-weekly-2026-06-08_to_2026-06-14-lite-preview.pdf",
                "typst_meta": {"typ_path": str(typ_path)},
                "lite_preview": {
                    "status": "ok",
                    "local_pdf": str(tmp_path / "preview.pdf"),
                    "oss_pdf_path": "oss://bucket/gongkao-weekly-2026-06-08_to_2026-06-14.pdf",
                },
            },
            "plain_text": "本周复盘资料包",
            "html_body": "<p>本周复盘资料包</p>",
        },
        delivery_date="2026-06-15",
    )

    codes = {item["code"] for item in result["issues"]}
    assert result["status"] == "fail"
    assert "weekly_pdf_internal_marker_leaked" in codes
    assert "weekly_pdf_full_path_wrong_variant" in codes
    assert "weekly_pdf_lite_path_wrong_variant" in codes
