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

正式环境还必须满足：`RUN_MODE=prod`、`SEND_EMAIL=true`、`SMTP_USER` 可用。
管理员预览没有成功送达时，Agent 返回 `BLOCKED`，不会写入正式候选；只有预览
成功后才把通过门禁的候选写入本地/OSS 正式存储。

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

初次部署时**不要先创建定时触发器**。先完成第 5 节的本地 dry run 和第 6 节的
隔离 OSS 演练，确认后再启用定时器。

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
通过门禁 → 构建候选 → 发送【预览邮件】到你的邮箱（SMTP_USER）→ 保存正式候选
   ↓
状态 PUBLISHED：等待次日早晨发送链路自动群发
   ↓
你在邮箱里检查预览（可选项）：
   ├─ 没问题 → 什么都不用做，次日早晨 07:30 自动发送
   └─ 有问题 → 点【取消次日发送】→ 候选门禁置 fail → 次日发送链路自动阻断
```

与方式一（FC 夜间流水线）、方式二（ChatGPT 技能）的发送完全一致：
**都是生成候选 → 存正式候选 → 次日早晨 morning_send 自动群发**。

三种方式可以共用标准，但不能在同一投递日期同时写同一个
`CANDIDATE_PREFIX`。Agent 进入正式候选前，必须暂停原 FC 的
`nightly_candidate` 触发器；原 `morning_send` 触发器保留。ChatGPT Skill
当日如已发布候选，也不要再触发 Agent。

运行状态与中间产物保存在 `agent-runs/{delivery_date}/`（`OUTPUT_DIR` 下），
用于单次执行审计。FC 本地目录不是跨实例持久存储；取消链接直接以 OSS 候选
为权威状态，不依赖另一个实例能否读取该 `run.json`。

## 5. 本地验证

### 5.1 单元 / 集成测试（不联网、不调用模型）

```bash
python -m unittest tests.test_agent_state tests.test_agent_orchestrator
```

### 5.2 本地 dry run（mock 模型，不发送）

```bash
RUN_MODE=test \
TEST_LLM_MODEL=mock \
SEND_EMAIL=false \
CANDIDATE_STORAGE=local \
OUTPUT_DIR=/tmp/gongkao-agent-smoke \
python -m agent.run_local --date 2026-10-26 --test
```

`TEST_LLM_MODEL=mock` 时 Orchestrator 自动使用确定性策略（选前 3 篇、质检放行），
走完整个“抓取 → 选文 → 生成 → 渲染 → 质检 → 候选构建”链路，但不调模型、
不写 `candidates/` 或 OSS 正式候选、不发邮件。成功终态为 `VALIDATED`，返回
`status=dry_run_complete`。禁止通过注释代码跳过安全逻辑。

### 5.3 隔离 OSS 演练（不接晨间群发）

1. 新建独立 Agent FC，但先不加定时触发器。
2. 设置独立前缀，例如
   `CANDIDATE_PREFIX=gongkao-morning-mailer/agent-staging/candidates`。
3. 其余 OSS、模型和 SMTP 配置复用生产值，手动触发一次
   `{"mode":"agent_nightly","delivery_date":"YYYY-MM-DD"}`。
4. 预期：管理员收到预览，状态为 `PUBLISHED`，候选只写 staging 前缀；
   生产 `morning_send` 不会读取该前缀。
5. 点击取消链接后会先看到确认页；再次点击“确认取消”，确认 staging 候选
   `quality_gate.overall=fail`。GET 请求不会直接改候选，避免邮件安全扫描器误取消。

取消闸门的离线回归由 `tests.test_agent_orchestrator.TestConfirmFlow` 覆盖。

### 5.4 正式切换

1. 暂停原 FC 的 `nightly_candidate` 定时触发器，保留 `morning_send`。
2. 把 Agent 的 `CANDIDATE_PREFIX` 切回生产候选前缀。
3. 手动生成一个次日候选，确认预览、OSS 候选和取消闸门。
4. 确认无误后再启用 Agent 每晚定时触发器。
5. 首周每天检查 Agent 返回状态、管理员预览与早晨发送日志。

## 6. 回滚

删除新函数 `fc_agent_orchestrator` 及其触发器即可，现有 `main.handler`
流水线不受任何影响。Agent 仅写入自己的 `agent-runs/` 目录和正式候选
（`save_candidate` 与夜间链路共用同一候选存储，写入前必须过门禁）。
