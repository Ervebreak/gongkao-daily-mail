# Harness Change Log

本文件记录公考晨读邮件项目的重要规则、Prompt、质检、渲染和部署改动。以后 AI Coding / Codex / Cursor / OpenClaw 接手项目前，必须先读本文件，再读 `AGENTS.md` 和 `content_harness/00_index.md`。

## 使用规则

1. 每次修改规则、Prompt、质检、渲染、发送链路、归档链路或部署配置后，都要在本文件新增一条记录。
2. 记录要写清楚：改动日期、改动范围、涉及文件、为什么改、最新版行为是什么、后续要注意什么。
3. 本文件只记录“项目行为变化”和“容易影响后续判断的决策”，不记录普通错别字和无行为影响的小排版。
4. 新增记录放在“最新改动”下面，保持倒序。
5. 如果某次改动同时影响 Prompt 和质检，必须同时说明生成侧和拦截侧分别改了什么。

## 当前最新版状态

### 今日一题模块边界

当前约定：

- 审题关键：看清题。只拆题，说明题目真正问什么、涉及哪些对象、核心矛盾是什么、哪些作答方向不能漏。不得写完整对策路线。
- 作答主线：打开题。底层字段仍使用 `breaking_hint`，展示语义是“作答主线”。只给一句总路线，例如“先释疑稳预期，再溯源查问题，最后建机制管长远”。不得列完整分点。
- 作答框架：写成题。使用 `answer_framework` / `answer_frame`，只写 3-4 条正式分点骨架，每点不超过 35 字，格式为“动词短语：简短解释。”。
- 考生版参考答案：完整展开，负责把作答框架转成自然、稳重、可复述的考场表达。

一句话规则：

> 审题关键看清题，作答主线打开题，作答框架写成题。

## 最新改动

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
