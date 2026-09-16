# 公考晨读 Agent · 部署文档

新增代码全部位于 `agent/` 目录，独立于现有生产流水线（`main.handler` 不动）。
部署为一个**新的阿里云函数计算函数** `fc_agent_orchestrator`，
日常生产入口不变，风险隔离。

## 1. 新增文件

```
agent/
├── __init__.py          # 包说明
├── schemas.py           # 模型结构化输出校验（禁止发明状态/工具）
├── state.py             # 状态机 + 运行断点（run.json）
├── tools.py             # 受控工具层（8 个工具，包装现有模块）
├── orchestrator.py      # 主循环（选文 / 质检放行两个模型决策点）
├── confirm.py           # 预览 + 取消闸门（次日自动发送 + hmac 取消链接）
├── instructions.py      # 读取系统提示词
├── prompts/
│   └── orchestrator.md  # 职责边界与决策格式（Agent instructions）
├── fc_entry.py          # FC 入口 fc_agent_orchestrator.handler
└── run_local.py         # 本地运行入口
tests/test_agent_state.py          # 状态机 / 结构化输出 / token 单测
tests/test_agent_orchestrator.py   # 编排集成测试（确定性 Planner + mock）
```

## 2. 新增环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `AGENT_CONFIRM_SECRET` | 是 | 取消链接签名密钥（高熵随机串，建议 32+ 位） |
| `AGENT_CONFIRM_BASE_URL` | 是 | 函数 HTTP 触发域名，如 `https://xxx.cn-hangzhou.fcapp.run` |
| `AGENT_MORNING_SEND_HINT` | 否 | 预览邮件里提示的发送时间，默认"次日早晨 07:30" |
| `AGENT_MAX_MODEL_CALLS` | 否 | 模型调用次数上限，默认 8 |
| `AGENT_MAX_TOOL_CALLS` | 否 | 工具调用次数上限，默认 20 |
| `AGENT_MAX_REPAIR_ROUNDS` | 否 | 定点修复轮次上限，默认 2 |

其余复用现有环境变量（`DASHSCOPE_API_KEY` / `SMTP_*` / `CANDIDATE_STORAGE` 等）。
`CANDIDATE_STORAGE=oss` 时 `save_candidate` 写入正式 OSS 候选，次日发送链路读取。

## 3. 部署步骤（阿里云 FC）

### 3.1 打包

复用现有打包脚本（生成 `function.zip`）：

```bash
bash scripts/build_fc_package.sh
```

### 3.2 创建函数

- 服务：复用现有服务（或新建 `gongkao-agent`）
- 函数名：`fc_agent_orchestrator`
- 运行时：Python 3.10+
- 入口：`agent.fc_entry.handler`
- 内存：建议 ≥ 1024 MB（生成链路耗时较长）
- 超时：建议 600 秒（FC 最大超时），一次运行通常 2~5 分钟

### 3.3 环境变量

在函数配置中填写第 2 节全部变量（复用生产环境的 `DASHSCOPE_API_KEY`、SMTP、OSS 等）。

### 3.4 触发器

**定时触发器（每晚 20:00）**：
- Cron：`0 20 * * *`（Asia/Shanghai）
- 触发事件：
  ```json
  { "mode": "agent_nightly" }
  ```
  不传 `delivery_date` 时默认生成**次日**晨读（20:00 生成 → 保存候选 + 发预览 →
  次日早晨自动发送）。

**HTTP 触发器（用于取消链接）**：
- 认证：无需认证（链接本身带 hmac token）
- 创建后得到访问域名，填入 `AGENT_CONFIRM_BASE_URL`

## 4. 使用流程

```
20:00  定时触发 fc_agent_orchestrator
   ↓
Agent：搜索文章 → 模型选文 → 生成 brief → 渲染 → 质检
   ↓（P0 门禁失败自动定点修复，最多 2 轮）
通过门禁 → 保存候选（正式存储）→ 发送【预览邮件】到你的邮箱（SMTP_USER）
   ↓
状态 PUBLISHED：等待次日早晨发送链路自动群发
   ↓
你在邮箱里检查预览（可选项）：
   ├─ 没问题 → 什么都不用做，次日早晨 07:30 自动发送
   └─ 有问题 → 点【取消次日发送】→ 候选门禁置 fail → 次日发送链路自动阻断
```

与方式一（FC 夜间流水线）、方式二（ChatGPT 技能）的发送完全一致：
**都是生成候选 → 存正式候选 → 次日早晨 morning_send 自动群发**。

运行状态与断点保存在 `agent-runs/{delivery_date}/run.json`
（`OUTPUT_DIR` 下；若 `CANDIDATE_STORAGE=oss` 建议同步备份该目录）。

## 5. 本地验证

### 5.1 单元 / 集成测试（不联网、不调用模型）

```bash
python -m unittest tests.test_agent_state tests.test_agent_orchestrator
```

### 5.2 本地 dry run（mock 模型，不发送）

```bash
TEST_LLM_MODEL=mock python -m agent.run_local --date 2026-09-16 --test
```

`TEST_LLM_MODEL=mock` 时 Orchestrator 自动使用确定性策略（选前 3 篇、质检放行），
走完整个状态机但不调模型、不发邮件（预览发送在本地 dry run 中会真实执行，
如需跳过可临时注释 `agent/orchestrator.py` 中 `send_preview_email` 调用）。

### 5.3 模拟取消（本地验证安全网）

```bash
TEST_LLM_MODEL=mock python -m agent.run_local --date 2026-09-16 --test --cancel
```

会模拟管理员点击取消链接，验证候选被标记、状态进入 BLOCKED。

## 6. 回滚

删除新函数 `fc_agent_orchestrator` 及其触发器即可，现有 `main.handler`
流水线不受任何影响。Agent 仅写入自己的 `agent-runs/` 目录和正式候选
（`save_candidate` 与夜间链路共用同一候选存储，写入前必须过门禁）。
