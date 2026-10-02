"""Agent 运行状态机与断点持久化。

状态机的意义：模型可以自由选择工具，但不能发明状态。所有状态迁移
必须经过 transition()，非法迁移直接抛错，防止 Agent 跳过质检门禁
或绕过候选保存直接发布。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---- 状态机定义 ----
STATE_CREATED = "CREATED"
STATE_SEARCHING = "SEARCHING"
STATE_SELECTING = "SELECTING"
STATE_GENERATING = "GENERATING"
STATE_AUDITING = "AUDITING"
STATE_REPAIRING = "REPAIRING"
# PUBLISHED：候选已保存到正式存储（OSS/本地）且预览已发，等待次日早晨
# 发送链路（main.handler morning_send）读取候选后发送；Agent 不再人工触发发送。
STATE_PUBLISHED = "PUBLISHED"
STATE_SENT = "SENT"
STATE_BLOCKED = "BLOCKED"
STATE_FAILED = "FAILED"

# 主链状态（按序推进）
MAIN_STATES = [
    STATE_CREATED,
    STATE_SEARCHING,
    STATE_SELECTING,
    STATE_GENERATING,
    STATE_AUDITING,
    STATE_REPAIRING,
    STATE_PUBLISHED,
    STATE_SENT,
]

# 终态：进入后不允许再被模型驱动前进
TERMINAL_STATES = frozenset({STATE_PUBLISHED, STATE_SENT, STATE_BLOCKED, STATE_FAILED})

# 允许从任意主链状态进入的异常态
FAILED_FROM = set(MAIN_STATES)
BLOCKED_FROM = set(MAIN_STATES)

# 合法迁移表：state -> 允许的下一状态集合
TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_CREATED: frozenset({STATE_SEARCHING, STATE_FAILED}),
    STATE_SEARCHING: frozenset({STATE_SELECTING, STATE_BLOCKED, STATE_FAILED}),
    STATE_SELECTING: frozenset({STATE_GENERATING, STATE_BLOCKED, STATE_FAILED}),
    STATE_GENERATING: frozenset({STATE_AUDITING, STATE_BLOCKED, STATE_FAILED}),
    STATE_AUDITING: frozenset({STATE_REPAIRING, STATE_PUBLISHED, STATE_BLOCKED, STATE_FAILED}),
    STATE_REPAIRING: frozenset({STATE_AUDITING, STATE_BLOCKED, STATE_FAILED}),
    STATE_PUBLISHED: frozenset({STATE_SENT, STATE_BLOCKED, STATE_FAILED}),
    STATE_SENT: frozenset(),          # 终态
    STATE_BLOCKED: frozenset(),       # 终态
    STATE_FAILED: frozenset(),        # 终态
}


class IllegalTransitionError(RuntimeError):
    pass


def assert_transition(current: str, target: str) -> None:
    if target not in TRANSITIONS.get(current, frozenset()):
        raise IllegalTransitionError(f"Illegal state transition: {current} -> {target}")


# ---- 运行状态 ----
@dataclass
class RunState:
    run_id: str
    delivery_date: str
    state: str = STATE_CREATED
    repair_round: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    selected_article_ids: list[int] = field(default_factory=list)
    candidate_saved: bool = False
    preview_sent: bool = False
    published: bool = False
    sent: bool = False
    confirm_token: str = ""
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "delivery_date": self.delivery_date,
            "state": self.state,
            "repair_round": self.repair_round,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "selected_article_ids": list(self.selected_article_ids),
            "candidate_saved": self.candidate_saved,
            "preview_sent": self.preview_sent,
            "published": self.published,
            "sent": self.sent,
            "confirm_token": self.confirm_token,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RunState":
        return cls(
            run_id=str(raw.get("run_id") or ""),
            delivery_date=str(raw.get("delivery_date") or ""),
            state=str(raw.get("state") or STATE_CREATED),
            repair_round=int(raw.get("repair_round") or 0),
            model_calls=int(raw.get("model_calls") or 0),
            tool_calls=int(raw.get("tool_calls") or 0),
            selected_article_ids=[int(i) for i in (raw.get("selected_article_ids") or [])],
            candidate_saved=bool(raw.get("candidate_saved")),
            preview_sent=bool(raw.get("preview_sent")),
            published=bool(raw.get("published")),
            sent=bool(raw.get("sent")),
            confirm_token=str(raw.get("confirm_token") or ""),
            last_error=str(raw.get("last_error") or ""),
            created_at=str(raw.get("created_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
            history=list(raw.get("history") or []),
        )

    def transition(self, target: str, *, note: str = "") -> None:
        assert_transition(self.state, target)
        self.state = target
        self.updated_at = _now_iso()
        if note:
            self.history.append(
                {"ts": self.updated_at, "event": "transition", "to": target, "note": note}
            )

    def log_event(self, event: str, **payload: Any) -> None:
        self.updated_at = _now_iso()
        entry: dict[str, Any] = {"ts": self.updated_at, "event": event}
        entry.update(payload)
        self.history.append(entry)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def default_run_dir() -> Path:
    from config import settings

    return Path(settings.output_dir) / "agent-runs"


def run_dir(delivery_date: str) -> Path:
    return default_run_dir() / delivery_date


def run_path(delivery_date: str) -> Path:
    return run_dir(delivery_date) / "run.json"


def load_run(delivery_date: str) -> Optional[RunState]:
    path = run_path(delivery_date)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return RunState.from_dict(raw)
    except Exception:
        return None


def save_run(state: RunState) -> dict[str, Any]:
    d = run_dir(state.delivery_date)
    d.mkdir(parents=True, exist_ok=True)
    path = run_path(state.delivery_date)
    path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"run_state_path": str(path), "run_state_saved": True}
