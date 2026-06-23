from __future__ import annotations

import sys
import types

sys.modules.setdefault("requests", types.SimpleNamespace())

import email_sender
from config import settings
from email_renderer import render_email_html
from lite_email_renderer import render_lite_email


def _sample_brief() -> dict:
    return {
        "mail_id": "mail-referral-001",
        "date": "2026-06-22",
        "email_subject": "测试晨读",
        "today_theme": "基层治理",
        "today_focus": "聚焦群众诉求响应与协商推进。",
        "reading_guide": {},
        "today_three_things": {
            "theme": "基层治理",
            "must_remember_sentence": "先回应现实诉求，再推动协商治理。",
            "daily_question": "如果你负责推进一项争议较大的公共工程，请谈谈工作思路。",
        },
        "featured_article": {
            "title": "把群众工作做成闭环",
            "source": "人民日报",
            "published_at": "2026-06-22",
            "theme": "基层治理",
            "url": "https://example.com/featured",
            "one_sentence": "先把群众最现实的困难办到位，再推动后续协商，更容易形成共识。",
            "rewritable_expression": "先回应现实诉求，再推动协商治理。",
            "article_framework_map": {
                "steps": [
                    {"label": "找准问题", "content": "先把群众顾虑摸清楚。"},
                    {"label": "先办急事", "content": "优先解决最现实的问题。"},
                    {"label": "公开协商", "content": "在沟通中形成共识。"},
                ]
            },
        },
        "daily_question": {
            "question": "如果你负责推进一项争议较大的公共工程，请谈谈工作思路。",
            "answer_framework": [
                "摸清诉求：先把群众顾虑找准。",
                "先办急事：优先解决现实问题。",
                "公开协商：把方案摆到桌面上反复沟通。",
            ],
            "candidate_answer": "这是完整版参考答案，不应该出现在免费简版或推荐模块里。",
        },
        "quick_reads": [
            {
                "title": "规范收费要先把规则讲清楚",
                "source": "光明网",
                "theme": "消费治理",
                "one_sentence": "收费规则透明，理解成本才不会被转嫁。",
            },
            {
                "title": "让技术红利真正落到中小主体",
                "source": "人民网观点",
                "theme": "数字普惠",
                "one_sentence": "推动技术普惠应用，关键是降低接入门槛。",
            },
        ],
        "today_takeaway": {
            "keywords": ["基层治理", "公开协商"],
            "common_knowledge_points": ["基层治理要兼顾效率与公平。"],
            "golden_sentences": [{"sentence": "治理要先回应群众关切，再推动长效机制。"}],
        },
    }


def _sample_latest_json() -> dict:
    return {"brief": _sample_brief()}


def _snapshot_settings() -> dict[str, str]:
    return {
        "referral_entry_url": settings.referral_entry_url,
        "smtp_user": settings.smtp_user,
        "admin_report_emails_raw": settings.admin_report_emails_raw,
        "unsubscribe_email_raw": settings.unsubscribe_email_raw,
        "unsubscribe_mode": settings.unsubscribe_mode,
        "feedback_base_url": settings.feedback_base_url,
    }


def _restore_settings(snapshot: dict[str, str]) -> None:
    for key, value in snapshot.items():
        object.__setattr__(settings, key, value)


def _with_referral_settings() -> dict[str, str]:
    snapshot = _snapshot_settings()
    object.__setattr__(settings, "referral_entry_url", "https://example.com/referral-entry")
    object.__setattr__(settings, "smtp_user", "smtp@example.com")
    object.__setattr__(settings, "admin_report_emails_raw", "ops@example.com")
    object.__setattr__(settings, "unsubscribe_email_raw", "")
    object.__setattr__(settings, "unsubscribe_mode", "mailto")
    object.__setattr__(settings, "feedback_base_url", "")
    return snapshot


def test_full_recipient_with_referral_code_gets_full_referral_copy() -> None:
    snapshot = _with_referral_settings()
    try:
        plain_text = "FULL BODY"
        html_body = render_email_html(_sample_brief())
        personalized_plain, personalized_html = email_sender.personalize_email_payload_for_recipient(
            plain_text,
            html_body,
            {
                "email": "full@example.com",
                "uid": "u-full",
                "email_hash": "hash-full",
                "variant": "full_normal",
                "referral_code": "FULL123",
            },
        )
    finally:
        _restore_settings(snapshot)

    combined = personalized_plain + personalized_html
    assert "推荐给备考同学" in combined
    assert "你的完整版有效期延长 7 天" in combined
    assert "你的推荐码：FULL123" in combined
    assert "https://example.com/referral-entry" in combined
    assert "mailto:ops@example.com?" in combined


def test_lite_recipient_with_referral_code_gets_lite_referral_copy() -> None:
    snapshot = _with_referral_settings()
    try:
        rendered = render_lite_email(_sample_latest_json())
        personalized_plain, personalized_html = email_sender.personalize_email_payload_for_recipient(
            rendered["plain_text"],
            rendered["html_body"],
            {
                "email": "lite@example.com",
                "uid": "u-lite",
                "email_hash": "hash-lite",
                "variant": "free_lite",
                "referral_code": "LITE123",
            },
        )
    finally:
        _restore_settings(snapshot)

    combined = personalized_plain + personalized_html
    assert "推荐解锁完整版" in combined
    assert "你将获得 7 天完整版权益" in combined
    assert "你的推荐码：LITE123" in combined
    assert "https://example.com/referral-entry" in combined
    assert "点击这里发送退订邮件" in combined
    assert "这是完整版参考答案，不应该出现在免费简版或推荐模块里。" not in combined


def test_referral_footer_hidden_when_referral_code_missing() -> None:
    snapshot = _with_referral_settings()
    try:
        rendered = render_lite_email(_sample_latest_json())
        personalized_plain, personalized_html = email_sender.personalize_email_payload_for_recipient(
            rendered["plain_text"],
            rendered["html_body"],
            {
                "email": "lite@example.com",
                "uid": "u-lite",
                "email_hash": "hash-lite",
                "variant": "free_lite",
                "referral_code": "",
            },
        )
    finally:
        _restore_settings(snapshot)

    combined = personalized_plain + personalized_html
    assert "推荐解锁完整版" not in combined
    assert "推荐给备考同学" not in combined


def test_referral_footer_hidden_when_entry_url_missing() -> None:
    snapshot = _snapshot_settings()
    try:
        object.__setattr__(settings, "referral_entry_url", "")
        object.__setattr__(settings, "smtp_user", "smtp@example.com")
        object.__setattr__(settings, "admin_report_emails_raw", "ops@example.com")
        object.__setattr__(settings, "unsubscribe_email_raw", "")
        object.__setattr__(settings, "unsubscribe_mode", "mailto")
        object.__setattr__(settings, "feedback_base_url", "")
        html_body = render_email_html(_sample_brief())
        personalized_plain, personalized_html = email_sender.personalize_email_payload_for_recipient(
            "FULL BODY",
            html_body,
            {
                "email": "full@example.com",
                "uid": "u-full",
                "email_hash": "hash-full",
                "variant": "full_normal",
                "referral_code": "FULL123",
            },
        )
    finally:
        _restore_settings(snapshot)

    combined = personalized_plain + personalized_html
    assert "推荐给备考同学" not in combined
    assert "https://example.com/referral-entry" not in combined


def test_referral_fields_do_not_affect_try_variant_segmentation() -> None:
    record = {
        "email": "try@example.com",
        "status": "active",
        "plan": "try",
        "paid_until": "2026-06-25",
        "send_mode": "full",
        "referral_code": "TRY123",
        "referred_by": "ABC999",
    }

    normalized = email_sender.normalize_recipient_record(record)

    assert normalized["referral_code"] == "TRY123"
    assert normalized["referred_by"] == "ABC999"
    assert email_sender.recipient_variant(record, today="2026-06-22") == "full_normal"


def test_subscribers_csv_table_supports_referral_columns() -> None:
    table = email_sender.parse_subscribers_csv_table(
        "uid,email,status,plan,paid_until,send_mode,referral_code,referred_by\n"
        "u1,test@example.com,active,free,,lite,ABC123,REF001\n"
    )

    assert "referral_code" in table["fieldnames"]
    assert "referred_by" in table["fieldnames"]
    assert table["records"][0]["referral_code"] == "ABC123"
    assert table["records"][0]["referred_by"] == "REF001"


def test_missing_referral_code_column_is_backfilled_and_generated() -> None:
    table = email_sender.parse_subscribers_csv_table(
        "uid,email,status,plan,paid_until,send_mode\n"
        "u1,Test@Example.com,active,free,,lite\n"
    )

    assert "referral_code" in table["fieldnames"]
    assert "referred_by" in table["fieldnames"]
    assert table["records"][0]["referral_code"] == "GK973DFE"
    assert table["records"][0]["referred_by"] == ""
    assert table["referral_backfill_meta"]["subscribers_referral_code_updates"] == 1
    assert table["referral_backfill_meta"]["subscribers_referral_field_backfill_needed"] is True


def test_existing_referral_code_is_not_overwritten() -> None:
    table = email_sender.parse_subscribers_csv_table(
        "uid,email,status,plan,paid_until,send_mode,referral_code,referred_by\n"
        "u1,test@example.com,active,free,,lite,KEEP01,\n"
    )

    assert table["records"][0]["referral_code"] == "KEEP01"
    assert table["referral_backfill_meta"]["subscribers_referral_code_updates"] == 0
