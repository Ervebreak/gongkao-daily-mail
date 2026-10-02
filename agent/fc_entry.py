"""阿里云 FC 入口：fc_agent_orchestrator.handler。

独立于 main.handler 部署，避免影响现有生产流水线。

路由：
- HTTP 请求（路径含 agent-confirm）→ 取消次日发送（agent/confirm.handle_confirm）
- 定时触发（mode=agent_nightly）→ 执行 Agent 编排（agent/orchestrator.run）
- 其他 → blocked
"""
from __future__ import annotations

import datetime as dt
from typing import Any


def _normalize(event: Any) -> dict[str, Any]:
    if event is None:
        return {}
    if isinstance(event, dict):
        return event
    return {"raw": str(event)}


def _is_http(event: dict[str, Any]) -> bool:
    if "httpMethod" in event or "requestContext" in event:
        return True
    path = str(event.get("path") or event.get("request_path") or "")
    return "agent-confirm" in path


def _is_confirm(event: dict[str, Any]) -> bool:
    path = str(event.get("path") or event.get("request_path") or "")
    query = event.get("query") or event.get("queryStringParameters") or {}
    if "agent-confirm" in path:
        return True
    if isinstance(query, dict) and any("agent-confirm" in str(k) for k in query):
        return True
    return False


def _is_test(event: dict[str, Any]) -> bool:
    mode = str(event.get("mode") or event.get("run_mode") or "").lower()
    return mode == "test" or bool(event.get("test") or event.get("test_mode"))


def _resolve_delivery_date(event: dict[str, Any]) -> str:
    value = event.get("delivery_date") or event.get("date")
    if value:
        return str(value).strip()
    # 定时 20:00 触发默认生成次日晨读；HTTP 手动触发默认今天。
    if _is_http(event):
        return dt.date.today().isoformat()
    return (dt.date.today() + dt.timedelta(days=1)).isoformat()


def handler(event: Any, context: Any = None) -> dict[str, Any]:
    payload = _normalize(event)
    try:
        if _is_http(payload):
            if _is_confirm(payload):
                from agent.confirm import handle_confirm

                return handle_confirm(payload)
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json; charset=utf-8"},
                "body": '{"error":"unsupported_http_path"}',
            }

        mode = str(payload.get("mode") or payload.get("event_type") or "").lower()
        if mode not in {"agent_nightly", "agent", "agent_daily"} and not payload.get("agent"):
            return {
                "status": "blocked",
                "reason": "unsupported_mode",
                "mode": mode or "unknown",
                "hint": 'use {"mode":"agent_nightly","delivery_date":"YYYY-MM-DD"}',
            }

        delivery_date = _resolve_delivery_date(payload)
        from agent.orchestrator import run

        return run(
            delivery_date,
            test_mode=_is_test(payload),
        )
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }


if __name__ == "__main__":
    import json
    import sys

    event = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {"mode": "agent_nightly", "test": True}
    print(json.dumps(handler(event), ensure_ascii=False, indent=2))
