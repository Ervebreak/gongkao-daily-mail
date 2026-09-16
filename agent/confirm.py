"""预览邮件与取消闸门。

Agent 候选通过门禁后：保存到正式候选存储（OSS/本地）→ 发送预览邮件
给管理员本人。次日早晨由现有发送链路（main.handler morning_send）
自动读取候选并群发，与方式一/方式二完全一致。

预览邮件是「安全网」：如果管理员发现内容有问题，可点击【取消次日发送】，
系统会把候选的质量门禁标记为 fail，次日早晨发送链路读到门禁失败即自动
阻断，不会发出去。不点击则照常自动发送。

取消链接使用 hmac 签名，仅当天有效；发送/取消均不注册为模型工具。
"""
from __future__ import annotations

import hashlib
import hmac
import html as _html
import os
from typing import Any
from urllib.parse import parse_qs

from config import settings
from agent.state import (
    STATE_BLOCKED,
    STATE_PUBLISHED,
    STATE_SENT,
    load_run,
    save_run,
)

# 预览邮件里提示的次日发送时间（与部署的 morning_send 定时器一致，纯提示用）
MORNING_SEND_HINT = os.environ.get("AGENT_MORNING_SEND_HINT", "次日早晨 07:30")


def _secret() -> str:
    value = os.environ.get("AGENT_CONFIRM_SECRET") or settings.download_tracking_secret or ""
    return value.strip()


def build_confirm_token(delivery_date: str, action: str) -> str:
    secret = _secret()
    if not secret:
        raise RuntimeError(
            "AGENT_CONFIRM_SECRET is not configured; cannot build cancel token."
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
            "AGENT_CONFIRM_BASE_URL is not configured; preview email cannot include cancel link."
        )
    return base


def confirm_url(delivery_date: str, action: str) -> str:
    token = build_confirm_token(delivery_date, action)
    return f"{_base_url()}/agent-confirm?date={delivery_date}&action={action}&token={token}"


def send_preview_email(delivery_date: str) -> dict[str, Any]:
    """把已保存候选渲染成预览邮件发给管理员本人，附带「取消次日发送」链接。"""
    from candidate_store import load_candidate
    from email_sender import send_email_to_recipients

    candidate, load_meta = load_candidate(delivery_date)
    if not candidate:
        raise RuntimeError(f"candidate missing for preview: {delivery_date}")
    subject = str(candidate.get("subject") or "")
    plain_text = str(candidate.get("plain_text") or "")
    html_body = str(candidate.get("html_body") or "")
    cancel = confirm_url(delivery_date, "cancel")

    footer_html = (
        '<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;'
        'font-family:sans-serif;font-size:14px;color:#374151;">'
        "<p><strong>✅ 本邮件是给管理员的预览，已保存为次日候选。</strong></p>"
        f"<p>如无问题，系统将于 <b>{_html.escape(MORNING_SEND_HINT)}</b> 自动发送给订阅用户，"
        "你无需任何操作。</p>"
        '<p style="color:#dc2626;">如内容有问题，请点击取消：'
        f'<a href="{_html.escape(cancel, quote=True)}" '
        'style="color:#dc2626;font-weight:600;">❌ 取消次日发送</a>'
        "（链接仅当天有效）</p>"
        "</div>"
    )

    preview_html = html_body + footer_html
    preview_subject = f"【预览·次日自动发送】{subject}"
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
        state.confirm_token = build_confirm_token(delivery_date, "cancel")
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
        "cancel_url": cancel,
        "send_result": result,
    }


# ---------------------------------------------------------------------------
# HTTP 取消处理（FC 入口路由到此处）
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


def _cancel_candidate(delivery_date: str) -> None:
    """把已保存候选的质量门禁标记为 fail，使次日发送链路自动阻断。

    发送链路（send_saved_candidate）读取候选时校验 quality_gate，
    overall != ok 即阻断，不会发出。不需要改动生产发送代码。
    """
    from candidate_store import load_candidate, save_candidate

    candidate, _ = load_candidate(delivery_date)
    if candidate is None:
        return
    candidate["quality_gate"] = {
        "overall": "fail",
        "p0_count": 1,
        "p0_issues": [
            {
                "module": "agent_cancel",
                "severity": "P0",
                "reason": "管理员在预览中取消次日发送",
            }
        ],
    }
    candidate["_agent_cancelled"] = True
    save_candidate(candidate)


def handle_confirm(event: Any) -> dict[str, Any]:
    """处理 /agent-confirm 请求（当前仅支持 cancel 动作）。"""
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

    if not delivery_date or action not in {"cancel"}:
        return _page("参数错误", "<p>缺少 date / action / token 参数，或不支持该动作。</p>")

    if not verify_confirm_token(delivery_date, action, token):
        return _page("校验失败", "<p>链接无效或已过期（仅当天有效）。</p>")

    state = load_run(delivery_date)
    if state is None:
        return _page("运行不存在", f"<p>日期 {delivery_date} 没有 Agent 运行记录。</p>")
    if state.state not in {STATE_PUBLISHED, STATE_SENT}:
        return _page(
            "状态不允许",
            f"<p>当前状态为 <b>{state.state}</b>，无法执行取消操作。</p>",
        )
    if state.state == STATE_SENT:
        return _page("已发送", "<p>该日候选已发送，无法取消。</p>")

    # cancel：标记候选门禁 fail + 运行状态 BLOCKED
    _cancel_candidate(delivery_date)
    state.transition(STATE_BLOCKED, note="cancelled by admin from preview")
    save_run(state)
    return _page(
        "已取消次日发送",
        f"<p>{delivery_date} 的候选已被标记为取消，次日早晨不会发送。</p>"
        "<p>如需重新生成，可删除对应候选后重新触发。</p>",
    )
