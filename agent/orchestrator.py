"""Agent Orchestrator 主程序。

职责：接收 delivery_date → 按状态机推进 → 在「选文」和「质检放行」
两个决策点调用模型 → 其余步骤全部执行受控工具（复用生产链路）→
候选通过门禁后保存到正式候选存储并发送预览（PUBLISHED），次日早晨
由现有发送链路自动群发，与方式一/方式二完全一致。

安全控制：
- 模型不能发明状态（迁移必须经过 state.transition 校验）
- 模型不能调用发布/发送工具（发送由次日早晨链路执行，可被预览邮件取消）
- 修复最多两轮；模型调用 / 工具调用有预算上限；异常立即 FAILED
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Optional

from config import settings
from agent.schemas import ModelDecision, parse_decision
from agent.state import (
    RunState,
    STATE_AUDITING,
    STATE_BLOCKED,
    STATE_CREATED,
    STATE_FAILED,
    STATE_GENERATING,
    STATE_REPAIRING,
    STATE_SEARCHING,
    STATE_SELECTING,
    STATE_SENT,
    STATE_PUBLISHED,
    TERMINAL_STATES,
    load_run,
    save_run,
)
from agent.tools import execute_tool, load_workspace, tool_descriptions
from agent import instructions


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


MAX_MODEL_CALLS = _env_int("AGENT_MAX_MODEL_CALLS", 8)
MAX_TOOL_CALLS = _env_int("AGENT_MAX_TOOL_CALLS", 20)
MAX_REPAIR_ROUNDS = _env_int("AGENT_MAX_REPAIR_ROUNDS", 2)


# ---------------------------------------------------------------------------
# 模型调用（Planner）：默认走百炼，支持注入确定性 Planner 供测试
# ---------------------------------------------------------------------------


class DeterministicPlanner:
    """test 模式兜底 / 离线测试用：不调用模型，按规则决策。

    select_first_n：选文阶段选前 N 篇。
    auto_pass：质检是否直接 PASS（False 时第一轮 REPAIR、第二轮 PASS）。
    """

    def __init__(self, select_first_n: int = 3, auto_pass: bool = True) -> None:
        self.select_first_n = select_first_n
        self.auto_pass = auto_pass

    def __call__(self, prompt: str, stage: str, context: dict[str, Any]) -> ModelDecision:
        if stage == "select":
            articles = context.get("articles") or []
            ids = [int(a["id"]) for a in articles[: self.select_first_n]]
            return ModelDecision(
                decision="CONTINUE",
                next_tool="select_articles",
                arguments={"article_ids": ids},
                reason=f"确定性策略：选择前 {len(ids)} 篇候选文章。",
            )
        if stage == "audit":
            issues = context.get("issues") or []
            if self.auto_pass:
                return ModelDecision(decision="PASS", reason="确定性策略：直接放行。")
            if context.get("repair_round", 0) == 0:
                return ModelDecision(
                    decision="REPAIR",
                    next_tool="repair_candidate",
                    issues=issues[:2] if issues else [],
                    reason="确定性策略：第一轮先修复。",
                )
            return ModelDecision(decision="PASS", reason="确定性策略：第二轮放行。")
        return ModelDecision(decision="BLOCKED", reason=f"未知 stage: {stage}")


def _default_model(test_mode: bool) -> str:
    if test_mode:
        return (
            settings.test_selection_llm_model
            or settings.test_llm_model
            or settings.selection_llm_model
            or settings.llm_model
        )
    return settings.selection_llm_model or settings.llm_model


def _call_model(
    state: RunState,
    prompt: str,
    stage: str,
    context: dict[str, Any],
    planner: Optional[Callable[[str, str, dict[str, Any]], ModelDecision]],
) -> ModelDecision:
    """调用一次模型（或确定性 Planner），返回结构化决策。"""
    state.model_calls += 1
    state.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save_run(state)
    if planner is not None:
        return planner(prompt, stage, context)
    # 生产 / 非 mock 测试：走百炼 chat_completion（json_object 模式）
    from llm_client import chat_completion

    system_prompt = instructions.build_system_prompt(tool_descriptions())
    raw = chat_completion(_default_model(settings.run_mode != "test"), prompt, system_prompt=system_prompt)
    return parse_decision(raw)


# ---------------------------------------------------------------------------
# 决策点 prompt 构造
# ---------------------------------------------------------------------------


def _select_prompt(delivery_date: str, articles: list[dict[str, Any]]) -> str:
    compact = [
        {
            "id": a["id"],
            "title": a["title"],
            "source": a["source"],
            "column": a["column"],
            "published_at": a["published_at"],
            "themes": a["themes"],
            "score": a["score"],
            "snippet": (a.get("snippet") or "")[:300],
        }
        for a in articles
    ]
    return (
        f"目标投递日期：{delivery_date}\n"
        f"候选文章 {len(compact)} 篇：\n"
        f"{json.dumps(compact, ensure_ascii=False, indent=2)}\n\n"
        "请从中选择 3~6 篇最具公考价值的主线/速读候选（优先官方媒体、主题贴近申论/面试热点、"
        "内容时效新、正文可读）。输出 JSON：{\"decision\":\"CONTINUE\",\"next_tool\":\"select_articles\","
        "\"arguments\":{\"article_ids\":[...]},\"reason\":\"选文理由\"}"
    )


def _audit_prompt(delivery_date: str, audit: dict[str, Any], repair_round: int) -> str:
    return (
        f"目标投递日期：{delivery_date}\n"
        f"当前修复轮次：{repair_round}（上限 {MAX_REPAIR_ROUNDS}）\n"
        f"质检结果：\n{json.dumps(audit, ensure_ascii=False, indent=2)}\n\n"
        "请决策：\n"
        "- 若 overall=ok：输出 {\"decision\":\"PASS\"}（系统随后自动保存候选、发送预览，次日早晨自动发送）。\n"
        "- 若存在可修复问题且未达轮次上限：输出 {\"decision\":\"REPAIR\",\"next_tool\":\"repair_candidate\","
        "\"issues\":[{\"module\":\"模块key\",\"severity\":\"P0|P1\",\"reason\":\"问题\"}]}。\n"
        "- 若无法修复或已达轮次上限：输出 {\"decision\":\"BLOCKED\",\"reason\":\"原因\"}。\n"
        "只能输出一个 JSON 对象。"
    )


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def run(
    delivery_date: str,
    test_mode: bool = False,
    planner: Optional[Callable[[str, str, dict[str, Any]], ModelDecision]] = None,
) -> dict[str, Any]:
    """执行一次 Agent 运行。返回结构化结果（状态机终态）。"""
    delivery_date = str(delivery_date or "").strip()
    if not delivery_date:
        raise ValueError("delivery_date is required.")

    state = load_run(delivery_date)
    if state is not None and state.state == STATE_PUBLISHED:
        return {
            "status": "already_published",
            "delivery_date": delivery_date,
            "run_id": state.run_id,
            "state": state.state,
            "message": "本轮候选已生成并保存，预览邮件已发送，将按次日早晨发送链路自动发送。",
        }
    if state is not None and state.state in TERMINAL_STATES:
        return {
            "status": "already_terminal",
            "delivery_date": delivery_date,
            "run_id": state.run_id,
            "state": state.state,
            "message": f"该日期已有终态运行（{state.state}），不重复执行。",
        }

    if state is None:
        state = RunState(
            run_id=f"{delivery_date}-agent-v1",
            delivery_date=delivery_date,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            updated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        save_run(state)

    use_mock = test_mode and (settings.test_llm_model or "").strip().lower() == "mock"
    if planner is None and use_mock:
        planner = DeterministicPlanner()
    if planner is None and not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is required for agent orchestration.")

    try:
        return _run_pipeline(state, test_mode=test_mode, planner=planner)
    except Exception as exc:
        state.last_error = str(exc)[:2000]
        try:
            state.transition(STATE_FAILED, note=f"exception: {exc}")
        except Exception:
            state.state = STATE_FAILED
            state.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        save_run(state)
        return {
            "status": "failed",
            "delivery_date": delivery_date,
            "run_id": state.run_id,
            "state": state.state,
            "error": str(exc),
        }


def _run_pipeline(
    state: RunState,
    *,
    test_mode: bool,
    planner: Optional[Callable[[str, str, dict[str, Any]], ModelDecision]],
) -> dict[str, Any]:
    delivery_date = state.delivery_date

    def _refresh() -> RunState:
        """工具会在磁盘上更新 state（如选中文章 id），主循环必须重新加载，
        否则旧对象覆盖磁盘会丢失工具写入的字段。"""
        nonlocal state
        fresh = load_run(delivery_date)
        if fresh is not None:
            state = fresh
        return state

    def _guard() -> None:
        if state.model_calls >= MAX_MODEL_CALLS:
            raise RuntimeError(f"model call budget exhausted ({MAX_MODEL_CALLS})")
        if state.tool_calls >= MAX_TOOL_CALLS:
            raise RuntimeError(f"tool call budget exhausted ({MAX_TOOL_CALLS})")

    # 1) 搜索文章（确定性）
    state.transition(STATE_SEARCHING, note="start search")
    save_run(state)
    search = execute_tool("search_articles", {}, delivery_date=delivery_date, test_mode=test_mode)
    if not search.get("articles"):
        raise RuntimeError("search_articles returned no articles.")
    _refresh()

    # 2) 模型决策：选文
    _guard()
    state.transition(STATE_SELECTING, note="model selects articles")
    save_run(state)
    decision = _call_model(
        state,
        _select_prompt(delivery_date, search["articles"]),
        "select",
        {"articles": search["articles"]},
        planner,
    )
    if decision.decision != "CONTINUE" or decision.next_tool != "select_articles":
        state.transition(STATE_BLOCKED, note=f"select stage invalid decision: {decision.decision}/{decision.next_tool}")
        save_run(state)
        return _result(state, "blocked", "select stage invalid decision")
    execute_tool(
        "select_articles",
        decision.arguments,
        delivery_date=delivery_date,
        test_mode=test_mode,
    )
    _refresh()

    # 3) 生成 brief（确定性）
    _guard()
    state.transition(STATE_GENERATING, note="generate brief")
    save_run(state)
    execute_tool("generate_brief", {}, delivery_date=delivery_date, test_mode=test_mode)
    _refresh()

    # 4) 渲染 + 质检（确定性）
    state.transition(STATE_AUDITING, note="render and audit")
    save_run(state)
    execute_tool("render_candidate", {}, delivery_date=delivery_date, test_mode=test_mode)
    audit = execute_tool("audit_candidate", {}, delivery_date=delivery_date, test_mode=test_mode)
    _refresh()

    # 5) 模型决策循环：PASS / REPAIR / BLOCKED
    while True:
        _guard()
        if audit.get("overall") == "ok":
            decision = _call_model(
                state,
                _audit_prompt(delivery_date, audit, state.repair_round),
                "audit",
                {
                    "issues": audit.get("issues") or [],
                    "repair_round": state.repair_round,
                },
                planner,
            )
        else:
            # 门禁硬失败（P0）：不允许模型放行，只能修复或阻断。
            if state.repair_round >= MAX_REPAIR_ROUNDS:
                state.transition(STATE_BLOCKED, note="P0 gate fail after max repair rounds")
                save_run(state)
                return _result(state, "blocked", "P0 gate fail after max repair rounds")
            decision = ModelDecision(
                decision="REPAIR",
                next_tool="repair_candidate",
                issues=audit.get("issues") or [],
                reason="门禁硬失败，需修复",
            )

        if decision.decision == "PASS":
            if audit.get("overall") != "ok":
                state.transition(STATE_BLOCKED, note="model PASS while gate not ok")
                save_run(state)
                return _result(state, "blocked", "model PASS while gate not ok")
            break

        if decision.decision == "REPAIR":
            if state.repair_round >= MAX_REPAIR_ROUNDS:
                state.transition(STATE_BLOCKED, note="repair rounds exhausted")
                save_run(state)
                return _result(state, "blocked", "repair rounds exhausted")
            state.transition(STATE_REPAIRING, note=f"repair round {state.repair_round + 1}")
            save_run(state)
            execute_tool("repair_candidate", {}, delivery_date=delivery_date, test_mode=test_mode)
            _refresh()
            state.transition(STATE_AUDITING, note="re-audit after repair")
            save_run(state)
            execute_tool("render_candidate", {}, delivery_date=delivery_date, test_mode=test_mode)
            audit = execute_tool("audit_candidate", {}, delivery_date=delivery_date, test_mode=test_mode)
            _refresh()
            continue

        # BLOCKED 或未知决策
        state.transition(STATE_BLOCKED, note=decision.reason or "blocked by model")
        save_run(state)
        return _result(state, "blocked", decision.reason or "blocked by model")

    # 6) PASS：保存候选到正式存储（OSS/本地）→ 发预览 → PUBLISHED（等次日早晨自动发送）
    _guard()
    execute_tool("save_candidate", {}, delivery_date=delivery_date, test_mode=test_mode)
    _refresh()
    from agent.confirm import send_preview_email

    preview = send_preview_email(delivery_date)
    _refresh()  # send_preview_email 会写入 cancel_token，必须重新加载
    state.transition(
        STATE_PUBLISHED,
        note="candidate saved and preview sent; morning send pipeline will deliver",
    )
    save_run(state)
    return {
        "status": "published",
        "delivery_date": delivery_date,
        "run_id": state.run_id,
        "state": state.state,
        "preview": preview,
        "model_calls": state.model_calls,
        "tool_calls": state.tool_calls,
        "repair_round": state.repair_round,
    }


def _result(state: RunState, status: str, reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "delivery_date": state.delivery_date,
        "run_id": state.run_id,
        "state": state.state,
        "reason": reason,
        "model_calls": state.model_calls,
        "tool_calls": state.tool_calls,
        "repair_round": state.repair_round,
    }
