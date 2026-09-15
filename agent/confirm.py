"""人工确认闸门（Human-in-the-loop）。

Agent 生成候选并质检通过后，不会自动发布/发送；系统先发送一封
「预览邮件」给管理员本人，邮件内带确认 / 拒绝链接（hmac 签名，
仅当天有效）。管理员点击确认后，系统才调用现有发送链路群发。
拒绝则进入 BLOCKED 终态。

发布/发送工具不注册给模型——只能通过这里的人工确认触发，这是
Agent 无法绕过的安全边界。
"""
from __future__ import annotations

import hashlib
import hmac
import html as _html
import json
import os
import time
from typing import Any, Optional
from urllib.parse import parse_qs

from config import settings
from agent.state import (
    RunState,
    STATE_BLOCKED,
    STATE_PUBLISHED,
    STATE_SENT,
    STATE_WAITING_FOR_APPROVAL,
    load_run,
    save_run,
)


def _secret() -> str:
    value = os.environ.get("AGENT_CONFIRM_SECRET") or settings.download_tracking_secret or ""
    return value.strip()


def build_confirm_token(delivery_date: str, action: str) -> str:
    secret = _secret()
    if not secret:
        raise RuntimeError(
            "AGENT_CONFIRM_SECRET is not configured; cannot build confirm token."
        )
    message = f"{delivery_date}|{action}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_confirm_token(delivery_date: str, action: str, token: str) -> bool:
    if not token:
        return False
    expected = build_confirm_token(delivery_date, action)
    return hmac.compare_digest(expected, token)


def _base_url() -> str:
    base = (os.environ.get("AGENT_CONFIRM_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError(
            "AGENT_CONFIRM_BASE_URL is not configured; preview email cannot include confirm links."
        )
    return base


def confirm_url(delivery_date: str, action: str) -> str:
    token = build_confirm_token(delivery_date, action)
    return f"{_base_url()}/agent-confirm?date={delivery_date}&action={action}&token={token}"


def send_preview_email(delivery_date: str) -> dict[str, Any]:
    """把已保存候选渲染成预览邮件，发给管理员本人，附带确认/拒绝链接。"""
    from candidate_store import load_candidate
    from email_sender import send_email_to_recipients

    candidate, load_meta = load_candidate(delivery_date)
    if not candidate:
        raise RuntimeError(f"candidate missing for preview: {delivery_date}")
    subject = str(candidate.get("subject") or "")
    plain_text = str(candidate.get("plain_text") or "")
    html_body = str(candidate.get("html_body") or "")
    approve = confirm_url(delivery_date, "approve")
    reject = confirm_url(delivery_date, "reject")

    footer_html = (
        '<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;'
        'font-family:sans-serif;font-size:14px;color:#374151;">'
        '<p><strong>这是发给管理员的预览，尚未发送给订阅用户。</strong></p>'
        '<p>确认无误后点击发送：<a href="%s" '
        'style="display:inline-block;padding:8px 18px;background:#16a34a;color:#fff;'
        'text-decoration:none;border-radius:6px;">✅ 确认发送</a></p>'
        '<p style="color:#9ca3af;">如内容有问题，请点击：'
        '<a href="%s" style="color:#dc2626;">拒绝并标记失败</a>（链接仅当天有效）</p>'
        "</div>"
    ) % (_html.escape(approve, quote=True), _html.escape(reject, quote=True))

    preview_html = html_body + footer_html
    preview_subject = f"【预览·请确认】{subject}"
    result = send_email_to_recipients(
        preview_subject,
        plain_text,
        preview_html,
        [settings.smtp_user],
        recipient_source="agent_preview",
    )
    state = load_run(delivery_date)
    if state is not None:
        state.preview_sent = bool(result.get("success_count", 0) > 0)
        state.confirm_token = build_confirm_token(delivery_date, "approve")
        state.log_event(
            "preview_email_sent",
            to=settings.smtp_user,
            success_count=result.get("success_count"),
            fail_count=result.get("fail_count"),
        )
        save_run(state)
    return {
        "preview_sent": True,
        "to": settings.smtp_user,
        "subject": preview_subject,
        "approve_url": approve,
        "reject_url": reject,
        "send_result": result,
    }


# ---------------------------------------------------------------------------
# HTTP 确认处理（FC 入口路由到此处）
# ---------------------------------------------------------------------------


def _page(title: str, body: str) -> dict[str, Any]:
    html = (
        "<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>公考晨读 Agent</title></head>"
        "<body style='font-family:sans-serif;max-width:560px;margin:64px auto;"
        "padding:0 20px;line-height:1.7;color:#111827;'>"
        f"<h2 style='font-size:20px;'>{_html.escape(title)}</h2>"
        f"<div>{body}</div>"
        "</body></html>"
    )
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": html,
    }


def handle_confirm(event: Any) -> dict[str, Any]:
    """处理 /agent-confirm 请求。event 需为已 normalize 的 dict，含 query 参数。"""
    query = event.get("query") or event.get("queryStringParameters") or {}
    if isinstance(query, str):
        query = parse_qs(query)
    params: dict[str, str] = {}
    for key, value in (query or {}).items():
        if isinstance(value, list) and value:
            params[str(key)] = str(value[0])
        elif value is not None:
            params[str(key)] = str(value)

    delivery_date = (params.get("date") or "").strip()
    action = (params.get("action") or "").strip().lower()
    token = (params.get("token") or "").strip()

    if not delivery_date or action not in {"approve", "reject"}:
        return _page("参数错误", "<p>缺少 date / action / token 参数。</p>")

    if not verify_confirm_token(delivery_date, action, token):
        return _page("校验失败", "<p>链接无效或已过期（仅当天有效）。</p>")

    state = load_run(delivery_date)
    if state is None:
        return _page("运行不存在", f"<p>日期 {delivery_date} 没有 Agent 运行记录。</p>")
    if state.state != STATE_WAITING_FOR_APPROVAL:
        return _page(
            "状态不允许",
            f"<p>当前状态为 <b>{state.state}</b>，不是 WAITING_FOR_APPROVAL，无法执行该操作。</p>",
        )

    if action == "reject":
        state.transition(STATE_BLOCKED, note="rejected by admin")
        save_run(state)
        return _page("已拒绝", f"<p>{delivery_date} 候选已被标记为 BLOCKED，不会发送。</p>")

    # approve：调用现有发送链路（读候选 → 门禁复查 → 分段发送）
    from main import send_saved_candidate

    state.published = True
    state.transition(STATE_PUBLISHED, note="approved by admin, sending")
    save_run(state)
    try:
        send_result = send_saved_candidate(
            {"mode": "candidate_send", "delivery_date": delivery_date}
        )
    except Exception as exc:
        state.last_error = str(exc)[:2000]
        state.transition(STATE_BLOCKED, note=f"send failed after approval: {exc}")
        save_run(state)
        return _page(
            "发送失败",
            f"<p>发送链路异常：{_html.escape(str(exc))}。状态已标记 BLOCKED。</p>",
        )

    sent = bool(send_result and send_result.get("status") == "ok")
    if sent:
        state.sent = True
        state.transition(STATE_SENT, note="sent to subscribers")
        save_run(state)
    else:
        state.transition(STATE_BLOCKED, note=f"send blocked by pipeline: {send_result}")
        save_run(state)
    reason = (send_result or {}).get("reason") or send_result.get("status") or "unknown"
    body = (
        f"<p>发送结果：<b>{'成功' if sent else '未发送'}</b></p>"
        f"<p>流水线返回：{_html.escape(str(reason))}</p>"
    )
    return _page("已确认发送", body)
