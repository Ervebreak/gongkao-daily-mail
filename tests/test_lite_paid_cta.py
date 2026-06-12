from __future__ import annotations

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
                "candidate_answer": "这是完整版参考答案，不应该出现在 lite 邮件里。",
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


def test_lite_paid_cta_contains_mailto_plans_and_unsubscribe() -> None:
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

        rendered = render_lite_email(_sample_latest_json())
    finally:
        object.__setattr__(settings, "paid_trial_entry_url", original_paid_trial_entry_url)
        object.__setattr__(settings, "admin_report_emails_raw", original_admin_report_emails_raw)
        object.__setattr__(settings, "smtp_user", original_smtp_user)
        object.__setattr__(settings, "unsubscribe_email_raw", original_unsubscribe_email_raw)
        object.__setattr__(settings, "unsubscribe_mode", original_unsubscribe_mode)
        object.__setattr__(settings, "feedback_base_url", original_feedback_base_url)

    body = rendered["plain_text"] + rendered["html_body"]

    assert "完整版今天多什么" in body
    assert "今日一题参考答案" in body
    assert "文章框架图" in body
    assert "考场转化" in body
    assert "金句拆解" in body
    assert "周末 PDF 汇编" in body
    assert "4.9 元 / 7 天" in body
    assert "9.9 元 / 30 天" in body
    assert "回复“体验”领取说明" in body
    assert "填写报名表" in body
    assert "mailto:ops@example.com?" in body
    assert "subject=%E4%BD%93%E9%AA%8C%E5%AE%8C%E6%95%B4%E7%89%88%E6%99%A8%E8%AF%BB%E9%82%AE%E4%BB%B6" in body
    assert "body=%E4%BD%A0%E5%A5%BD%EF%BC%8C%E6%88%91%E6%83%B3%E4%BD%93%E9%AA%8C%E5%AE%8C%E6%95%B4%E7%89%88%E6%99%A8%E8%AF%BB%E9%82%AE%E4%BB%B6%EF%BC%8C%E8%AF%B7%E5%8F%91%E6%88%91%E5%86%85%E6%B5%8B%E8%AF%B4%E6%98%8E%E5%92%8C%E4%BB%98%E6%AC%BE%E6%96%B9%E5%BC%8F%E3%80%82" in body
    assert "https://paid.example.com/entry" in body
    assert "暂时不参加也没关系，免费简版会继续保留。" in body
    assert "点击这里发送退订邮件" in body
    assert "这是完整版参考答案，不应该出现在 lite 邮件里。" not in body
