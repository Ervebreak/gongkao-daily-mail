from __future__ import annotations

import email_renderer
import pytest
from config import settings
from lite_email_renderer import render_lite_email
from lite_paid_cta import (
    BLACKLISTED_LITE_ANSWER_MODULE_TERMS,
    SAFE_LITE_CTA_FALLBACK,
    is_valid_lite_paid_cta_hook,
)


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


def test_lite_paid_cta_uses_safe_brief_hook_and_keeps_entries() -> None:
    payload = _sample_latest_json()
    safe_hook = "完整版会补充文章框架图和原文问题链，并结合治理边界辨析、考场转化与表达积累，供申论分析题和面试复盘时按需使用。"
    payload["brief"]["lite_paid_cta"] = {
        "hook_type": "daily_question",
        "hook": safe_hook,
        "source_module": "daily_question",
        "fallback_used": False,
    }

    rendered = _render_with_cta_settings(payload)
    body = rendered["plain_text"] + rendered["html_body"]

    assert not hasattr(email_renderer, "_call_lite_paid_highlight_llm")
    assert "今天完整版多讲了什么" in body
    assert "完整版会补充" in body
    assert safe_hook in body
    assert "完整版还包含：文章框架图、考场转化、原文问题链、治理边界辨析、素材迁移、表达积累、周末 PDF 汇编。" in body
    plain_cta = rendered["plain_text"].split("今天完整版多讲了什么", 1)[1]
    html_cta = rendered["html_body"].split("今天完整版多讲了什么", 1)[1]
    for term in BLACKLISTED_LITE_ANSWER_MODULE_TERMS:
        assert term not in plain_cta
        assert term not in html_cta
    assert "体验说明：4.9 元 / 7 天｜9.9 元 / 30 天" in body
    assert "4.9 元 / 7 天" in body
    assert "9.9 元 / 30 天" in body
    assert "回复“体验”了解说明" in body
    assert "查看报名表" in body
    assert "早鸟内测" not in body
    assert "mailto:ops@example.com?" in body
    assert "https://paid.example.com/entry" in body
    assert "点击这里发送退订邮件" in body
    assert "这是完整版参考答案，不应出现在 lite 邮件里。" not in body


def test_lite_paid_cta_uses_latest_json_hook_when_brief_hook_missing() -> None:
    payload = _sample_latest_json()
    safe_hook = "完整版会补充文章框架图、原文问题链和治理边界辨析，并把素材迁移与表达积累落到申论分析和面试复盘场景中。"
    payload["lite_paid_cta"] = {
        "hook_type": "policy_coordinate",
        "hook": safe_hook,
        "source_module": "policy_coordinate",
        "fallback_used": False,
    }

    rendered = _render_with_cta_settings(payload)
    body = rendered["plain_text"] + rendered["html_body"]

    assert safe_hook in body
    assert "完整版会补充" in body


def test_lite_paid_cta_falls_back_when_hook_missing() -> None:
    payload = _sample_latest_json()

    rendered = _render_with_cta_settings(payload)
    body = rendered["plain_text"] + rendered["html_body"]

    assert SAFE_LITE_CTA_FALLBACK in body


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
    assert SAFE_LITE_CTA_FALLBACK in body


@pytest.mark.parametrize(
    "blacklisted_term",
    ["审题关键", "作答主线", "完整作答框架", "参考答案", "30秒答案"],
)
def test_lite_paid_cta_rejects_legacy_hooks_naming_full_answer_modules(blacklisted_term: str) -> None:
    payload = _sample_latest_json()
    legacy_hook = f"完整版会补充文章框架图、考场转化和{blacklisted_term}，并把素材迁移放到具体题型中。"
    payload["brief"]["lite_paid_cta"] = {
        "hook_type": "legacy",
        "hook": legacy_hook,
        "source_module": "daily_question",
        "fallback_used": False,
    }

    rendered = _render_with_cta_settings(payload)
    body = rendered["plain_text"] + rendered["html_body"]

    assert legacy_hook not in body
    assert SAFE_LITE_CTA_FALLBACK in body


def test_lite_paid_cta_revalidates_cached_legacy_hook() -> None:
    payload = _sample_latest_json()
    legacy_hook = "完整版会补充文章框架图、考场转化、审题关键和参考答案，并说明素材迁移场景。"
    payload["_lite_paid_highlight"] = legacy_hook

    rendered = _render_with_cta_settings(payload)
    body = rendered["plain_text"] + rendered["html_body"]

    assert legacy_hook not in body
    assert SAFE_LITE_CTA_FALLBACK in body
    assert payload["_lite_paid_highlight"] == SAFE_LITE_CTA_FALLBACK


def test_safe_lite_paid_cta_wording_passes_validation() -> None:
    payload = _sample_latest_json()
    hook = "完整版会展开文章框架图与原文问题链，补充治理边界辨析、素材迁移和表达积累，适合申论分析与面试复盘时按需使用。"

    assert is_valid_lite_paid_cta_hook(hook, payload["brief"])


@pytest.mark.parametrize(
    "hook",
    [
        "完整版会结合文章框架图和考场转化，按摸清诉求—先办急事—公开协商的顺序展开，并补充素材迁移场景。",
        "完整版会结合文章框架图和考场转化，先摸清诉求，再处理现实堵点，最后公开协商，并补充素材迁移场景。",
    ],
)
def test_lite_paid_cta_still_rejects_answer_label_chains(hook: str) -> None:
    payload = _sample_latest_json()

    assert not is_valid_lite_paid_cta_hook(hook, payload["brief"])
