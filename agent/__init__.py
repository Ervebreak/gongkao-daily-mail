"""公考晨读 Agent：把现有生产能力包装成受控工具，由 Orchestrator 动态编排。

模块：
- schemas.py        模型结构化输出定义与校验
- state.py          状态机 + 运行断点持久化（run.json）
- tools.py          受控工具层（包装现有模块，不重写算法）
- orchestrator.py   主循环（两个模型决策点：选文 / 质检放行）
- confirm.py        人工确认闸门（预览邮件 + hmac 确认链接）
- fc_entry.py       阿里云 FC 入口 fc_agent_orchestrator.handler
- prompts/          Orchestrator 系统提示词
"""
