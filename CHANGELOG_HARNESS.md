# Harness Change Log

本文件记录公考晨读邮件项目的重要规则、Prompt、质检、渲染和部署改动。以后 AI Coding / Codex / Cursor / OpenClaw 接手项目前，必须先读本文件，再读 `AGENTS.md` 和 `content_harness/00_index.md`。

## 使用规则

1. 每次修改规则、Prompt、质检、渲染、发送链路、归档链路或部署配置后，都要在本文件新增一条记录。
2. 记录要写清楚：改动日期、改动范围、涉及文件、为什么改、最新版行为是什么、后续要注意什么。
3. 本文件只记录“项目行为变化”和“容易影响后续判断的决策”，不记录普通错别字和无行为影响的小排版。
4. 新增记录放在“最新改动”下面，保持倒序。
5. 如果某次改动同时影响 Prompt 和质检，必须同时说明生成侧和拦截侧分别改了什么。

## 当前最新版状态

### 项目接手阅读顺序

当前约定：

1. 先读 `CHANGELOG_HARNESS.md`，确认最近改了什么、当前最新版行为是什么、还有哪些待补项。
2. 再读 `AGENTS.md`，确认项目运行边界、禁止行为、核心文件地图和验证要求。
3. 最后按修改类型读取 `content_harness/00_index.md` 指向的规则、Skill、质检和工作流文档。

### 今日一题模块边界

当前约定：

- 审题关键：看清题。只拆题，说明题目真正问什么、涉及哪些对象、核心矛盾是什么、哪些作答方向不能漏。不得写完整对策路线。
- 作答主线：打开题。底层字段仍使用 `breaking_hint`，展示语义是“作答主线”。只给一句总路线，例如“先释疑稳预期，再溯源查问题，最后建机制管长远”。不得列完整分点。
- 作答框架：写成题。使用 `answer_framework` / `answer_frame`，只写 3-4 条正式分点骨架，每点不超过 45 字，格式为“动词短语：简短解释。”。
- 考生版参考答案：完整展开，负责把作答框架转成自然、稳重、可复述的考场表达。

一句话规则：

> 审题关键看清题，作答主线打开题，作答框架写成题。

## 最新改动

### 2026-05-21｜统一今日一题作答框架上限为45字

**改动原因**

35字过紧时容易诱发半截句，45字作为安全上限，但仍要求短、准、完整。

**涉及文件**

- `question_quality.py`
- `content_harness/daily_question_skill.md`
- `content_harness/quality_checks.md`
- `content_harness/daily_question_boundary_rules.md`
- `content_harness/runtime_prompt_rules.md`

**最新版行为**

- `answer_framework` / `answer_frame` 每点上限统一为 45 字。
- 45字不是写满要求；优先短、准、完整，不得为了压缩而出现半截句。

### 2026-05-21｜检查今日一题代码层边界改动

**改动原因**

Codex 已完成今日一题三层边界相关代码修改，需要将代码层检查结果同步到变更记录，方便后续接手时区分“已完成”和“待小修”的内容。

**已检查文件**

- `prompt_templates.py`
- `email_renderer.py`
- `question_quality.py`
- `CHANGELOG_HARNESS.md`

**检查结果**

- `prompt_templates.py` 已将 `exam_focus` 改为“只拆题，不写作答路线或具体对策”。
- `prompt_templates.py` 已将 `breaking_hint` 改为“1句话作答主线”，并要求不得列完整分点、不得和作答框架重复。
- `email_renderer.py` 已将 HTML 展示标题从“破题提示”改为“作答主线”，底层字段仍读取 `breaking_hint` / `breaking_direction` / `review_key`。
- `question_quality.py` 已新增 `ANSWER_ROUTE_TERMS`，并加入以下边界质检：
  - `exam_focus_too_answer_like`
  - `breaking_hint_duplicates_framework`
  - `breaking_hint_too_framework_like`

**发现的待小修问题**

- `prompt_templates.py` 中 `answer_framework` 字段说明写成“每条不超过45字”，当前规则、Skill、质检已在后续变更中统一为 45 字，保持生成侧与质检侧一致。
- `question_quality.py` 中缺少作答主线时的提示语仍写“缺少破题提示”，后续建议改成“缺少作答主线”。该问题不影响功能，但会影响管理员报告口径一致性。

**最新版行为**

代码层已经基本完成“审题关键 / 作答主线 / 作答框架”边界改造；但在正式视为闭环前，建议完成上述两个小修，并重新运行：

```powershell
python -m py_compile prompt_templates.py question_quality.py email_renderer.py
```

### 2026-05-21｜沉淀今日一题三层边界到长文档

**改动原因**

专项规则文件已经建立，但长期维护还需要同步进入模块 Skill 和质量检查清单。否则后续只阅读 `daily_question_skill.md` 或 `quality_checks.md` 时，仍可能遗漏“审题关键 / 作答主线 / 作答框架”的边界要求。

**已改文件**

- `content_harness/daily_question_skill.md`
- `content_harness/quality_checks.md`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- `daily_question_skill.md` 已把输出链路改为“题目场景 → 审题关键 → 作答主线 → 作答框架 → 考生表达”。
- `daily_question_skill.md` 已明确 `exam_focus` / `review_key`、`breaking_hint`、`answer_framework` / `answer_frame` 的字段含义和展示关系。
- `daily_question_skill.md` 已新增“三层边界”章节、合格/不合格示例和自检项。
- `quality_checks.md` 已新增 `Check 7.7：审题关键、作答主线、作答框架是否边界清楚`。
- `quality_checks.md` 已把今日一题完整结构从“审题关键 + 作答框架”升级为“审题关键 + 作答主线 + 作答框架”。
- `quality_checks.md` 已列出建议质检 code：`exam_focus_too_answer_like`、`breaking_hint_too_framework_like`、`breaking_hint_duplicates_framework`。

**后续建议补齐**

1. Codex 完成 `prompt_templates.py`、`email_renderer.py`、`question_quality.py` 后，在本文件追加代码层改动记录。
2. 后续如新增今日一题好/坏样例，应优先覆盖“三层边界重复”的回归样例。

### 2026-05-21｜同步 Harness 索引中的阅读顺序和今日一题边界规则

**改动原因**

`CHANGELOG_HARNESS.md` 和 `daily_question_boundary_rules.md` 已经建立，但 `content_harness/00_index.md` 仍未把它们纳入总览顺序和今日一题必读清单。后续 Codex / Cursor 可能只按索引读文件，从而遗漏最新边界规则。

**已改文件**

- `content_harness/00_index.md`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- `content_harness/00_index.md` 的总览顺序已前置 `../CHANGELOG_HARNESS.md` 和 `../AGENTS.md`。
- 今日一题修改类型的必读文件已加入 `daily_question_boundary_rules.md`。
- 今日一题、考生表达质感、质检门禁等相关修改类型均提示先读 `CHANGELOG_HARNESS.md`。
- 今日一题章节新增确认点：审题关键只拆题，`breaking_hint` 底层字段不改但展示语义为作答主线，作答主线不写成第二套框架，作答框架才正式分点。

**后续建议补齐**

1. Codex 完成 `prompt_templates.py`、`email_renderer.py`、`question_quality.py` 后，在本文件追加代码层改动记录。
2. 继续把三层边界规则同步进 `daily_question_skill.md` 和 `quality_checks.md`。

### 2026-05-21｜强制接手前先读变更记录

**改动原因**

用户希望创建一个文件，把每次改动、当前最新版行为和后续注意事项记录下来，并要求以后每次修改前先读这个文件。

**已改文件**

- `AGENTS.md`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- `AGENTS.md` 已把 `CHANGELOG_HARNESS.md` 设为接手项目的第一阅读入口。
- 所有修改类型的必读文件中都加入 `CHANGELOG_HARNESS.md`。
- 后续任何规则、Prompt、质检、渲染、发送链路、归档链路或部署配置的行为变化，都必须同步追加到 `CHANGELOG_HARNESS.md`。

**后续建议补齐**

1. 将 `CHANGELOG_HARNESS.md` 也加入 `content_harness/00_index.md` 的总览顺序。
2. 后续每次提交前检查本文件是否同步更新。

### 2026-05-21｜新增今日一题三层边界专项规则文件

**改动原因**

仅在运行时 Prompt 中写规则还不够，后续改 Prompt、质检、渲染或样例时，需要一个更稳定的专项规则文件，避免“审题关键 / 作答主线 / 作答框架”边界再次模糊。

**已改文件**

- `content_harness/daily_question_boundary_rules.md`
- `CHANGELOG_HARNESS.md`

**最新版行为**

新增专项规则文件，固定以下约定：

- `exam_focus` / `review_key` = 审题关键，只拆题，不展开对策。
- `breaking_hint` = 作答主线，底层字段不改，展示语义改为“作答主线”。
- `answer_framework` / `answer_frame` = 作答框架，负责正式分点。

**后续建议补齐**

1. 将 `content_harness/daily_question_boundary_rules.md` 加入 `AGENTS.md` 和 `content_harness/00_index.md` 的必读清单。
2. 同步修改 `prompt_templates.py`、`question_quality.py`、`email_renderer.py`。

### 2026-05-21｜明确今日一题三层边界

**改动原因**

用户反馈“审题关键”和“破题提示”含义相近；进一步讨论后发现，如果“破题提示”等于答题路线，又可能和“作答框架”重复。需要把三者边界固化到规则和运行 Prompt 中。

**已改文件**

- `content_harness/runtime_prompt_rules.md`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- `breaking_hint` 底层字段保留，避免破坏 JSON schema 和旧代码兼容。
- 运行时语义改为“作答主线”。
- 审题关键不得写成作答路线。
- 作答主线不得写成第二套答题框架。
- 作答框架负责正式分点，并与考生版参考答案分工。

**后续建议补齐**

1. 在 `prompt_templates.py` 的 `JSON_SCHEMA_HINT` 中同步修改 `exam_focus`、`breaking_hint`、`answer_framework` 字段说明。
2. 在 `question_quality.py` 中新增以下质检：
   - `exam_focus_too_answer_like`
   - `breaking_hint_duplicates_framework`
   - `breaking_hint_too_framework_like`
3. 在 `email_renderer.py` 中把展示标题“破题提示”改为“作答主线”。
4. 在 `content_harness/daily_question_skill.md` 和 `content_harness/quality_checks.md` 中补充正式文档说明。

## 历史改动

暂无更早人工整理记录。后续如需追溯更早变更，请查看 Git commit history。
