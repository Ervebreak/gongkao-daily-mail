# 公考晨读 Agent · 架构说明

## 1. 定位

本项目已有完整的"抓取 → 生成 → 质检 → 渲染 → 发布 → 发送"生产链路
（`main.handler` / `run_daily_brief`）。Agent 层**不重写任何业务算法**，
只做三件事：

1. 把现有成熟能力包装成**受控工具**（输入输出明确的函数接口）
2. 用 **Orchestrator** 在关键决策点调用模型（选文、质检放行）
3. 加一道**人工确认闸门**（Human-in-the-loop），确认前绝不发布/发送

```text
定时触发 20:00
   ↓
fc_agent_orchestrator.handler
   ↓
Agent Orchestrator（agent/orchestrator.py）
   ├── 模型决策①：选文（select_articles）
   ├── 工具链：generate_brief → render_candidate → audit_candidate
   ├── 模型决策②：PASS / REPAIR / BLOCKED（修复最多 2 轮）
   └── save_candidate → 发预览给自己 → WAITING_FOR_APPROVAL
                                          ↓ 人工确认
                                     现有发送链路（send_saved_candidate）
                                          ↓
                                       订阅用户邮件
```

三种入口共用同一套 Candidate Schema / 质检门禁 / Renderer / Publisher /
Sender，不会出现多套质量标准漂移。

## 2. 受控工具（agent/tools.py）

| 工具 | 包装的现有模块 | 说明 |
|---|---|---|
| `search_articles` | `fetch_articles.get_candidate_articles_with_stats` | 抓取候选文章池 |
| `select_articles` | （校验 + 工作区落盘） | 校验模型选中的文章 id |
| `generate_brief` | `llm_client.generate_brief` + `brief_schema.ensure_brief_schema` | 生成晨读材料 |
| `render_candidate` | `email_renderer` | 渲染 subject/plain/html |
| `audit_candidate` | `quality_gate.evaluate_all_quality` + `build_gate_from_quality_map` | 全量质检 + 门禁 |
| `repair_candidate` | `llm_client.rewrite_failed_modules_once` | 定点修复失败模块 |
| `save_candidate` | `candidate_store.build_candidate_payload` + `save_candidate` | 保存正式候选 |
| `get_run_status` | `agent.state` | 只读查询运行状态 |

**发布 / 发送不注册为模型工具**——只能由人工确认触发（`agent/confirm.py`），
这是 Agent 无法绕过的安全边界。

## 3. 状态机（agent/state.py）

```text
CREATED → SEARCHING → SELECTING → GENERATING → AUDITING → REPAIRING
                                                              ↓
                                              WAITING_FOR_APPROVAL
                                                      ↓ 人工确认
                                              PUBLISHED → SENT
```

异常态：`BLOCKED` / `FAILED`（终态）。所有迁移必须经过 `transition()` 校验，
模型不能发明状态；`TERMINAL_STATES` 内不允许再次运行（幂等）。

## 4. 模型决策（结构化输出）

模型每轮只输出一个 JSON，由 `agent/schemas.py` 解析与容错：

```json
{
  "decision": "CONTINUE | PASS | REPAIR | BLOCKED",
  "next_tool": "要调用的工具名",
  "arguments": { "工具参数" },
  "reason": "决策理由",
  "issues": [ { "module": "模块 key", "severity": "P0|P1|P2", "reason": "问题" } ]
}
```

- 非法决策（如 `SEND_NOW_WITHOUT_APPROVAL`）一律回退为 `BLOCKED`
- 门禁 `overall != ok` 时模型无权 PASS，只能修复或阻断

## 5. 安全控制

- 工具 / 模型调用次数预算（`AGENT_MAX_*`），防止循环烧钱
- 修复最多两轮（`AGENT_MAX_REPAIR_ROUNDS`）
- 确认链接 hmac 签名，仅当天有效；approve / reject 分离 token
- 同一日期已终态（SENT/BLOCKED/FAILED）不重复运行
- 模型不能直接触碰 OSS、订阅隐私、SMTP、发送历史（见 instructions）

## 6. 断点与可观测

- 每次运行写入 `agent-runs/{delivery_date}/run.json`
  （state / repair_round / model_calls / tool_calls / history 事件轨迹）
- 中间产物（articles / brief / rendered / quality / candidate）落盘同目录，
  支持断点续跑与事后审计

## 7. 测试策略

- 单元测试：结构化输出容错、状态机非法迁移、token 校验
- 编排集成测试：确定性 Planner + mock 外部依赖，覆盖
  全链路到 WAITING_FOR_APPROVAL、终态幂等、P0 阻断、确认/拒绝流
- 质检内部逻辑复用项目既有 40+ 测试，不重复造轮子
