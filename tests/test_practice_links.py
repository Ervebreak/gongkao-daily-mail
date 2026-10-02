from __future__ import annotations

import email_renderer
import email_sender
from practice_links import create_email_marker, remove_practice_cta, replace_email_markers, verify_token


SECRET = b"0123456789abcdef0123456789abcdef"


def _brief() -> dict:
    return {
        "date": "2026-10-02",
        "daily_question": {
            "question_type": "申论对策题",
            "question": "请提出提升基层公共服务效能的三点建议。",
            "answer_framework": ["完善清单", "优化协同", "健全反馈"],
            "candidate_answer": "从清单、协同和反馈三个方面提升服务效能。",
        },
    }


def test_email_marker_becomes_recipient_bound_signed_token() -> None:
    brief = _brief()
    marker = create_email_marker(brief["date"], brief["daily_question"])
    replaced = replace_email_markers(
        f"https://practice.example/t/{marker}",
        uid="u_123",
        secret=SECRET,
        expires_at=2_000_000_000,
    )
    token = replaced.rsplit("/", 1)[-1]
    payload = verify_token(token, secret=SECRET, now=1_900_000_000)
    assert payload["uid"] == "u_123"
    assert payload["date"] == "2026-10-02"
    assert payload["qid"]


def test_send_time_injection_does_not_change_canonical_renderer(monkeypatch) -> None:
    del monkeypatch
    brief = _brief()
    original_enabled = email_renderer.settings.practice_enabled
    original_base_url = email_renderer.settings.practice_base_url
    try:
        object.__setattr__(email_renderer.settings, "practice_enabled", True)
        object.__setattr__(email_renderer.settings, "practice_base_url", "https://practice.example")
        plain, html = email_sender.inject_practice_cta(
            "已审核正文",
            "<html><body>已审核正文</body></html>",
            brief,
        )
    finally:
        object.__setattr__(email_renderer.settings, "practice_enabled", original_enabled)
        object.__setattr__(email_renderer.settings, "practice_base_url", original_base_url)
    assert "开始训练：https://practice.example/t/__PRACTICE_TOKEN__" in plain
    assert "PRACTICE_CTA_START" in html
    assert "已审核正文" in plain and "已审核正文" in html


def test_bcc_cleanup_removes_practice_cta() -> None:
    marker = create_email_marker("2026-10-02", _brief()["daily_question"])
    plain = f"正文\n开始训练：https://practice.example/t/{marker}\n退订"
    html = f"正文<!-- PRACTICE_CTA_START --><a href='/{marker}'>开始</a><!-- PRACTICE_CTA_END -->退订"
    assert "开始训练" not in remove_practice_cta(plain)
    assert "PRACTICE_TOKEN" not in remove_practice_cta(html)


def test_recipient_personalization_signs_both_email_parts(monkeypatch) -> None:
    marker = create_email_marker("2026-10-02", _brief()["daily_question"])
    original_secret = email_sender.settings.practice_link_secret
    original_days = email_sender.settings.practice_link_days
    try:
        object.__setattr__(email_sender.settings, "practice_link_secret", SECRET.decode("ascii"))
        object.__setattr__(email_sender.settings, "practice_link_days", 7)
        monkeypatch.setattr(email_sender.time, "time", lambda: 1_900_000_000)
        plain, html = email_sender.personalize_email_payload_for_recipient(
            f"开始训练：https://practice.example/t/{marker}",
            f'<a href="https://practice.example/t/{marker}">开始训练</a>',
            {"uid": "u_123", "email": "user@example.com"},
        )
    finally:
        object.__setattr__(email_sender.settings, "practice_link_secret", original_secret)
        object.__setattr__(email_sender.settings, "practice_link_days", original_days)
    assert marker not in plain and marker not in html
    plain_token = plain.split("/t/", 1)[1].split()[0]
    html_token = html.split("/t/", 1)[1].split('"', 1)[0]
    assert plain_token == html_token
    payload = verify_token(plain_token, secret=SECRET, now=1_900_000_001)
    assert payload["uid"] == "u_123"
