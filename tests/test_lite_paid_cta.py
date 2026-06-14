from __future__ import annotations

import email_renderer
from config import settings
from lite_email_renderer import render_lite_email


def _sample_latest_json() -> dict:
    return {
        "brief": {
            "mail_id": "mail-lite-cta-001",
            "date": "2026-06-12",
            "today_theme": "基层治理中的协同推进",
            "featured_article": {
                "title": "把群众工作做成一张可执行清单",
                "source": "人民日报",
                "published_at": "2026-06-12",
                "theme": "基层治理",
                "url": "https://example.com/featured",
                "one_sentence": "先解决群众最在意的现实问题，再推进后续协商，治理工作才更容易形成稳定共识。",
                "rewritable_expression": "可用表达：先把急事办好，再把共识做实。",
            },
            "daily_question": {
                "question": "如果你负责推进一项群众争议较大的公共工程，请谈谈工作思路。",
                "answer_framework": [
                    "摸清诉求：先把群众顾虑和现实堵点找准。",
                    "先办急事：优先解决群众最急的现实问题。",
                    "公开协商：把方案摆到桌面上反复沟通。",
                ],
                "candidate_answer": "这是完整版参考答案，不应出现在 lite 邮件里。",
            },
            "quick_reads": [
                {
                    "title": "规范收费要先把规则讲清楚",
                    "source": "光明网",
                    "theme": "消费治理",
                    "one_sentence": "收费规则透明，群众的理解成本才不会被转嫁。",
                },
                {
                    "title": "让技术红利真正落到中小主体",
                    "source": "人民网观点",
                    "theme": "数字普惠",
                    "one_sentence": "推动新技术普惠应用，关键是降低中小主体接入门槛。",
                },
            ],
        }
    }


def _render_with_cta_settings(payload: dict) -> dict[str, str]:
    original_paid_trial_entry_url = settings.paid_trial_entry_url
    original_admin_report_emails_raw = settings.admin_report_emails_raw
    original_smtp_user = settings.smtp_user
    original_unsubscribe_email_raw = settings.unsubscribe_email_raw
    original_unsubscribe_mode = settings.unsubscribe_mode
    original_feedback_base_url = settings.feedback_base_url
    try:
        object.__setattr__(settings, "paid_trial_entry_url", "https://paid.example.com/entry")
        object.__setattr__(settings, "admin_report_emails_raw", "ops@example.com")
        object.__setattr__(settings, "smtp_user", "smtp@example.com")
        object.__setattr__(settings, "unsubscribe_email_raw", "")
        object.__setattr__(settings, "unsubscribe_mode", "mailto")
        object.__setattr__(settings, "feedback_base_url", "")
        return render_lite_email(payload)
    finally:
        object.__setattr__(settings, "paid_trial_entry_url", original_paid_trial_entry_url)
        object.__setattr__(settings, "admin_report_emails_raw", original_admin_report_emails_raw)
        object.__setattr__(settings, "smtp_user", original_smtp_user)
        object.__setattr__(settings, "unsubscribe_email_raw", original_unsubscribe_email_raw)
        object.__setattr__(settings, "unsubscribe_mode", original_unsubscribe_mode)
        object.__setattr__(settings, "feedback_base_url", original_feedback_base_url)


def test_lite_paid_cta_uses_brief_hook_and_keeps_entries() -> None:
    payload = _sample_latest_json()
    payload["brief"]["lite_paid_cta"] = {
        "hook_type": "daily_question",
        "hook": "今天这道题适合练“群众诉求复杂、推进受阻”类场景，完整版会补充闭环推进思路，适合迁移到基层治理和公共工程推进题。",
        "source_module": "daily_question",
        "fallback_used": False,
    }

    rendered = _render_with_cta_settings(payload)
    body = rendered["plain_text"] + rendered["html_body"]

    assert not hasattr(email_renderer, "_call_lite_paid_highlight_llm")
    assert "想看今天的完整版？" in body
    assert "今日完整版亮点" in body
    assert "群众诉求复杂、推进受阻" in body
    assert "完整版还包含：参考答案、框架图、考场转化、金句拆解、周末 PDF。" in body
    assert "4.9 元 / 7 天" in body
    assert "9.9 元 / 30 天" in body
    assert "回复“体验”领取说明" in body
    assert "填写报名表" in body
    assert "mailto:ops@example.com?" in body
    assert "https://paid.example.com/entry" in body
    assert "点击这里发送退订邮件" in body
    assert "这是完整版参考答案，不应出现在 lite 邮件里。" not in body


def test_lite_paid_cta_uses_latest_json_hook_when_brief_hook_missing() -> None:
    payload = _sample_latest_json()
    payload["lite_paid_cta"] = {
        "hook_type": "policy_coordinate",
        "hook": "今天的政策坐标点出了一句适合记忆的权威表达，完整版会继续讲清它怎样迁移到基层治理和民生服务类题。",
        "source_module": "policy_coordinate",
        "fallback_used": False,
    }

    rendered = _render_with_cta_settings(payload)
    body = rendered["plain_text"] + rendered["html_body"]

    assert "今天的政策坐标点出了一句适合记忆的权威表达" in body
    assert "今日完整版亮点" in body


def test_lite_paid_cta_falls_back_when_hook_missing() -> None:
    payload = _sample_latest_json()

    rendered = _render_with_cta_settings(payload)
    body = rendered["plain_text"] + rendered["html_body"]

    assert "今日完整版亮点" in body
    assert "今天完整版会补充参考答案、文章框架图、考场转化和金句拆解" in body


def test_lite_paid_cta_falls_back_when_hook_contains_banned_words() -> None:
    payload = _sample_latest_json()
    payload["brief"]["lite_paid_cta"] = {
        "hook_type": "daily_question",
        "hook": "今天这条内容是内部资料，几乎必考，不看就亏。",
        "source_module": "daily_question",
        "fallback_used": False,
    }

    rendered = _render_with_cta_settings(payload)
    body = rendered["plain_text"] + rendered["html_body"]

    assert "今天这条内容是内部资料，几乎必考，不看就亏。" not in body
    assert "今天完整版会补充参考答案、文章框架图、考场转化和金句拆解" in body
