# Content Harness Index

本文件串联 `content_harness/` 下的产品、规则、技能、工作流和评估文档。AI Coding 工具修改项目前，应先读根目录 `CHANGELOG_HARNESS.md`，再读根目录 `AGENTS.md`，最后按本索引读取对应文档。

## 1. 总览顺序

建议阅读顺序：

1. `../CHANGELOG_HARNESS.md`：确认最近改了什么、当前最新版行为是什么、还有哪些待补项。
2. `../AGENTS.md`：确认项目运行边界、禁止行为、核心文件地图和验证要求。
3. `product_spec.md`：产品定位、用户价值、模块边界。
4. `content_rules.md`：所有正式内容必须遵守的红线。
5. `workflow.md`：文章抓取、生成、质检、候选、发送、归档的完整链路。
6. `quality_checks.md`：质检层级、阻断标准、修复原则。
7. `runtime_prompt_rules.md`：运行时注入模型的短规则。
8. `display_rules.md`、`fact_safety_rules.md`、`deployment_rules.md`、`p0_repair_workflow.md`：展示边界、事实安全、部署和 P0 修复闭环。
9. 各模块 Skill：今日一题、框架图、今日可带走。
10. `knowledge/README.md`：项目正反例和题型转换方法索引。

## 2. 文档职责

| 文件 | 作用 |
| --- | --- |
| `../CHANGELOG_HARNESS.md` | 定义当前最新版行为、最近改动、后续待补项；所有修改前必须先读 |
| `../AGENTS.md` | 定义 AI Coding 工具接手项目时的入口、禁止行为、核心文件地图和验证要求 |
| `product_spec.md` | 定义项目是什么、服务谁、为什么不是普通新闻摘要 |
| `content_rules.md` | 定义长期内容红线和表达规则 |
| `workflow.md` | 定义从抓取到发送、归档、复盘的系统工作流 |
| `quality_checks.md` | 定义什么要检查、如何判定、失败后怎么处理 |
| `runtime_prompt_rules.md` | 定义运行时 Prompt 的精简规则 |
| `display_rules.md` | 定义邮件展示、模块边界、标签泄漏和三版本同步规则 |
| `fact_safety_rules.md` | 定义时政常识、部门/文件/政策事实的安全边界 |
| `deployment_rules.md` | 定义发布 zip 和阿里云 FC 部署前依赖自检 |
| `p0_repair_workflow.md` | 定义 P0 聚合、模块修复、兜底和 blocked case 沉淀流程 |
| `article_selection_prompt.md` | 定义选文固定 Prompt：考题转化度、问题意识、场景具体度、矛盾张力、降权规则和输出字段 |
| `question_bank_skill.md` | 定义申论真题题库轻接入、隐藏参考、fail-open 和材料依赖边界 |
| `daily_question_skill.md` | 定义“今日一题”的目标、结构、合格标准 |
| `daily_question_boundary_rules.md` | 定义“审题关键 / 作答主线 / 作答框架”的三层边界 |
| `framework_map_skill.md` | 定义“文章框架图”的目标、结构、合格标准 |
| `takeaway_expression_skill.md` | 定义“今日可带走/表达沉淀”的目标、结构、合格标准 |
| `../knowledge/README.md` | 定义正反例、题型方法和每周样例沉淀规则 |

## 3. 按修改类型读取

### 产品定位、模块取舍

必读：

- `../CHANGELOG_HARNESS.md`
- `product_spec.md`
- `content_rules.md`
- `workflow.md`

适用场景：

- 新增或删除邮件模块。
- 调整邮件面向的人群。
- 改变“公考/考编可用”的内容定位。

### 选文 Prompt

必读：

- `../CHANGELOG_HARNESS.md`
- `article_selection_prompt.md`
- `workflow.md`
- `content_rules.md`
- `../knowledge/exam_patterns/article_to_question.md`

相关代码：

- `prompt_templates.py`
- `llm_client.py`
- `fetch_articles.py`
- `history.py`

必须确认：

- 固定规则只放长期选文标准，不放每日候选文章。
- 动态上下文由程序注入最近7天精读、近3天来源/主题、今日候选池。
- 当前阶段使用“考题转化度”，不得写成“真题相似度”。

### 今日一题

必读：

- `../CHANGELOG_HARNESS.md`
- `daily_question_boundary_rules.md`
- `daily_question_skill.md`
- `question_bank_skill.md`
- `quality_checks.md`
- `content_rules.md`
- `../knowledge/good_examples/daily_question.md`
- `../knowledge/bad_examples/daily_question.md`
- `../knowledge/exam_patterns/article_to_question.md`

相关代码：

- `prompt_templates.py`
- `question_quality.py`
- `question_bank.py`
- `scripts/validate_daily_brief.py`

必须确认：

- 审题关键只拆题，不写作答路线。
- `breaking_hint` 底层字段不改，但展示语义是“作答主线”。
- 作答主线只给一句总路线，不写成第二套框架。
- 作答框架才正式分点，每条不超过 45 字。

### 文章框架图

必读：

- `../CHANGELOG_HARNESS.md`
- `framework_map_skill.md`
- `quality_checks.md`
- `content_rules.md`
- `display_rules.md`
- `../knowledge/good_examples/framework_map.md`
- `../knowledge/bad_examples/framework_map.md`

相关代码：

- `prompt_templates.py`
- `framework_quality.py`
- `scripts/validate_daily_brief.py`

### 今日可带走、金句、表达沉淀

必读：

- `../CHANGELOG_HARNESS.md`
- `takeaway_expression_skill.md`
- `quality_checks.md`
- `content_rules.md`
- `fact_safety_rules.md`
- `../knowledge/good_examples/today_takeaway.md`
- `../knowledge/bad_examples/today_takeaway.md`

相关代码：

- `prompt_templates.py`
- `takeaway_quality.py`
- `scripts/validate_daily_brief.py`

### 速读考试价值

必读：

- `../CHANGELOG_HARNESS.md`
- `product_spec.md`
- `content_rules.md`
- `quality_checks.md`
- `display_rules.md`
- `../knowledge/bad_examples/quick_reads.md`

相关代码：

- `quick_reads_quality.py`
- `scripts/validate_daily_brief.py`

必须确认：

- 速读不是普通新闻摘要。
- 每篇速读应说明考点、案例、表达或题型价值。

### 跨模块重复

必读：

- `../CHANGELOG_HARNESS.md`
- `content_rules.md`
- `quality_checks.md`

相关代码：

- `duplication_quality.py`
- `module_redundancy_quality.py`
- `scripts/validate_daily_brief.py`

必须确认：

- 今日一题、精读、金句、速读之间不能大段重复。
- 重复观点要压缩或换成不同角度。

### 考生表达质感

必读：

- `../CHANGELOG_HARNESS.md`
- `content_rules.md`
- `takeaway_expression_skill.md`
- `daily_question_boundary_rules.md`
- `daily_question_skill.md`
- `display_rules.md`
- `../knowledge/good_examples/today_takeaway.md`
- `../knowledge/bad_examples/today_takeaway.md`

相关代码：

- `expression_quality.py`
- `question_quality.py`
- `takeaway_quality.py`
- `scripts/validate_daily_brief.py`

必须确认：

- 答案、可用表达、30秒输出、金句等字段，要像有水平的普通考生能写出来、说出来的话。
- 不能写成政策报告、机关材料、教研点评或训练指令。

### 整封邮件清洁度

必读：

- `../CHANGELOG_HARNESS.md`
- `content_rules.md`
- `quality_checks.md`
- `runtime_prompt_rules.md`
- `display_rules.md`

相关代码：

- `brief_quality.py`
- `brief_schema.py`
- `email_renderer.py`
- `scripts/validate_daily_brief.py`

### 发送链路

必读：

- `../CHANGELOG_HARNESS.md`
- `workflow.md`
- `quality_checks.md`
- `p0_repair_workflow.md`

相关代码：

- `main.py`
- `email_sender.py`
- `history.py`
- `daily_archive.py`

必须确认：

- test/prod 隔离没有被破坏。
- 早晨发送不会绕过候选件和门禁。
- 正式发送成功后才写历史和归档。

### 夜间候选件

必读：

- `../CHANGELOG_HARNESS.md`
- `workflow.md`
- `quality_checks.md`
- `p0_repair_workflow.md`

相关代码：

- `main.py`
- `candidate_store.py`
- `admin_report.py`
- `harness_audit.py`
- `harness_metrics.py`

必须确认：

- 夜间只保存候选件和报告，不给用户发正式邮件。
- 夜间不写正式发送历史。
- P0 fail 时必须失败留档。

### 归档、历史、OSS

必读：

- `../CHANGELOG_HARNESS.md`
- `workflow.md`

相关代码：

- `history.py`
- `daily_archive.py`
- `candidate_store.py`
- `config.py`

必须确认：

- FC 跨实例场景优先用 OSS。
- 不能让本地临时目录成为生产唯一可靠状态。
- 候选件、历史、归档的日期口径一致。

### 质检、门禁、自动修复

必读：

- `../CHANGELOG_HARNESS.md`
- `quality_checks.md`
- `content_rules.md`
- `runtime_prompt_rules.md`
- `daily_question_boundary_rules.md`
- `p0_repair_workflow.md`
- `../knowledge/README.md`
- `../knowledge/quality_issues.jsonl`

相关代码：

- `brief_quality.py`
- `question_quality.py`
- `framework_quality.py`
- `takeaway_quality.py`
- `quick_reads_quality.py`
- `duplication_quality.py`
- `expression_quality.py`
- `scripts/validate_daily_brief.py`
- `llm_client.py`
- `harness_audit.py`

必须确认：

- 新增检查规则要能进入总门禁。
- 新增阻断原因要能进入失败留档和指标统计。
- 自动修复必须保留修复前后对比。

### 知识库样例沉淀

必读：

- `../CHANGELOG_HARNESS.md`
- `../knowledge/README.md`
- `../knowledge/weekly_log.md`
- `../knowledge/good_examples/`
- `../knowledge/bad_examples/`
- `../knowledge/exam_patterns/`

必须确认：

- 每周至少新增 2 个 bad example 和 1 个 good example。
- 反例必须说明坏在哪里、为什么坏、怎么修。
- 好例必须说明好在哪里、适用边界和可复用规则。
- 题型转换方法进入 `exam_patterns/`，不要只散落在日志中。

## 4. Eval 与指标

当前评估入口：

- `quality_checks.md`：规则层评估标准。
- `scripts/validate_daily_brief.py`：可执行总门禁。
- `harness_metrics.py`：运行指标流水。
- `harness_audit.py`：失败留档和重写前后对比。
- `scripts/weekly_quality_review.py`：周度 Harness 质量复盘。

后续建议：

- 建立固定回归样例集。
- 汇总 `harness_metrics.jsonl`，输出日/周趋势。
- 统计 P0/P1/P2、模块失败率、自动修复成功率、早晨阻断原因。

### 周度质量复盘

必读：

- `../CHANGELOG_HARNESS.md`
- `scripts/weekly_quality_review.py`
- `harness_metrics.py`
- `../knowledge/README.md`
- `../knowledge/weekly_log.md`

复盘必须覆盖：

- 本周 P0/P1/P2 数量和模块分布。
- 一次重写与 P0 二次修复成功率。
- 管理员报告发送成功率和早晨发送成功率。
- 重复问题是否已转为规则、脚本或样例。
- 下一周 Harness 升级清单。

## Stage 3 规则治理入口

新增规则治理入口文件：

- `rule_registry.md`
- `field_impact_map.json`

修改以下高风险字段前，先查这两个文件：

- `daily_question.answer_framework`
- `daily_question.thirty_second_answer`
- `policy_coordinate`
- `golden_sentences`
- `rewritable_expression`
- `lite_paid_cta`
- `lite_paid_highlight`
- `speed_reads`
- `weekly_pdf_url / oss_pdf_path`
- `subscription.end_date / reminder_sent / plan`
- `referral_code / referred_by`

需要核对运行时 Prompt 规则漂移时，先运行：

- `python scripts/audit_prompt_rules.py --json`


## 0. 唯一有效生产标准（2026-08 定版）

在本索引所列文档之前，必须先读 [公考晨读生产标准](gongkao_morning_reading_production_standard.md)。它定义选文、生成、质检、定点重写和成品发布的唯一有效口径；与任何历史文档冲突时，以该标准为准。本索引和各模块文档继续承担实现路径与字段细节，不得另立相冲突的产品口径。


## 5. 每日晨读生成技能

仓库内的可复用技能入口：`../skills/gongkao-morning-reading-generation/SKILL.md`。它独立生成待审核的每日晨读候选件，不负责发送，也不替代独立的“公考晨读邮件审核”技能。使用前先读统一生产标准；需要字段契约或具体生成判断时，按入口指向读取技能内参考文件。
