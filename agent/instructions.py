"""Agent 指令与职责边界（Instructions）。

供 Orchestrator 作为 system prompt 注入模型。正文唯一来源是
agent/prompts/orchestrator.md，此处只负责读取并动态注入工具清单。
"""
from __future__ import annotations

from pathlib import Path


def _prompt_body() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "orchestrator.md"
    if not path.exists():
        raise RuntimeError(f"orchestrator prompt missing: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_system_prompt(tool_descriptions: str) -> str:
    """组装 system prompt：提示词正文 + 动态工具清单。"""
    return f"""{_prompt_body()}

## 可用工具

{tool_descriptions}
"""
