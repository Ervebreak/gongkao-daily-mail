from __future__ import annotations

import base64
import io
import json
import logging
import sys
import zipfile
import builtins
from pathlib import Path
from types import SimpleNamespace

import pytest

import fc_weekly_render as target
import weekly_typst_export as weekly_export


TOKEN = "test-token-that-must-not-leak"


def _question(question_type: str) -> dict:
    return {
        "question_type": question_type,
        "question": "测试题干",
        "answer_hint": "测试提示",
        "mini_reference_answer": "测试答案",
        "suggested_golden_sentences": ["测试表达"],
    }


def _enrichment() -> dict:
    return {
        "exam_map_cards": [{"title": f"考点{i}"} for i in range(4)],
        "selected_expression_rows": [{"sentence": f"表达{i}"} for i in range(8)],
        "material_cards": [],
        "practice_questions": [
            _question("面试综合分析题"),
            _question("对策建议题"),
            _question("申论作文分论点展开题"),
        ],
    }


def _payload() -> dict:
    dates = [f"2026-09-{day:02d}" for day in (5, 6, 8, 9, 10, 11)]
    return {
        "start_date": "2026-09-05",
        "end_date": "2026-09-11",
        "days": [{"date": date, "brief": {"date": date}} for date in dates],
        "enrichment": _enrichment(),
    }


def _event(payload: dict, token: str = TOKEN) -> dict:
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "body": json.dumps(payload, ensure_ascii=False),
    }


@pytest.fixture(autouse=True)
def _token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEEKLY_RENDER_TOKEN", TOKEN)


def _body(response: dict) -> dict:
    return json.loads(response["body"])


def test_unauthorized_request_is_rejected() -> None:
    response = target.handler(_event(_payload(), "wrong"), None)
    assert response["statusCode"] == 401
    assert _body(response)["issue_code"] == "weekly_render_auth_failed"


def test_token_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    target.handler(_event(_payload(), "wrong"), None)
    assert TOKEN not in caplog.text


def test_requires_exactly_six_daily_objects() -> None:
    payload = _payload()
    payload["days"] = payload["days"][:5]
    response = target.handler(_event(payload), None)
    assert response["statusCode"] == 400
    assert _body(response)["issue_code"] == "weekly_render_input_invalid"


def test_rejects_duplicate_dates() -> None:
    payload = _payload()
    payload["days"][1] = payload["days"][0]
    response = target.handler(_event(payload), None)
    assert _body(response)["issue_code"] == "weekly_render_date_invalid"


def test_rejects_missing_enrichment_field() -> None:
    payload = _payload()
    del payload["enrichment"]["material_cards"]
    response = target.handler(_event(payload), None)
    assert _body(response)["issue_code"] == "weekly_render_enrichment_invalid"


def test_allow_incomplete_cannot_be_enabled() -> None:
    payload = _payload()
    payload["allow_incomplete"] = True
    response = target.handler(_event(payload), None)
    assert _body(response)["issue_code"] == "weekly_render_input_invalid"


def test_typst_missing_returns_explicit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_export = SimpleNamespace(find_typst_binary=lambda: None)
    monkeypatch.setitem(sys.modules, "weekly_typst_export", fake_export)
    response = target.handler(_event(_payload()), None)
    assert response["statusCode"] == 503
    assert _body(response)["issue_code"] == "weekly_render_typst_unavailable"


def test_explicit_enrichment_never_imports_model_curator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "weekly_material_curator":
            raise AssertionError("model enrichment module must not be imported")
        return original_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "weekly_material_curator", raising=False)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    payload = _payload()
    data = weekly_export.build_data(
        payload["days"],
        payload["start_date"],
        payload["end_date"],
        [],
        enrichment_override=payload["enrichment"],
    )
    assert data["exam_map_cards"] is payload["enrichment"]["exam_map_cards"]


def test_success_uses_one_shared_data_and_returns_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {"full": None, "lite": None, "model": 0, "side_effect": 0}

    def build_data(payloads, start, end, misses, *, enrichment_override=None):
        assert len(payloads) == 6
        assert misses == []
        assert enrichment_override is not None
        return {
            "start_date": start,
            "end_date": end,
            "days": [{"date": item["date"]} for item in payloads],
            "warnings": [],
            **enrichment_override,
        }

    def render(payloads, misses, pdf_path, start, end, *, data=None):
        calls["full"] = data
        pdf_path.write_bytes(b"%PDF-1.7\n" + b"0" * 64)
        typ_path = pdf_path.with_suffix(".typ")
        typ_path.write_text("rendered full", encoding="utf-8")
        data_path = pdf_path.with_suffix(".json")
        data_path.write_text("{}", encoding="utf-8")
        return {"typ_path": str(typ_path), "data_path": str(data_path)}

    def render_lite(payloads, misses, pdf_path, start, end, *, data=None):
        calls["lite"] = data
        pdf_path.write_bytes(b"%PDF-1.7\n" + b"1" * 64)
        typ_path = pdf_path.with_suffix(".typ")
        typ_path.write_text("rendered lite", encoding="utf-8")
        data_path = pdf_path.with_suffix(".json")
        data_path.write_text("{}", encoding="utf-8")
        return {"typ_path": str(typ_path), "data_path": str(data_path)}

    fake_export = SimpleNamespace(
        find_typst_binary=lambda: "/opt/bin/typst",
        build_data=build_data,
        build_typst_weekly_pdf=render,
        build_typst_weekly_preview_pdf=render_lite,
    )
    monkeypatch.setitem(sys.modules, "weekly_typst_export", fake_export)
    monkeypatch.setattr(target, "_typst_version", lambda _binary: "typst 0.13.1")

    for name in ("weekly_material_curator", "daily_archive", "email_sender", "candidate_store"):
        monkeypatch.setitem(
            sys.modules,
            name,
            SimpleNamespace(__getattr__=lambda _name: calls.__setitem__("side_effect", 1)),
        )

    response = target.handler(_event(_payload()), None)

    assert response["statusCode"] == 200
    assert response["isBase64Encoded"] is True
    assert calls["full"] is calls["lite"]
    assert calls["model"] == 0
    assert calls["side_effect"] == 0

    archive_bytes = base64.b64decode(response["body"])
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = set(archive.namelist())
        assert "gongkao-weekly-2026-09-05_to_2026-09-11.pdf" in names
        assert "gongkao-weekly-2026-09-05_to_2026-09-11-lite-preview.pdf" in names
        assert "weekly_pdf_delivery_report.json" in names
        report = json.loads(archive.read("weekly_pdf_delivery_report.json"))

    assert report["status"] == "pass"
    assert report["generation_mode"] == "offline_enrichment"
    assert report["renderer"] == "typst"
    assert report["typst_version"] == "typst 0.13.1"
    assert report["model_enrichment_disabled"] is True
    assert report["model_api_call"] is False
    assert report["allow_incomplete"] is False
    assert report["prohibited_actions"]["oss_upload"] is False
    assert report["prohibited_actions"]["email_send"] is False
    assert report["prohibited_actions"]["candidate_write"] is False


def test_entrypoint_has_no_production_side_effect_imports() -> None:
    source = Path(target.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "weekly_report",
        "daily_archive",
        "email_sender",
        "candidate_store",
        "llm_client",
        "requests",
        "put_oss_object",
        "send_email(",
        "save_candidate(",
        "--allow-incomplete",
    ):
        assert forbidden not in source

    exporter_source = Path(weekly_export.__file__).read_text(encoding="utf-8")
    for forbidden in ("weekly_report", "daily_archive", "email_sender", "candidate_store"):
        assert forbidden not in exporter_source
