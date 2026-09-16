"""Agent 结构化输出定义与校验。

模型不自由输出大段文本，而是返回固定 JSON 结构；本模块负责解析、
容错和校验，字段缺失时回退到安全默认值，避免格式漂移破坏状态机。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

# 模型允许输出的决策类型
DECISION_CONTINUE = "CONTINUE"          # 继续调用下一个工具
DECISION_PASS = "PASS"                  # 质检通过，保存候选并发送预览
DECISION_REPAIR = "REPAIR"              # 需要定点修复
DECISION_BLOCKED = "BLOCKED"            # 无法通过，阻断

VALID_DECISIONS = frozenset(
    {DECISION_CONTINUE, DECISION_PASS, DECISION_REPAIR, DECISION_BLOCKED}
)


@dataclass
class Issue:
    """一条质检问题。"""

    module: str = ""
    severity: str = "P2"          # P0 / P1 / P2
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"module": self.module, "severity": self.severity, "reason": self.reason}


@dataclass
class ModelDecision:
    """模型一轮决策的结构化结果。"""

    decision: str = DECISION_CONTINUE
    next_tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "next_tool": self.next_tool,
            "arguments": self.arguments,
            "reason": self.reason,
            "issues": [i.to_dict() for i in self.issues],
        }


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def parse_issue(raw: Any) -> Issue:
    if not isinstance(raw, dict):
        return Issue(reason=_as_text(raw)[:500])
    severity = _as_text(raw.get("severity") or raw.get("level") or "P2").upper()
    if severity not in {"P0", "P1", "P2"}:
        severity = "P2"
    return Issue(
        module=_as_text(raw.get("module") or raw.get("field") or "")[:100],
        severity=severity,
        reason=_as_text(raw.get("reason") or raw.get("message") or raw.get("detail") or "")[:1000],
    )


def parse_decision(raw: Any) -> ModelDecision:
    """把模型返回的任意 JSON 解析成 ModelDecision，缺失字段回退默认值。"""
    raw = _as_dict(raw)
    decision = _as_text(raw.get("decision") or raw.get("action") or raw.get("next_action") or "").upper()
    if decision not in VALID_DECISIONS:
        # 模型输出非法决策时，视为 FAILED 型 BLOCKED，不允许发明状态。
        decision = DECISION_BLOCKED

    next_tool = _as_text(raw.get("next_tool") or raw.get("tool") or raw.get("next_action_tool") or "")
    arguments = _as_dict(raw.get("arguments") or raw.get("args") or raw.get("params") or {})
    reason = _as_text(raw.get("reason") or raw.get("rationale") or "")[:2000]

    issues: list[Issue] = []
    for item in _as_list(raw.get("issues") or raw.get("repair_targets")):
        issues.append(parse_issue(item))

    return ModelDecision(
        decision=decision,
        next_tool=next_tool,
        arguments=arguments,
        reason=reason,
        issues=issues,
    )


def dump_decision(decision: ModelDecision) -> str:
    """供日志 / prompt 展示用。"""
    return json.dumps(decision.to_dict(), ensure_ascii=False, indent=2)
