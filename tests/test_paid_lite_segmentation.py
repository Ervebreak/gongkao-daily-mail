from __future__ import annotations

import json
import sys
import types

sys.modules.setdefault("requests", types.SimpleNamespace())

from config import settings
from email_sender import (
    parse_subscribers_csv_all_records,
    save_send_audit,
    split_recipient_records,
    update_send_audit_results,
)
from lite_email_renderer import render_lite_email


def test_paid_lite_recipient_segmentation() -> None:
    csv_text = """email,status,plan,paid_until,send_mode,note
paid@example.com,active,paid_trial,2026-06-30,,
expired@example.com,active,paid_monthly,2026-06-01,,
free@example.com,active,free,,,
gone@example.com,unsubscribed,paid_monthly,2026-06-30,,
"""
    records = parse_subscribers_csv_all_records(csv_text)

    segments = split_recipient_records(records, today="2026-06-07")

    assert [item["email"] for item in segments["full"]] == ["paid@example.com"]
    assert [item["email"] for item in segments["lite"]] == ["expired@example.com", "free@example.com"]
    assert [item["email"] for item in segments["skipped"]] == ["gone@example.com"]


def test_missing_paid_fields_default_to_active_free_lite() -> None:
    records = parse_subscribers_csv_all_records("email\nlegacy@example.com\n")

    segments = split_recipient_records(records, today="2026-06-07")

    assert segments["full"] == []
    assert [item["email"] for item in segments["lite"]] == ["legacy@example.com"]
    assert segments["skipped"] == []


def test_send_mode_overrides_plan_and_paid_until() -> None:
    csv_text = """email,status,plan,paid_until,send_mode,note
force_full@example.com,active,free,,full,
force_lite@example.com,active,paid_monthly,2026-06-30,lite,
force_none@example.com,active,paid_monthly,2026-06-30,none,
"""
    records = parse_subscribers_csv_all_records(csv_text)

    segments = split_recipient_records(records, today="2026-06-07")

    assert [item["email"] for item in segments["full"]] == ["force_full@example.com"]
    assert [item["email"] for item in segments["lite"]] == ["force_lite@example.com"]
    assert [item["email"] for item in segments["skipped"]] == ["force_none@example.com"]


def test_send_audit_records_send_results(tmp_path) -> None:
    original_output_dir = settings.output_dir
    object.__setattr__(settings, "output_dir", tmp_path)
    try:
        segments = split_recipient_records(
            parse_subscribers_csv_all_records(
                """email,status,plan,paid_until
full@example.com,active,paid_trial,2026-06-30
lite@example.com,active,free,
"""
            ),
            today="2026-06-07",
        )
        audit = save_send_audit("2026-06-07", segments, "test")
        update_send_audit_results(
            "2026-06-07",
            audit,
            {
                "success_count": 1,
                "fail_count": 0,
                "recipient_status": [{"email": "full@example.com", "status": "sent"}],
                "failures": [],
            },
            {
                "success_count": 0,
                "fail_count": 1,
                "recipient_status": [{"email": "lite@example.com", "status": "failed", "error": "smtp"}],
                "failures": [{"email": "lite@example.com", "error": "smtp"}],
            },
        )
        stored = json.loads((tmp_path / "send_audit_2026-06-07.json").read_text(encoding="utf-8"))

        assert stored["full_emails"] == ["full@example.com"]
        assert stored["lite_emails"] == ["lite@example.com"]
        assert stored["full_result"]["success_count"] == 1
        assert stored["lite_result"]["failures"] == [{"email": "lite@example.com", "error": "smtp"}]
    finally:
        object.__setattr__(settings, "output_dir", original_output_dir)


def test_render_lite_email_returns_dict_and_keeps_structured_preview() -> None:
    original_feedback_base_url = settings.feedback_base_url
    original_paid_trial_entry_url = settings.paid_trial_entry_url
    original_admin_report_emails_raw = settings.admin_report_emails_raw
    original_smtp_user = settings.smtp_user
    object.__setattr__(settings, "feedback_base_url", "https://feedback.example.com/form")
    object.__setattr__(settings, "paid_trial_entry_url", "")
    object.__setattr__(settings, "admin_report_emails_raw", "ops@example.com")
    object.__setattr__(settings, "smtp_user", "smtp@example.com")
    try:
        lite = render_lite_email(
            {
                "brief": {
                    "mail_id": "mail-lite-001",
                    "date": "2026-06-07",
                    "today_theme": "基层治理中的协同处置",
                    "email_subject": "升级后的免费简版",
                    "featured_article": {
                        "title": "把群众工作做成一张可执行清单",
                        "source": "人民网",
                        "published_at": "2026-06-07",
                        "theme": "基层治理",
                        "url": "https://example.com/featured",
                        "one_sentence": "先解决群众的急难愁盼，再推动公共事项协商，治理工作才有信任基础，也更容易把后续执行中的阻力提前化解掉。",
                        "rewritable_expression": "可用表达：把群众的烦心事先办成，再去谈需要大家配合的大事，这样后续推进才更容易形成稳定共识。",
                        "article_framework_map": {
                            "framework_style": "发现痛点：先摸清顾虑 → 化解阻力：先办急事 → 推动协商：再谈共识"
                        },
                    },
                    "today_takeaway": {
                        "golden_sentences": [{"sentence": "这条金句不应覆盖 featured rewritable_expression。"}],
                    },
                    "daily_question": {
                        "question": "如果你负责推进一项群众争议较大的公共工程，请谈谈工作思路。",
                        "answer_framework": [
                            "摸清诉求：先把群众顾虑和历史欠账找准。",
                            "先办急事：优先解决群众最急的现实问题。",
                            "公开协商：把方案摆到桌面上反复沟通。",
                        ],
                        "candidate_answer": "这是完整版参考答案，不应该出现在 lite 邮件里。",
                    },
                    "quick_reads": [
                        {
                            "title": "规范收费先把规则讲清楚",
                            "source": "光明网",
                            "theme": "消费治理",
                            "one_sentence": "收费标准如果藏在长条款里，最后承担理解成本的还是普通消费者，治理透明度也会随之被削弱。",
                        },
                        {
                            "title": "让技术红利真正落到中小主体",
                            "source": "人民网观点",
                            "theme": "数字普惠",
                            "one_sentence": "推动新技术普惠应用，关键是降低中小主体接入门槛并完善公共支持。",
                        },
                    ],
                },
                "weekly_pdf": {"oss_pdf_path": "oss://bucket/weekly.pdf"},
            }
        )
    finally:
        object.__setattr__(settings, "feedback_base_url", original_feedback_base_url)
        object.__setattr__(settings, "paid_trial_entry_url", original_paid_trial_entry_url)
        object.__setattr__(settings, "admin_report_emails_raw", original_admin_report_emails_raw)
        object.__setattr__(settings, "smtp_user", original_smtp_user)

    assert isinstance(lite, dict)
    assert set(lite) >= {"plain_text", "html_body"}
    assert isinstance(lite["plain_text"], str)
    assert isinstance(lite["html_body"], str)

    html_body = lite["html_body"]
    body = lite["plain_text"] + html_body
    assert "今日精读文章" in html_body
    assert ("3步看懂" in html_body) or ("先想 3 个角度" in html_body)
    assert "今日一题" in html_body
    assert "今日速读" in html_body
    assert "今日完整版亮点" in html_body
    assert "退订" in html_body
    assert "把群众工作做成一张可执行清单" in body
    assert "先解决群众的急难愁盼" in body
    assert "摸清诉求" in html_body
    assert "公开协商" in html_body
    assert "规范收费先把规则讲清楚" in html_body
    assert "让技术红利真正落到中小主体" in html_body
    assert "mailto:ops@example.com?" in body
    assert '<span style="font-weight:900;color:#0f172a;">1.</span>' not in html_body
    assert "这样后续推进才更容易形成稳定共识" in body
    assert "治理透明度也会随之被削弱" in body
    assert "这是完整版参考答案，不应该出现在 lite 邮件里。" not in body
    assert "oss://bucket/weekly.pdf" not in body
    assert "周末 PDF 下载" not in body


def test_render_lite_email_degrades_gracefully_for_partial_content() -> None:
    original_feedback_base_url = settings.feedback_base_url
    original_paid_trial_entry_url = settings.paid_trial_entry_url
    original_admin_report_emails_raw = settings.admin_report_emails_raw
    original_smtp_user = settings.smtp_user
    object.__setattr__(settings, "feedback_base_url", "https://feedback.example.com/form")
    object.__setattr__(settings, "paid_trial_entry_url", "")
    object.__setattr__(settings, "admin_report_emails_raw", "ops@example.com")
    object.__setattr__(settings, "smtp_user", "smtp@example.com")
    latest_json = {
        "brief": {
            "mail_id": "mail-lite-002",
            "date": "2026-06-07",
            "today_theme": "基层治理中的协同处置",
            "featured_article": {
                "source": "人民网",
                "published_at": "2026-06-07",
                "theme": "基层治理",
                "one_sentence": "先把群众最在意的现实问题处理好，再推进后续协商，更容易形成共识。",
                "rewritable_expression": "可用表达：先把急事办好，再把共识做实。",
            },
            "daily_question": {
                "question": "如果你负责推进一项群众争议较大的公共工程，请谈谈工作思路。",
                "answer_framework": [
                    "先摸诉求：先把群众顾虑和现实堵点找准。"
                ],
            },
            "quick_reads": [
                {
                    "title": "规范收费要先把规则讲清楚",
                    "source": "光明网",
                    "theme": "消费治理",
                    "one_sentence": "收费规则透明，群众的理解成本才不会被转嫁。",
                }
            ],
        }
    }
    try:
        lite = render_lite_email(latest_json)
    finally:
        object.__setattr__(settings, "feedback_base_url", original_feedback_base_url)
        object.__setattr__(settings, "paid_trial_entry_url", original_paid_trial_entry_url)
        object.__setattr__(settings, "admin_report_emails_raw", original_admin_report_emails_raw)
        object.__setattr__(settings, "smtp_user", original_smtp_user)

    assert isinstance(lite, dict)
    assert set(lite) >= {"plain_text", "html_body"}
    assert latest_json.get("lite_quality_warning") in (None, ["featured_title"])

    html_body = lite["html_body"]
    body = lite["plain_text"] + html_body
    assert "今日精读文章" in html_body
    assert "今日一题" in html_body
    assert ("先想 3 个角度" in html_body) or ("先搭作答框架" in html_body)
    assert "今日速读" in html_body
    assert "规范收费要先把规则讲清楚" in body
    assert "先摸诉求" in body
    assert "今日完整版亮点" in body
    assert "今天完整版会补充参考答案、文章框架图、考场转化和金句拆解" in body




