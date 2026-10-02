from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

from practice_demo import AttemptStore, PracticeDemoApp, PracticeDemoError, create_token, load_practice_candidate, verify_token
from practice_coach import normalize_api_feedback


def _candidate() -> dict:
    return {
        "delivery_date": "2026-09-30",
        "quality_gate": {"overall": "ok", "p0_count": 0},
        "brief": {
            "daily_question": {
                "question_type": "申论对策题",
                "question": "请提出提升基层公共服务效能的三点建议。",
                "answer_framework": ["完善服务清单", "优化协同流程", "健全反馈闭环"],
                "candidate_answer": "从清单、协同和反馈三个方面提升服务效能。",
            }
        },
    }


def _app(tmp_path: Path) -> PracticeDemoApp:
    return PracticeDemoApp(
        candidate=_candidate(),
        secret=b"test-secret",
        store=AttemptStore(tmp_path / "attempts.json"),
        uid="u_123",
        expires_at=2_000_000_000,
    )


def _submission(request_id: str = "request-1") -> bytes:
    return urlencode(
        {
            "request_id": request_id,
            "p1": "建立群众需求清单，明确服务对象和办理事项。",
            "p2": "打通部门协同流程，减少重复提交材料。",
            "p3": "建立评价反馈闭环，根据群众意见持续改进。",
        }
    ).encode("utf-8")


def test_signed_link_opens_the_matching_question(tmp_path: Path) -> None:
    app = _app(tmp_path)
    status, content_type, body = app.handle("GET", app.training_path)
    page = body.decode("utf-8")
    assert status == 200
    assert content_type == "text/html; charset=utf-8"
    assert "提升基层公共服务效能" in page
    assert "今日剩余 2 次评价" in page


def test_email_preview_contains_the_personal_training_link(tmp_path: Path) -> None:
    app = _app(tmp_path)
    status, _, body = app.handle("GET", "/demo-email")
    page = body.decode("utf-8")
    assert status == 200
    assert app.training_path in page
    assert "开始训练" in page


def test_tampered_link_is_rejected() -> None:
    candidate = _candidate()
    token = create_token(uid="u_123", candidate=candidate, secret=b"test-secret", expires_at=2_000_000_000)
    with pytest.raises(PracticeDemoError, match="无效|修改"):
        verify_token(token + "x", candidate=candidate, secret=b"test-secret", now=1_900_000_000)


def test_expired_link_is_rejected() -> None:
    candidate = _candidate()
    token = create_token(uid="u_123", candidate=candidate, secret=b"test-secret", expires_at=100)
    with pytest.raises(PracticeDemoError, match="过期"):
        verify_token(token, candidate=candidate, secret=b"test-secret", now=101)


def test_candidate_must_have_passed_quality_gate(tmp_path: Path) -> None:
    candidate = _candidate()
    candidate["quality_gate"]["overall"] = "blocked"
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PracticeDemoError, match="质量门禁"):
        load_practice_candidate(path)


def test_successful_submission_is_saved_and_deducts_one_review(tmp_path: Path) -> None:
    app = _app(tmp_path)
    status, _, body = app.handle("POST", app.training_path, _submission())
    page = body.decode("utf-8")
    assert status == 200
    assert "今日剩余 1 次评价" in page
    assert "第 1 次模拟点评" in page
    assert "考生版参考答案" in page

    reloaded = _app(tmp_path)
    status, _, body = reloaded.handle("GET", reloaded.training_path)
    assert status == 200
    assert "第 1 次模拟点评" in body.decode("utf-8")


def test_same_request_id_is_idempotent(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.handle("POST", app.training_path, _submission("same-request"))
    status, _, body = app.handle("POST", app.training_path, _submission("same-request"))
    page = body.decode("utf-8")
    assert status == 200
    assert "今日剩余 1 次评价" in page
    assert page.count("次模拟点评") == 1


def test_third_successful_submission_is_rejected(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.handle("POST", app.training_path, _submission("request-1"))
    app.handle("POST", app.training_path, _submission("request-2"))
    status, _, body = app.handle("POST", app.training_path, _submission("request-3"))
    assert status == 429
    assert "2 次评价机会已经用完" in body.decode("utf-8")


def test_full_quota_is_rejected_before_calling_coach(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.handle("POST", app.training_path, _submission("request-1"))
    app.handle("POST", app.training_path, _submission("request-2"))

    def must_not_run(points: list[str], question: dict) -> dict:
        raise AssertionError("coach must not run after quota is full")

    app.coach = must_not_run
    status, _, body = app.handle("POST", app.training_path, _submission("request-3"))
    assert status == 429
    assert "2 次评价机会已经用完" in body.decode("utf-8")


def test_incomplete_submission_does_not_deduct_review(tmp_path: Path) -> None:
    app = _app(tmp_path)
    body = urlencode({"request_id": "request-1", "p1": "一个点", "p2": "", "p3": "第三点"}).encode("utf-8")
    status, _, page = app.handle("POST", app.training_path, body)
    assert status == 422
    assert "请完整填写三个要点" in page.decode("utf-8")
    assert "今日剩余 2 次评价" in page.decode("utf-8")


def _api_feedback() -> dict:
    return {
        "mode": "api",
        "summary": "作答切题，三个方向清楚，但第三点需要补充执行结果。",
        "scores": {"relevance": 5, "structure": 4, "specificity": 4, "expression": 4},
        "strengths": ["覆盖了需求、协同和反馈三个层次"],
        "improvements": ["第三点补充责任主体和闭环结果"],
        "improved_points": ["完善需求清单", "优化部门协同", "健全反馈闭环"],
        "thirty_second_answer": "提升服务效能，要从需求清单、部门协同和反馈闭环三个方面发力。",
    }


def test_api_feedback_is_rendered_and_deducts_one_review(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.coach = lambda points, question: _api_feedback()
    app.coach_name = "api"
    status, _, body = app.handle("POST", app.training_path, _submission())
    page = body.decode("utf-8")
    assert status == 200
    assert "切题 5/5" in page
    assert "第 1 次 AI 点评" in page
    assert "优化后的三个点" in page
    assert "今日剩余 1 次评价" in page


def test_api_failure_does_not_deduct_review(tmp_path: Path) -> None:
    app = _app(tmp_path)

    def fail(points: list[str], question: dict) -> dict:
        raise TimeoutError("provider timed out")

    app.coach = fail
    app.coach_name = "api"
    status, _, body = app.handle("POST", app.training_path, _submission())
    page = body.decode("utf-8")
    assert status == 502
    assert "本次未扣次数" in page
    assert "今日剩余 2 次评价" in page


def test_api_feedback_schema_rejects_incomplete_response() -> None:
    with pytest.raises(ValueError, match="结构不完整"):
        normalize_api_feedback(
            {
                "summary": "评价",
                "scores": {"relevance": 5, "structure": 4, "specificity": 4, "expression": 4},
                "strengths": ["优点"],
                "improvements": [],
                "improved_points": ["一", "二", "三"],
                "thirty_second_answer": "示范",
            }
        )
