from __future__ import annotations

import sys
import types

sys.modules.setdefault("requests", types.SimpleNamespace())

from main import _weekly_pdf_oss_path


def test_weekly_pdf_oss_path_uses_put_oss_object_path_field() -> None:
    assets = {
        "oss_upload": {
            "pdf": {
                "ok": True,
                "path": "oss://gongkao-mailer-erve/gongkao-morning-mailer/weekly/gongkao-weekly-2026-06-01_to_2026-06-06.pdf",
            }
        }
    }

    assert _weekly_pdf_oss_path(assets) == assets["oss_upload"]["pdf"]["path"]


def test_weekly_pdf_oss_path_keeps_oss_path_compatibility() -> None:
    assets = {
        "oss_upload": {
            "pdf": {
                "ok": True,
                "oss_path": "oss://bucket/new-field.pdf",
                "path": "oss://bucket/old-field.pdf",
            }
        }
    }

    assert _weekly_pdf_oss_path(assets) == "oss://bucket/new-field.pdf"
