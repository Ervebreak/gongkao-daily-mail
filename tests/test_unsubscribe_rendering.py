from __future__ import annotations

import sys
import types

sys.modules.setdefault("requests", types.SimpleNamespace())

from config import settings
from email_renderer import render_email_html, render_unsubscribe_url
from lite_email_renderer import render_lite_email


def _sample_brief() -> dict:
    return {
        "mail_id": "mail-001",
        "date": "2026-06-09",
        "email_subject": "测试晨读",
        "today_theme": "基层治理",
        "today_focus": "聚焦协商治理中的现实堵点和解决思路。",
        "reading_guide": {},
        "today_three_things": {
            "theme": "基层治理",
            "must_remember_sentence": "先回应群众关切，再推动后续协商。",
            "daily_question": "如果你负责推进一项群众争议较大的公共工程，请谈谈工作思路。",
        },
        "featured_article": {
            "title": "把群众工作做细，协商才有基础",
            "source": "人民网",
            "published_at": "2026-06-09",
            "theme": "基层治理",
            "url": "https://example.com/featured",
            "one_sentence": "先解决群众最现实的急难愁盼，再推动公共事项协商，更容易形成共识。",
            "core_viewpoint": "协商治理的前提，是先把群众最关心的问题办到位。",
            "three_useful_points": ["先找准顾虑", "先解决急事", "再推动协商"],
            "exam_use": ["先把群众最关心的问题解决好，再谈后续推进。"],
            "rewritable_expression": "可用表达：先把群众最关心的问题解决好，再谈后续推进。",
            "article_framework_map": {
                "type": "评论",
                "main_thread": "先解难题，再聚共识",
                "steps": [
                    {"label": "找准问题", "content": "先把群众顾虑和现实堵点梳理清楚。"},
                    {"label": "回应急事", "content": "优先解决群众最在意的现实问题。"},
                    {"label": "推动协商", "content": "在公开沟通中逐步形成共识。"},
                ],
            },
        },
        "daily_question": {
            "question_type": "综合分析",
            "question": "如果你负责推进一项群众争议较大的公共工程，请谈谈工作思路。",
            "exam_focus": "先稳情绪，再推工作。",
            "answer_framework": [
                "摸清诉求：先把群众顾虑找准。",
                "先办急事：优先解决现实问题。",
                "公开协商：把方案摆到桌面上。",
            ],
            "candidate_answer": "这是完整版参考答案，不应该影响退订测试。",
            "output_prompt": "请用一句话写出这道题的开头表态。",
        },
        "today_takeaway": {
            "keywords": ["基层治理"],
            "common_knowledge_points": ["协商治理要兼顾效率与公平。"],
            "golden_sentences": [
                {"sentence": "治理要先回应群众关切，再推动长效机制。"},
            ],
        },
        "quick_reads": [
            {
                "title": "规范收费要先把规则讲清楚",
                "source": "光明网",
                "theme": "消费治理",
                "one_sentence": "收费规则透明，群众的理解成本才不会被转嫁。",
                "exam_value": "可作为基层治理中的沟通透明素材。",
            }
        ],
    }


def _sample_latest_json() -> dict:
    return {"brief": _sample_brief()}


def _snapshot_settings() -> dict[str, str]:
    return {
        "smtp_user": settings.smtp_user,
        "admin_report_emails_raw": settings.admin_report_emails_raw,
        "unsubscribe_email_raw": settings.unsubscribe_email_raw,
        "unsubscribe_mode": settings.unsubscribe_mode,
        "feedback_base_url": settings.feedback_base_url,
    }


def _restore_settings(snapshot: dict[str, str]) -> None:
    for key, value in snapshot.items():
        object.__setattr__(settings, key, value)


def test_default_unsubscribe_link_uses_mailto() -> None:
    snapshot = _snapshot_settings()
    try:
        object.__setattr__(settings, "smtp_user", "smtp@example.com")
        object.__setattr__(settings, "admin_report_emails_raw", "ops@example.com,backup@example.com")
        object.__setattr__(settings, "unsubscribe_email_raw", "")
        object.__setattr__(settings, "unsubscribe_mode", "mailto")
        object.__setattr__(settings, "feedback_base_url", "https://feedback.example.com/form")

        url = render_unsubscribe_url(_sample_brief())

        assert url.startswith("mailto:ops@example.com?")
        assert "subject=%E9%80%80%E8%AE%A2%E5%85%AC%E8%80%83%E6%99%A8%E8%AF%BB%E9%82%AE%E4%BB%B6" in url
        assert "%E4%BD%A0%E5%A5%BD%EF%BC%8C%E6%88%91%E6%83%B3%E6%9A%82%E5%81%9C%2F%E9%80%80%E8%AE%A2" in url
    finally:
        _restore_settings(snapshot)


def test_auto_unsubscribe_link_keeps_feedback_endpoint() -> None:
    snapshot = _snapshot_settings()
    try:
        object.__setattr__(settings, "unsubscribe_mode", "auto")
        object.__setattr__(settings, "feedback_base_url", "https://feedback.example.com/form")

        url = render_unsubscribe_url(_sample_brief())

        assert url.startswith("https://feedback.example.com/form?")
        assert "task=unsubscribe" in url
        assert "uid=__FEEDBACK_UID__" in url
        assert "email_hash=__FEEDBACK_EMAIL_HASH__" in url
    finally:
        _restore_settings(snapshot)


def test_lite_email_contains_unsubscribe_entry() -> None:
    snapshot = _snapshot_settings()
    try:
        object.__setattr__(settings, "smtp_user", "smtp@example.com")
        object.__setattr__(settings, "admin_report_emails_raw", "ops@example.com")
        object.__setattr__(settings, "unsubscribe_email_raw", "")
        object.__setattr__(settings, "unsubscribe_mode", "mailto")
        object.__setattr__(settings, "feedback_base_url", "")

        rendered = render_lite_email(_sample_latest_json())
    finally:
        _restore_settings(snapshot)

    assert "plain_text" in rendered
    assert "html_body" in rendered
    assert "如果你暂时不想继续接收，可以" in rendered["html_body"]
    assert "点击这里发送退订邮件" in rendered["html_body"]
    assert "我会手动处理。" in rendered["html_body"]
    assert "mailto:ops@example.com?" in rendered["html_body"]


def test_full_email_contains_unsubscribe_entry() -> None:
    snapshot = _snapshot_settings()
    try:
        object.__setattr__(settings, "smtp_user", "smtp@example.com")
        object.__setattr__(settings, "admin_report_emails_raw", "ops@example.com")
        object.__setattr__(settings, "unsubscribe_email_raw", "")
        object.__setattr__(settings, "unsubscribe_mode", "mailto")
        object.__setattr__(settings, "feedback_base_url", "")

        html_body = render_email_html(_sample_brief())
    finally:
        _restore_settings(snapshot)

    assert "如果你暂时不想继续接收，可以" in html_body
    assert "点击这里发送退订邮件" in html_body
    assert "mailto:ops@example.com?" in html_body
