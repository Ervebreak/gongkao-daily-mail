from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import fc_practice
from practice_demo import AttemptStore
from practice_links import create_candidate_token


SECRET = "0123456789abcdef0123456789abcdef"


def _candidate() -> dict:
    return {
        "delivery_date": "2026-10-02",
        "quality_gate": {"overall": "ok", "p0_count": 0},
        "brief": {
            "date": "2026-10-02",
            "daily_question": {
                "question_type": "申论对策题",
                "question": "请提出提升基层公共服务效能的三点建议。",
                "answer_framework": ["完善清单", "优化协同", "健全反馈"],
                "candidate_answer": "从清单、协同和反馈三个方面提升服务效能。",
            },
        },
    }


def _token(candidate: dict | None = None) -> str:
    return create_candidate_token(
        uid="u_123",
        candidate=candidate or _candidate(),
        secret=SECRET.encode("utf-8"),
        expires_at=2_000_000_000,
    )


def _configure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PRACTICE_LINK_SECRET", SECRET)
    monkeypatch.setenv("PRACTICE_COACH_MODE", "mock")
    monkeypatch.setenv("PRACTICE_MAX_REVIEWS", "2")
    monkeypatch.setattr(fc_practice, "settings", SimpleNamespace(candidate_storage="oss"))
    monkeypatch.setattr(
        fc_practice.candidate_store,
        "load_candidate",
        lambda delivery_date: (_candidate(), {"candidate_storage": "oss", "delivery_date": delivery_date}),
    )
    monkeypatch.setattr(
        fc_practice,
        "OssAttemptStore",
        lambda: AttemptStore(tmp_path / "attempts.json"),
    )


def test_healthz_is_available_without_loading_candidate() -> None:
    response = fc_practice.handler({"httpMethod": "GET", "path": "/healthz"}, None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["service"] == "gongkao-practice"
    assert response["headers"]["Cache-Control"] == "no-store"
    assert response["headers"]["Content-Disposition"] == "inline"


def test_get_serves_pass_candidate_from_oss(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    response = fc_practice.handler({"httpMethod": "GET", "path": f"/t/{_token()}"}, None)
    assert response["statusCode"] == 200
    assert "提升基层公共服务效能" in response["body"]
    assert "frame-ancestors 'none'" in response["headers"]["Content-Security-Policy"]


def test_post_returns_feedback_on_the_same_page(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    body = urlencode(
        {
            "request_id": "request-1",
            "p1": "建立群众需求清单，明确办理事项。",
            "p2": "优化部门协同，减少重复提交材料。",
            "p3": "健全评价反馈闭环，持续改进服务。",
        }
    )
    response = fc_practice.handler(
        {"httpMethod": "POST", "path": f"/t/{_token()}", "body": body, "isBase64Encoded": False},
        None,
    )
    assert response["statusCode"] == 200
    assert "第 1 次模拟点评" in response["body"]
    assert "今日剩余 1 次评价" in response["body"]


def test_local_candidate_fallback_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("PRACTICE_LINK_SECRET", SECRET)
    monkeypatch.setattr(fc_practice, "settings", SimpleNamespace(candidate_storage="local"))
    response = fc_practice.handler({"httpMethod": "GET", "path": f"/t/{_token()}"}, None)
    payload = json.loads(response["body"])
    assert response["statusCode"] == 503
    assert payload["code"] == "practice_candidate_storage_invalid"


def test_tampered_link_is_rejected_before_oss_read(monkeypatch) -> None:
    monkeypatch.setenv("PRACTICE_LINK_SECRET", SECRET)
    monkeypatch.setattr(fc_practice, "settings", SimpleNamespace(candidate_storage="oss"))

    def must_not_read(delivery_date: str):
        raise AssertionError(f"OSS must not be read for invalid link: {delivery_date}")

    monkeypatch.setattr(fc_practice.candidate_store, "load_candidate", must_not_read)
    response = fc_practice.handler({"httpMethod": "GET", "path": f"/t/{_token()}x"}, None)
    assert response["statusCode"] == 403
    assert json.loads(response["body"])["code"] == "practice_link_invalid"


def test_blocked_candidate_is_rejected(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    blocked = _candidate()
    blocked["quality_gate"] = {"overall": "ok", "p0_count": 1}
    monkeypatch.setattr(
        fc_practice.candidate_store,
        "load_candidate",
        lambda delivery_date: (blocked, {"candidate_storage": "oss"}),
    )
    response = fc_practice.handler({"httpMethod": "GET", "path": f"/t/{_token(blocked)}"}, None)
    assert response["statusCode"] == 403
    assert json.loads(response["body"])["code"] == "practice_candidate_invalid"
