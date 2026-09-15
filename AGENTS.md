# AGENTS.md

本文件是 Codex、OpenClaw、Cursor 等 AI Coding 工具接手本项目时的入口说明。接手项目前必须先读根目录 `CHANGELOG_HARNESS.md`，确认当前最新版行为和最近改动，再读本文件，并按修改类型读取 `content_harness/00_index.md` 指向的必读文档。

## 0. 必读顺序

1. `CHANGELOG_HARNESS.md`：先确认最近改了什么、当前最新版行为是什么、还有哪些待补项。
2. `AGENTS.md`：再确认项目运行边界、禁止行为、核心文件地图和验证要求。
3. `content_harness/00_index.md`：最后按具体修改类型读取对应规则、Skill、质检和工作流文档。

任何规则、Prompt、质检、渲染、发送链路、归档链路或部署配置的行为变化，都必须同步追加到 `CHANGELOG_HARNESS.md`。

## 1. 项目目标

公考晨读邮件程序每天把官方文章转化为公考/考编可用的申论、面试、公基备考材料，并通过邮件发送给用户。

当前核心机制是“两段式交付”：

- 晚上 22:00 生成第二天候选件，执行质检、重写、P0 门禁、P0 自动二次修复、候选保存、管理员质检报告。
- 早上 08:00 只读取当天候选件，候选件通过门禁后才给用户发送。

阿里云 FC 入口：`main.handler`。本地入口：`python main.py`。

### Agent 编排层（人工确认后发送）

`agent/` 目录提供独立的 AI Agent 编排入口（`fc_agent_orchestrator.handler`），
把现有能力包装成受控工具，由 Orchestrator 动态编排（模型只在选文和质检放行
两个决策点调用），候选通过门禁后**先发预览给管理员，确认后才发送**。
不重写业务算法，与 `main.handler` 共用同一套 Schema / 质检 / 渲染 / 发送链路。
详见 `docs/agent_architecture.md`、`docs/agent_deploy.md`。
修改 Agent 编排 / 工具 / 确认闸门时，必读：`agent/orchestrator.py`、
`agent/tools.py`、`agent/confirm.py`、`agent/prompts/orchestrator.md`。

## 2. 修改类型与必读文件

| 修改类型 | 必读文件 |
| --- | --- |
| 产品定位、模块增删 | `CHANGELOG_HARNESS.md`, `content_harness/product_spec.md`, `content_harness/content_rules.md` |
| 今日一题 | `CHANGELOG_HARNESS.md`, `content_harness/daily_question_skill.md`, `content_harness/quality_checks.md` |
| 框架图 | `CHANGELOG_HARNESS.md`, `content_harness/framework_map_skill.md`, `content_harness/quality_checks.md` |
| 今日可带走、金句表达 | `CHANGELOG_HARNESS.md`, `content_harness/takeaway_expression_skill.md`, `content_harness/quality_checks.md` |
| 速读、重复、考生表达质检 | `CHANGELOG_HARNESS.md`, `content_harness/00_index.md`, `quick_reads_quality.py`, `duplication_quality.py`, `expression_quality.py` |
| Prompt、生成规则 | `CHANGELOG_HARNESS.md`, `content_harness/runtime_prompt_rules.md`, `content_harness/article_selection_prompt.md`, `prompt_templates.py` |
| 质检、门禁、自动修复 | `CHANGELOG_HARNESS.md`, `content_harness/quality_checks.md`, `scripts/validate_daily_brief.py`, `brief_quality.py` |
| 展示重复、标签泄漏、三版本同步 | `CHANGELOG_HARNESS.md`, `content_harness/display_rules.md`, `email_renderer.py`, `duplication_quality.py`, `expression_quality.py` |
| 事实安全、时政常识风险 | `CHANGELOG_HARNESS.md`, `content_harness/fact_safety_rules.md`, `takeaway_quality.py`, `content_quality_reviewer.py` |
| P0 修复闭环 | `CHANGELOG_HARNESS.md`, `content_harness/p0_repair_workflow.md`, `main.py`, `llm_client.py`, `harness_audit.py` |
| 发布部署、FC 依赖 | `CHANGELOG_HARNESS.md`, `content_harness/deployment_rules.md`, `requirements.txt`, `README.md` |
| 晚上候选件 | `CHANGELOG_HARNESS.md`, `content_harness/workflow.md`, `candidate_store.py`, `main.py` |
| 早晨发送链路 | `CHANGELOG_HARNESS.md`, `content_harness/workflow.md`, `main.py`, `email_sender.py`, `history.py` |
| 归档、历史去重、OSS | `CHANGELOG_HARNESS.md`, `content_harness/workflow.md`, `daily_archive.py`, `history.py`, `candidate_store.py` |
| 管理员质检报告 | `CHANGELOG_HARNESS.md`, `admin_report.py`, `harness_audit.py`, `harness_metrics.py` |
| Harness 指标统计 | `CHANGELOG_HARNESS.md`, `harness_metrics.py`, `README.md` 的 Harness 指标统计段落 |
| 知识库样例沉淀 | `CHANGELOG_HARNESS.md`, `knowledge/README.md`, `knowledge/weekly_log.md`, `knowledge/good_examples/`, `knowledge/bad_examples/`, `knowledge/exam_patterns/` |
| 周度质量复盘 | `CHANGELOG_HARNESS.md`, `scripts/weekly_quality_review.py`, `harness_metrics.py`, `knowledge/README.md` |

## 3. 禁止行为

- 禁止绕过 `RUN_MODE`、`SEND_EMAIL`、测试收件人等 test/prod 隔离逻辑。
- 禁止在测试模式下误发正式用户邮件。
- 禁止在正式模式下默认跳过发送、历史、归档等关键链路，除非环境变量明确关闭。
- 禁止绕过 `quality_gate`、P0 门禁或 `scripts/validate_daily_brief.py` 的阻断结果。
- 禁止把 `quality_gate.overall != ok` 的候选件发给用户。
- 禁止删除、弱化、短路现有质量检查规则来让样例通过。
- 禁止无候选件时在早晨链路临时正式生成并发送邮件。
- 禁止夜间候选生成写入正式发送历史。
- 禁止把管理员质检报告发给普通用户订阅列表。
- 禁止把密钥、授权码、真实邮箱凭证写入代码、文档或样例。
- 禁止恢复夜间预览能力，除非用户明确要求重新设计该产品能力。
- 禁止用省略号、半句话、开发态字段污染正式邮件内容。

## 4. 核心文件地图

```text
main.py                         主流程、触发模式、夜间候选、早晨发送
config.py                       环境变量和运行配置
fetch_articles.py               抓取候选文章
article_filter.py               文章筛选和排除
llm_client.py                   大模型调用、生成、模块重写
prompt_templates.py             邮件生成 Prompt
brief_schema.py                 邮件 JSON 结构校验
brief_quality.py                整体质量评估组合
question_quality.py             今日一题质检
framework_quality.py            框架图质检
takeaway_quality.py             今日可带走质检
quick_reads_quality.py          速读考试价值质检
duplication_quality.py          跨模块重复质检
expression_quality.py           考生表达质感质检
scripts/validate_daily_brief.py 统一总门禁
harness_audit.py                失败留档、重写前后对比
harness_metrics.py              Harness 指标统计
scripts/weekly_quality_review.py 周度 Harness 质量复盘
candidate_store.py              候选件保存和读取
admin_report.py                 管理员质检报告
email_renderer.py               HTML/TXT 邮件渲染
email_sender.py                 SMTP 发送
history.py                      已发送历史去重
daily_archive.py                每日归档
CHANGELOG_HARNESS.md            Harness 行为变更记录，后续修改必须先读并追加记录
content_harness/                产品、规则、技能、工作流、评估文档
knowledge/                      正反例、题型转换方法、每周沉淀记录
```

## 5. 触发模式

夜间候选：`{"mode":"nightly_candidate"}`。早晨发送：`{"mode":"morning_send"}`。

夜间候选默认生成第二天邮件；早晨发送默认读取当天候选件。不要引入额外预览事件来替代候选件机制。

## 6. Harness 当前状态

- 已有结构化生成和 schema 校验。
- 已有今日一题、框架图、今日可带走、速读价值、跨模块重复、考生表达质感、整封邮件清洁度质检。
- 已有模块级重写、统一 P0/P1/P2 总门禁、P0 自动二次修复。
- 已有最终 P0 fail 阻断发送、失败留档、重写前后对比。
- 已有管理员质检报告、夜间候选保存、早晨读取发送、Harness 指标 JSONL 统计。
- 已有周度质量复盘脚本，可汇总 P0/P1/P2、模块分布、修复成功率和下周升级清单。

后续优先补“汇总统计、趋势报告、回归样例集”，不要急着给每个步骤堆 Agent。

## 7. 知识库沉淀规则

每周至少新增 2 个 `knowledge/bad_examples` 和 1 个 `knowledge/good_examples`。

新增样例必须写清楚：好/坏在哪里、判断依据、修复或复用方法。题型转换方法沉淀到 `knowledge/exam_patterns/`，每周新增情况记录到 `knowledge/weekly_log.md`。

## 8. 表达类修改规则

凡是修改选文 Prompt、选文评分、featured/quick_reads 选择逻辑，必须先读 `CHANGELOG_HARNESS.md`、`content_harness/article_selection_prompt.md`、`content_harness/workflow.md`。
凡是修改 `candidate_answer`、`rewritable_expression`、`exam_use`、`thirty_second_answer`、`output_sentence_template`、`golden_sentences`、`today_takeaway` 或相关 Prompt，必须先读 `CHANGELOG_HARNESS.md`、`content_harness/runtime_prompt_rules.md` 与 `content_harness/takeaway_expression_skill.md`。

表达类文字的目标不是“更官方”，而是“高水平考生可模仿”。

必须满足：

- 稳重、有层次，但不写成机关公文。
- 自然、顺口、好背，但不写成日常聊天。
- 有观点、有解释、有落点。
- 能进入申论答案、面试回答或复盘笔记。
- 用户看完知道这句话能怎么用。

避免：

- “持续完善、系统推进、形成合力、赋能增效”等套话堆叠。
- “路径纠偏、机制重塑、责任异化、深层治理逻辑”等晦涩词堆叠。
- “大家办事方便点就行”这类过度口语。
- “本题考查……建议考生……”这类教研点评。

改表达类 Prompt 后，必须确认 `expression_quality.py` 仍能覆盖新增字段。

## 9. 必跑验证

改 Python 后至少运行：`python -m py_compile main.py config.py scripts\validate_daily_brief.py`。

涉及 Harness 指标或质检时，加跑：`python -m py_compile harness_metrics.py brief_quality.py question_quality.py framework_quality.py takeaway_quality.py quick_reads_quality.py duplication_quality.py expression_quality.py`。

涉及周度复盘时，加跑：`python -m py_compile scripts\weekly_quality_review.py`。

涉及夜间候选时，用 `RUN_MODE=test`、`TEST_LLM_MODEL=mock`、`SEND_EMAIL=false` 跑 `nightly_candidate`。

涉及早晨发送时，先准备本地候选件，再用 `RUN_MODE=test`、`SEND_EMAIL=false` 跑 `morning_send`。

打包前检查：

- 不能包含 `__pycache__`。
- 不能包含临时坏样例或本地输出目录。
- 不能出现用户已废弃的预览触发字段。
- README、`.env.example`、`content_harness/00_index.md`、`CHANGELOG_HARNESS.md` 必须与新行为一致。

## 10. 输出产物

常用产物：`latest_articles.json`、`latest_brief.json`、`latest_quality.json`、`latest_email.html`、`latest_email.txt`、`latest_run.log`、`latest_candidate_send.log`、`candidates/YYYY-MM-DD.json`、`blocked_runs/YYYY-MM-DD/`、`harness_metrics.jsonl`、`sent_history.json`。

早晨没发出去时，优先查 `latest_candidate_send.log`、候选件 `quality_gate`、`harness_metrics.jsonl` 的 `send_status` 和 `reason`。
