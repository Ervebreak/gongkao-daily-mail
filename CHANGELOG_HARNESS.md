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

### 2026-05-22｜周末候选件改为只生成周 PDF 汇编

**改动原因**

用户确认周六晚上只需要生成周 PDF 汇编候选件，周日早晨只发送 PDF 汇编，不应再写新的每日精读文章。同时，发送前清洁度守卫只需要在夜里写入候选件前运行一次，早晨发送时继续信任夜里保存的 `quality_gate`。

**已改文件**

- `main.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- `morning_send` 不再重新运行 `pre_send_cleanliness_guard`，只读取夜里候选件中已经保存的 `quality_gate`。
- 新增 `weekly_pdf_candidate` / `weekly_candidate` / `nightly_weekly_pdf` 候选件模式：只读取每日归档生成周 PDF、保存 `candidate_type=weekly_pdf` 候选件，不进入每日文章抓取、选文和精读写稿流程。
- 如果周六夜里仍触发普通 `nightly_candidate`，且 `ENABLE_WEEKLY_PDF=true`、候选件日期正好是 `WEEKLY_PDF_WEEKDAY`，程序会自动转为周 PDF 候选件生成，避免周日候选件误写成每日精读。
- 周 PDF 候选件保存为第二天发送日期；周日 `morning_send` 读取后走已有 `send_weekly_pdf_candidate`，只发汇编 PDF，不写历史文章、不归档每日精读。
- 周 PDF 候选件邮件正文改为“周日复盘说明邮件”：标题为“本周 PDF 资料包已附上”，正文说明今天不推送新精读/速读、给出复习顺序，并保留反馈问题区；PDF 汇编作为附件发送。

**后续注意事项**

1. 如需在周末强制生成普通每日精读候选件，可在事件里加 `force_daily=true` 或 `skip_weekly_pdf_candidate=true`。
2. 周 PDF 依赖每日归档；如果归档天数不足，候选件生成会记录缺失日期并按已有周 PDF 汇编逻辑处理。

### 2026-05-22｜新增发送前清洁度守卫

**改动原因**

今晚邮件中“可用表达”模块出现了正文开头残留点号/冒号的问题，说明单靠渲染层去重还不够。为避免模板残留、标签泄漏、重复前缀、冒号残留和标题重复进入 `latest.json` 或正式发送正文，需要在发送前增加一层确定性的清洁度守卫。

**已改文件**

- `pre_send_cleanliness.py`
- `main.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- 新增 `pre_send_cleanliness_guard(data)`，内部按 `check_cleanliness -> auto_fix_cleanliness -> 同步渲染 plain_text/html_body -> recheck_cleanliness -> decide_gate_status` 执行。
- 自动修复 `可用表达：可用表达：`、`作答主线：作答主线：`、`审题关键：审题关键：`、`如果点原文，重点看：如果点原文，重点看`、字段正文开头冒号/点号残留，以及重复的 `【公考晨读】` 标题前缀。
- `featured_article.rewritable_expression` 字段会被清成纯表达，不再保留 `可用表达：` 前缀；`plain_text` 和 `html_body` 会随修复后的 brief 同步更新。
- 金句高度相似、30 秒输出偏长、考生版答案段落偏长只记录为低风险 issue，不阻断发送。
- 今日一题题干缺身份、场景、矛盾、任务要素时，清洁度守卫只记录高风险 issue，不硬改题目，并通过 `module_override=daily_question` 交给原有 daily_question 重写/质量门禁处理。
- 清洁度结果写入 `quality.final.cleanliness` 和 `quality.cleanliness`；未修复的明显模板残留会进入原 `quality_gate`。该守卫只在夜里候选件生成/评估阶段运行，早晨 `morning_send` 继续信任夜里保存的 `quality_gate`。

**后续注意事项**

1. 该守卫只做规则型清洁和门禁，不引入新 LLM，也不改变邮件结构。
2. 后续如果新增模块标题，需要同步加入 `pre_send_cleanliness.py` 的 `DISPLAY_LABELS`。

### 2026-05-22｜周 PDF 全面切换打印友好浅色填充

**改动原因**

用户继续反馈，周 PDF 虽然已经把日标题区改浅，但首页封面、金句区编号块、框架图步骤编号等元素仍是大面积深色实心填充，打印后容易变成“黑乎乎一片”，影响可读性和复印体验。

**已改文件**

- `weekly_typst_export.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- 周 PDF 首页封面由深蓝大底改为浅蓝灰底，主标题文字、数字统计卡片改为深色文字 + 浅色卡片，打印时不会出现大面积深色底。
- 框架图内的步骤编号、金句库编号块、其他小编号标签，统一改为“浅色底 + 深色字，带边框”的打印友好样式。
- 主题总览表格、精读原文索引、补充阅读列表的表头，由深色表头改为浅色表头，保留深色文字和结构层级。
- 这次仍只调整周 PDF 模板配色，不改内容提取、模块顺序和文案内容。

**后续注意事项**

1. 如果后续还要继续压浅颜色，需要同步抽查屏幕阅读时的对比度，避免浅到标题层级不够清。
2. 正式上线前建议再用一份完整七天样本复核版式，确认浅色表头和编号块在打印机上仍有足够辨识度。

### 2026-05-22｜周 PDF 改为模块尽量整块分页、浅色日标题与金句大框

**改动原因**

用户反馈周 PDF 存在三个阅读问题：一是文章框架图等模块会在分页处被拆开；二是每日标题区深色底打印不友好；三是“可背金句”逐条分散，视觉上不够整合。

**已改文件**

- `weekly_typst_export.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- Typst 周 PDF 中的精读卡、文章框架图、今日可带走等较小模块改为尽量整块保留；如果当前页放不下，会优先整体移到下一页，减少框架图跨页。
- 每日标题区由深色整块底改为浅蓝灰底 + 深色文字，更适合黑白或低彩打印，同时保留层次感。
- “可背金句”区域改为一个统一大框，框内按编号分条展示，不再以分散小块呈现。
- 这次仍只调整周 PDF 模板，不改每日邮件内容和模块提取逻辑。

**后续注意事项**

1. 对于高度明显超过一页的超长模块，Typst 仍可能被迫分页；当前优化主要解决框架图、提要卡这类中小模块被拆页的问题。
2. 如果后续继续压浅配色，需要同时关注屏幕阅读对比度，避免浅到底色和正文层级不清。

### 2026-05-22｜周 PDF Typst 模板放宽行距、段距与卡片留白

**改动原因**

周 PDF 汇编当前版本在连续大段正文、卡片说明和框架步骤区域排版偏紧，阅读时容易显得“密密麻麻”。本次参考旧版周复盘 PDF 的版式密度，放宽正文行距、段距和卡片内边距，并将字号微调放大，但避免明显增页。

**已改文件**

- `weekly_typst_export.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- Typst 周 PDF 正文字号从 `10pt` 微调到 `10.2pt`。
- 全局段落行距、段间距、列表间距同步放宽，长段正文和题目答案区域更容易扫读。
- 精读卡、文章框架图、今日一题、今日可带走、金句卡片等模块的内边距和标题留白同步增加，整体视觉更接近旧版周复盘 PDF 的呼吸感。
- 这次只调版式密度，不改周 PDF 的内容结构、模块顺序和提取逻辑。

**后续注意事项**

1. 后续如果继续加大字号或留白，需同时关注周 PDF 页数增长，避免周末附件过长。
2. 三天/四天预览与完整七天周报的分页效果不同；正式上线前仍建议用完整一周样本复核分页。

### 2026-05-22｜修复模块标题在正文中重复展示

**改动原因**

部分邮件字段本身带有展示前缀，例如 `可用表达：`、`作答主线：`、`如果点原文，重点看：`。渲染层又额外输出了一次模块标题，导致用户看到“标题 + 正文里再重复一遍同名标题”的双标题展示。

**已改文件**

- `email_renderer.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- HTML 渲染层会在展示 `original_reading_focus`、`breaking_hint`、`rewritable_expression` 时，自动剥离与模块标题完全重复的开头前缀。
- 这次只处理显示重复，不改字段原始内容、不改模块顺序、不改其它正文文案。
- 如果正文不是以这些模块标题开头，渲染层不会额外改写内容。

**后续注意事项**

1. 生成侧仍应尽量避免在这些字段里重复写展示标题，但即使模型偶尔带出前缀，渲染层也会兜底去重。
2. 后续如新增类似“标题 + 正文”模块，若正文字段也可能自带同名前缀，应同步接入同类渲染去重逻辑。

### 2026-05-22｜早晨发送改为信任夜间候选件 quality_gate

**改动原因**

夜间候选件已经完成正式质检并写入 `quality_gate`，但早晨 `morning_send` 之前仍会对同一份候选件再次执行全文质检。这样会出现“夜里候选件已是 ok，早晨却因新规则或重检结果被拦截”的漂移，导致正式发送依赖两次不同时间点的内容判定。

**已改文件**

- `main.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- 早晨发送读取 OSS / 本地保存的候选件后，直接信任候选件内已保存的 `quality_gate`，不再对非周报候选件重跑全文内容质检。
- 早晨发送仍然保留候选件存在性、`delivery_date` 匹配、已保存 `quality_gate.overall` 是否为 `ok`、收件人与发送链路等基础校验。
- 如果夜间保存下来的 `quality_gate.overall != ok`，早晨仍然会阻断发送；只是不会再因为早晨重新跑内容质检而把夜间已通过的候选件重新打回。
- 周报 PDF 候选件链路不受这次改动影响。

**后续注意事项**

1. 后续如果新增或收紧内容质检规则，夜间候选件生成链路才是唯一的正式内容门禁来源，早晨发送链路不再承担“重新判内容是否合格”的职责。
2. 如果需要验证正式发送行为，应优先用“夜间先生成候选件，早晨再读取候选件发送”的完整链路测试，而不是假设早晨发送会再做一次内容重检或自动修正文案。

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
