# Harness Change Log

## 2026-06-11 - Add policy coordinate diagnostics only

Reason:

- Policy coordinate matching already computes candidate rankings and hide/display reasons, but the run log does not expose enough context to diagnose why a module was shown or suppressed.
- This round is intentionally observability-only: it should help inspect query inputs, top candidates, backend status, semantic-fit status, and disabled reasons without changing match scores, thresholds, or render behavior.

Files:

- `main.py`
- `policy_coordinate_matcher.py`
- `tests/test_policy_coordinate_diagnostics.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added a structured `policy coordinate diagnostics` log event during policy-coordinate build.
- Logs now include compact input previews, topic anchors, matcher top candidates, selected evidence ids, scores, backend status, semantic-fit status, and disabled reason.
- Expanded matcher debug output so `framework_top` also exposes up to 5 items for diagnostics.
- Existing matching results, thresholds, display logic, and final rendering behavior remain unchanged.

## 2026-06-11 - Policy coordinate stage 2 profile input

Reason:

- The current `policy_coordinate` matcher mainly consumes brief summary fields and can miss policy semantics that only appear in the full article body.
- This stage adds full-text-aware `policy_profile` extraction and logging, but keeps the existing policy-coordinate scoring thresholds and display decisions unchanged.

Files changed:

- `policy_profile_builder.py`
- `main.py`
- `tests/test_policy_profile_builder.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- Added `policy_profile_builder.py` to build `core_problem`, `governance_logic`, `value_orientation`, `negative_behaviors`, `positive_behaviors`, `fine_anchors`, and `retrieval_queries` from article title, source, and full text with brief fallback.
- `build_policy_coordinate(...)` now accepts `source_articles`, prefers full article text from the original crawl payload, and falls back to `featured_article` text-like fields or brief-composed text when full text is unavailable.
- Policy-coordinate matching now receives the new policy-profile summaries, anchors, and retrieval queries as extra input, but the existing matching thresholds and display/hide logic are unchanged.
- Runtime logs now include a `policy coordinate profile` event with `article_title`, `article_source`, `article_text_source`, `article_text_length`, truncated text preview, full `policy_profile`, and generated `retrieval_queries`.

Follow-ups:

1. This stage only improves input quality and observability; it does not yet make `policy_profile` a hard decision layer for final display.
2. If full-text input later introduces noisy recall, tune query composition and keyword deduplication before changing backend display thresholds.

## 2026-06-02 - Add reading guide review checks

Reason:

- The first-stage reading guide module is already generated and rendered in the email body.
- The system now needs a lightweight review layer that can flag empty, generic, catalog-style, or hype-heavy guides for later prompt tuning without changing delivery behavior.

Files:

- `reading_guide_quality.py`
- `main.py`
- `tests/test_reading_guide_quality.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added `reading_guide_quality.py` with `evaluate_reading_guide_quality(brief)`.
- Checks now cover missing guide payloads, empty fields, invalid anchor modules, generic wording, module-catalog intros, hype language, overlong fields, and excessive repetition with the email subject.
- `reading_guide` quality is now aggregated into the final quality map for review and logging consistency.
- `build_quality_gate(...)` includes `reading_guide` in the module map, but no reading-guide issue code is promoted into `p0_codes`.
- This round adds monitoring only; it does not block sending or change send logic.

Follow-up:

- `reading_guide` quality is review-only and should be improved through prompt and fallback refinement when recurring issues appear.
- If a later round needs stronger enforcement, it should be introduced deliberately instead of silently escalating these review signals.

## 2026-06-02 - Add dynamic reading guide module

Reason:

- The email subject has already been upgraded to an exam-benefit headline to improve open rate.
- After open, the first screen still needs a lightweight, content-specific guide that tells the reader what is most worth learning today, where to focus, and what they can carry into exam answers.

Files:

- `prompt_templates.py`
- `content_harness/runtime_prompt_rules.md`
- `brief_schema.py`
- `email_renderer.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added `reading_guide` to the generation schema with `core_value`, `focus_path`, `learning_outcome`, and `anchor_module`.
- Added runtime prompt rules that define `reading_guide` as a dynamic value guide instead of a static module introduction.
- `ensure_brief_schema(...)` now fills `reading_guide` deterministically when the model omits it or leaves fields empty.
- The renderer now shows `📌 今天这封怎么用` below the top theme card and above `今日 3 件事` in both HTML and plain text.
- The module shows only the three reader-facing lines and does not expose `anchor_module`.
- This round adds generation, fallback, and rendering only; it does not add P0 blocking or change send logic.

Follow-up:

- `reading_guide` is a front-of-email guidance layer, not a new quality gate.
- If later rounds want to score or review this module, that should be added separately without changing the current send path.

## 2026-06-02 - Add subject quality review checks

Reason:

- The previous two stages already updated prompt guidance and added deterministic subject fallback normalization.
- The system still needs a lightweight way to record whether `email_subject` meets the exam-benefit title standard, so later open-rate tuning and manual review have structured evidence.

Files:

- `subject_quality.py`
- `main.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added `subject_quality.py` with `evaluate_subject_quality(brief)`.
- Checks now cover duplicate subject prefix, hype words, generic subjects, missing exam-value markers, and overlong subject lines.
- `subject_quality` is aggregated into `quality.final.subject_quality` during normal quality evaluation.
- `build_quality_gate(...)` now includes `subject_quality` in the module map for reporting consistency.
- No `subject_quality` code is added to `p0_codes`; title issues stay as review-only signals and do not block sending.
- Title problems are still expected to be fixed first by `subject_line.py`; remaining issues are recorded for review and later optimization.

Follow-up:

- Subject quality is for monitoring and review, not for delivery blocking.
- The current patch keeps `scripts/validate_daily_brief.py` unchanged to avoid expanding this round into a broader encoding cleanup.

## 2026-06-02 - Add deterministic email subject fallback

Reason:

- The previous stage updated prompt guidance so the model prefers exam-benefit subject lines.
- The generation side can still produce generic, overlong, prefixed, or hype-heavy subjects, so the schema normalization stage now adds a lightweight deterministic fallback.

Files:

- `subject_line.py`
- `brief_schema.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added `subject_line.py` as a dedicated email-subject normalization helper.
- The model can still generate `brief.email_subject` freely, but the program now strips prefixes such as `【公考晨读】`, `公考晨读`, and `Re:`.
- Generic subjects, hype-word subjects, empty subjects, and subjects longer than 26 characters are replaced with a stable exam-benefit fallback built from existing brief fields.
- Fallback generation prefers `daily_question.question_type`, `upper_exam_points`, `article_framework_map.exam_tags`, `featured_article.theme`, and related existing fields.
- `brief.email_subject` continues to stay prefix-free; the sending layer still adds the unified `【公考晨读】` prefix.

Follow-up:

- This is a normalization fallback only; it is not a new `subject_quality.py` module and does not change the sending pipeline.
- Future title tuning should prefer adjusting `subject_line.py` rules and fallback wording instead of moving prefix logic into generation or delivery.

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

### 2026-06-02｜新增考试收益型邮件标题规则

**改动原因**

当前邮件标题偏“文章主题型”，用户在收件箱里看不出今天能学到什么、练什么、带走什么。为提升打开前的价值承诺感，本次把标题规则调整为“考试收益型标题”。

**已改文件**

- `prompt_templates.py`
- `content_harness/runtime_prompt_rules.md`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- `brief.email_subject` 改为“不带【公考晨读】前缀的考试收益型标题”，前缀仍由发送层统一添加。
- 标题必须体现常考感、考试收益和具体收获，不能只写文章主题。
- 运行规则中新增 `Email Subject` 小节，明确标题应优先体现高频考点、常考场景、申论素材、面试常见题、机关实务题、今日带走、答题角度、政策坐标等打开价值。
- 标题必须带具体对象或具体考点，禁止使用“必考、押题、上岸、不看后悔、一定会考”等夸张营销词。
- 本次只改 Prompt 和规则文档，不改发送逻辑。

**后续注意事项**

1. 如果后续需要对标题做自动质检，应另起任务，不要把这次最小 patch 扩展成新的标题模块。
2. 发送层仍负责统一补 `【公考晨读】` 前缀，brief 生成侧不要重复添加。

### 2026-05-31｜新增 policy_coordinate 质检与降级

**改动原因**

“今日政策坐标”已进入 JSON 和邮件渲染，需要在最终质量复检中校验政策原文、来源、转译、文章落点、考场迁移和《求是》权威论述，避免错误政策引用或空泛表达直接展示。

**已改文件**

- `policy_coordinate_quality.py`
- `main.py`
- `admin_report.py`
- `CHANGELOG_HARNESS.md`

**最新版本行为**

- 新增 `evaluate_policy_coordinate_quality(...)`，检查政策原文、政策来源、政策转译、文章落点、考场迁移、匹配 ID、半截句、空泛表达、跨模块重复和渲染误放。
- 最终 `evaluate_all_quality(...)` 已接入 `policy_coordinate` 质检，`quality_payload["final"]` 和质量卡会展示最终剩余问题。
- 渲染前会确保 `brief["policy_coordinate"]` 已生成，修正此前“字段写入晚于渲染”的时序问题。
- 如果《求是》权威论述不合格，会删除权威论述，仅保留政策原文、文章落点、考场迁移。
- 如果政策原文或来源不合格，会尝试重新匹配；仍不合格则隐藏政策坐标模块，并在质量结果中记录降级原因。
- `policy_coordinate` 质检不进入 P0 阻断码，不会因为该模块影响其他模块正常生成或发送。

**后续注意事项**

1. 后续如需把政策坐标问题升级为发送阻断，应单独评估误伤率后再加入 P0 code。
2. 当前 `quality_card` 展示的是修复/降级后的最终剩余问题，不展示已删除的权威论述问题。

### 2026-05-31｜渲染今日政策坐标模块

**改动原因**

在任务 4 已写入 `brief["policy_coordinate"]` 的基础上，把“今日政策坐标”展示到邮件正文，位置放在“今日精读”之后、“今日一题”之前。

**已改文件**

- `email_renderer.py`
- `CHANGELOG_HARNESS.md`

**最新版本行为**

- HTML 和 plain_text 同步渲染 `policy_coordinate`。
- `policy_coordinate` 缺少 `policy_source` 或 `policy_quote` 时，整个模块不展示。
- 权威论述只有在 `authoritative_quote` 和 `authoritative_source` 同时存在时才展示，不会残留空标题。
- 政策原文行只使用政策语库字段：`policy_source` + `policy_quote`。
- 《求是》论述只展示在“权威论述”行，不会写成“政策原文”。
- 本次不修改发送逻辑、不修改 `quality_gate`，也不把“今日政策坐标”标题写入 brief 字段。

**后续注意事项**

1. 后续可基于实际邮件样式微调政策坐标卡片配色和间距。
2. 如要把政策坐标纳入质量门禁，应另起任务单独设计检查项。

### 2026-05-31｜daily JSON 写入 policy_coordinate 字段

**改动原因**

在不改邮件 HTML、发送逻辑和质量门禁的前提下，把政策坐标匹配结果写入每日 brief JSON，为后续渲染“今日政策坐标”模块做数据准备。

**已改文件**

- `main.py`
- `CHANGELOG_HARNESS.md`

**最新版本行为**

- 在最终保存 `latest_brief.json` 和候选 payload 前，为 `brief` 新增 `policy_coordinate` 字段。
- `policy_quote` 只来自政策语库，优先使用 `short_quote`，不合适时使用 `policy_quote`，且控制在 90 字以内。
- `policy_source` 使用政策条目的 `source_title`，`policy_source_type` 使用 `source_type`。
- `authoritative_quote` 只来自《求是》权威论述库，可为空；存在时必须同时生成 `authoritative_source`。
- `authoritative_source` 优先使用 `speech_date + speech_event`，否则回退到《求是》期刊文章标题。
- `article_connection` 和 `exam_transfer` 由最终精选文章、政策解释和考试场景生成，只写入 JSON，不进入正文渲染。
- `brief` 中不写入“今日政策坐标”标题，保持字段只存结构化正文数据。

**后续注意事项**

1. 下一步若接入 HTML renderer，应只读取 `brief["policy_coordinate"]`，不要重新在渲染层做匹配。
2. 渲染前建议先人工检查几天 `latest_brief.json` 中 `policy_coordinate` 的匹配质量。
3. 本阶段没有修改 `quality_gate`，因此政策坐标字段暂不参与拦截。

### 2026-05-31｜政策坐标匹配器预接入

**改动原因**

为后续把“今日政策坐标”接入邮件正文，先新增独立匹配器，从政策原文库和《求是》专题知识库中召回当天文章可用的政策原文、权威论述、相关片段和专题框架。本阶段只返回候选对象，不写入 daily JSON、不修改 HTML、不修改发送逻辑。

**已改文件**

- `policy_coordinate_matcher.py`
- `scripts/check_policy_coordinate_matcher.py`
- `CHANGELOG_HARNESS.md`

**最新版本行为**

- 新增 `match_policy_coordinate_candidates(...)`，输入标题、摘要/正文、主题、关键词和考试场景，输出 `matched_policy_coordinate_candidates`。
- 政策原文优先匹配 `policy_statements_core.jsonl`；核心库无语义命中时，再从扩展库中筛选 `quote_status=clean`、`display_ready=true`、`theme_confidence=high`、`usage_tier` 非 `disabled/background` 的条目。
- 《求是》权威论述优先匹配 `authoritative_quotes_core.jsonl`，候选库只在核心库无结果时兜底。
- `article_chunks.jsonl` 最多召回 3 个片段，`topic_frameworks.jsonl` 最多返回 1 个框架。
- 匹配打分综合主题、二级主题、关键词、考试场景、展示优先级、`usage_tier` 和 `freshness`；`historical_framework` 降权，`disabled` 不使用，`background` 不直接展示。
- 当前不接入生成链路，脚本 `scripts/check_policy_coordinate_matcher.py` 仅用于本地验证。

**后续注意事项**

1. 下一步接入邮件生成前，应先确认 `best_policy` 的展示质量和 `debug_scores` 是否符合人工预期。
2. renderer 接入应单独提交，避免匹配逻辑和 HTML 展示逻辑混在一起。
3. 如果后续切换 OSS 读取，需要先扩展 `knowledge_base_loader.py`，不要直接在匹配器里写 OSS 逻辑。

### 2026-05-31｜知识库 JSONL 加载器预接入

**改动原因**

为后续接入“今日政策坐标”和《求是》专题知识库，先提供独立的 JSONL 读取能力。本阶段只新增加载模块和检查脚本，不把知识库接入 daily JSON、邮件生成、HTML 渲染、发送或质量门禁逻辑。

**已改文件**

- `knowledge_base_loader.py`
- `scripts/check_knowledge_base_loader.py`
- `CHANGELOG_HARNESS.md`

**最新版本行为**

- 新增通用 `load_jsonl(path)`，支持读取 UTF-8/UTF-8 BOM JSONL。
- JSONL 单行解析失败时记录错误并跳过坏行，不中断主流程。
- 文件不存在时记录 warning 并返回空列表。
- 同一次运行内按绝对路径缓存读取结果，避免重复读取大文件。
- 新增加载函数：`load_policy_core`、`load_policy_all`、`load_qiushi_article_index`、`load_qiushi_chunks`、`load_qiushi_quotes_core`、`load_qiushi_quotes_candidates`、`load_topic_frameworks`。
- 当前不读取 `raw_articles/qiushi/` 全文目录。

**后续注意事项**

1. 正式接入邮件内容前，应优先使用 `load_policy_core()` 作为“今日政策坐标”的展示级政策原文来源。
2. 扩展候选、切片和权威引用暂时只作为后续检索能力预留，不应在本阶段改变邮件正文。
3. OSS 模式后续单独实现，当前加载器读取本地 `KNOWLEDGE_BASE_DIR`。

### 2026-05-31｜知识库目录与配置预接入

**改动原因**

为后续接入“今日政策坐标”和《求是》专题知识库，先把已整理好的知识库文件放入仓库，并预留本地/OSS 两种读取模式。本阶段只做目录、配置和打包资产接入，不改变生成、渲染、发送和质量门禁逻辑。

**已改文件**

- `config.py`
- `.env.example`
- `README.md`
- `scripts/build_fc_package.ps1`
- `content_harness/deployment_rules.md`
- `knowledge_base/policy_corpus/policy_statements_core.jsonl`
- `knowledge_base/policy_corpus/policy_statements.jsonl`
- `knowledge_base/topic_knowledge/`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- 新增环境变量：`KNOWLEDGE_BASE_MODE=local`、`KNOWLEDGE_BASE_DIR=knowledge_base`、`KNOWLEDGE_OSS_PREFIX=`。
- `config.Settings` 新增知识库配置和路径属性：`knowledge_base_path`、`policy_corpus_path`、`topic_knowledge_path`。
- 仓库新增 `knowledge_base/policy_corpus/`，包含政策原文核心展示库和扩展候选库。
- 仓库新增 `knowledge_base/topic_knowledge/`，包含《求是》专题索引、切片、权威引用、专题框架和 `raw_articles/qiushi/` 原文目录。
- FC 打包脚本会复制 `knowledge_base/`，并检查核心政策库和专题索引文件存在。
- 本阶段不读取知识库、不写入 daily JSON、不改 Prompt、不改 renderer、不改发送逻辑、不改 quality_gate。

**后续注意事项**

1. 正式接入“今日政策坐标”时，优先读取 `knowledge_base/policy_corpus/policy_statements_core.jsonl`。
2. 切换 OSS 时，将 `KNOWLEDGE_BASE_MODE` 改为 `oss`，并设置 `KNOWLEDGE_OSS_PREFIX` 为 bucket 内对象前缀；OSS 鉴权继续复用现有 OSS 配置。
3. 接入生成逻辑前，应单独增加读取失败兜底，避免知识库缺失影响候选邮件生成。

### 2026-05-28｜阶段 2 抽取统一质量计算 helper

**改动原因**

`main.py` 中多处在 brief 被修复或重写后重复执行“渲染、各模块质检、content quality、quality gate 构造”逻辑。重复代码越多，后续修复字段同步、P0 repair、pre-send guard 时越容易出现“某一路径漏跑某个质检”的问题。

**已改文件**

- `main.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- 新增 `render_brief_outputs`，统一从 brief 生成纯文本和 HTML。
- 新增 `evaluate_all_quality`，统一计算今日一题、框架图、今日可带走、整封清洁度、速读、重复、表达质感、模块冗余、内容风险、选文质量、content quality 和 pre-send cleanliness。
- 新增 `build_gate_from_quality_map`，统一把质量 map 转成 `build_quality_gate(...)` 参数，避免各处手写参数顺序。
- 新增 `recompute_after_brief_change`，用于 brief 变更后统一执行 schema 校验、URL 标注、最终选文摘要、主题变化检查、subject 重算、渲染和质量复算。
- 候选件复核、content quality minor fix、content issue rewrite、pre-send cleanliness guard、P0 repair 后的部分重复质检代码已改为使用统一 helper。
- 本阶段只抽函数和替换机械重复块，不拆文件、不改事件模式、不改发送判断、不改质量字段名。

**后续注意事项**

1. 后续继续替换剩余质量重复块时，应优先使用 `evaluate_all_quality` 和 `recompute_after_brief_change`，不要继续复制整段质检调用。
2. 第 3 阶段拆文件前，应先确认 `quality.final`、`quality_gate`、`latest_quality.json` 和管理员报告结构没有字段缺失。

### 2026-05-28｜阶段 1 部署文档与打包包名统一

**改动原因**

代码优化第一阶段先处理低风险的部署和仓库卫生问题。此前 README 写上传 `gongkao-morning-mailer.zip`，Bash 打包脚本输出 `function.zip`，PowerShell 打包脚本默认输出 `_release\gongkao-morning-mailer.zip`，容易导致本地、GitHub 和阿里云 FC 上传说明不一致。

**已改文件**

- `README.md`
- `requirements.txt`
- `.gitignore`
- `scripts/build_fc_package.ps1`
- `content_harness/deployment_rules.md`
- `docs/deploy_aliyun_fc.md`
- `docs/architecture.md`
- `docs/code_optimization_execution_plan.md`
- `docs/code_optimization_execution_plan.docx`

**最新版行为**

- 部署包统一命名为 `function.zip`。
- PowerShell 打包脚本默认在仓库根目录生成 `function.zip`；如果传入相对路径，会按仓库根目录解析。
- README 和部署规则文档统一说明上传 `function.zip`。
- 新增阿里云 FC 部署说明，明确本地检查、打包、上传、触发器和发布后验证步骤。
- 新增当前运行架构文档，记录 `main.handler`、HTTP 阻断、feedback、夜间候选、早晨发送、周报 PDF 和质量门禁边界。
- `reportlab` 依赖锁定为 `reportlab==4.5.1`，避免 FC 打包时安装不可预期版本。
- `.gitignore` 补充 `chardet/`，防止依赖目录误入仓库。

**后续注意事项**

1. 本阶段不删除仓库中已跟踪的 `reportlab/` 目录，后续如要移除 vendored 目录，必须单独验证 PDF 生成和 FC 打包。
2. 后续拆分 `main.py` 前，应先完成质量计算 helper 抽取，避免在多个文件之间复制重复质检代码。

### 2026-05-27｜渲染层与发送前清洗统一兜底去除展示标签泄漏

**改动原因**

用户继续反馈，最终 `candidate_email_*.html` 中仍反复出现“可用表达：可用表达：”“如果点原文，重点看：如果点原文，重点看：”“审题关键：审题关键：”“作答主线：作答主线：”等展示型小标题重复。单靠上游生成约束和早期渲染去重还不够，需要在渲染层和发送前清洗层同时做更稳的兜底。

**已改文件**

- `email_renderer.py`
- `pre_send_cleanliness.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- `email_renderer.py` 新增统一的展示前缀剥离逻辑，最终渲染 HTML / 纯文本时会重复剥离以下前缀，直到字段正文恢复为纯内容：
  - `如果点原文，重点看`
  - `可用表达`
  - `作答主线`
  - `审题关键`
  - `换成考场话`
  - `考场话`
- 纯文本和 HTML 渲染层都会在 `original_reading_focus`、`rewritable_expression`、`exam_focus`、参考句式等展示型字段上应用这层兜底，而不是只依赖上游 brief 已经被修干净。
- `pre_send_cleanliness.py` 补齐了 `usable_for_exam` 和 `exam_use[*]` 这两个字段别名的前缀清洗，避免质检命中一个字段名、最终渲染却走另一个字段名，导致“修了但邮件里还在”。
- 这次改动只处理展示标签泄漏，不改模块结构、不改字段含义、不重写正文内容。

**后续注意事项**

1. 如果后续新增新的“标题 + 正文”展示模块，且正文值也可能自带同名小标题，必须同步加入渲染层与 `pre_send_cleanliness.py` 的前缀剥离名单。
2. 生成侧仍应尽量避免输出这些前缀；当前修复是展示层兜底，不代表可以放松上游 Prompt 约束。

### 2026-05-26｜修复 rewrite 后候选件、HTML、纯文本与质量卡不一致

**改动原因**

用户反馈 `latest_quality_card.md` 的“自动修复摘要”显示某些字段已经修好，但最终 `latest.json`、`candidate_email_*.html`、`plain_text` 里仍残留半截句、小标题前缀或分号结尾；同时质量卡里同一条修复摘要会重复出现。问题本质是 rewrite 后写回、复检、再渲染和质量卡摘要去重没有完全打通。

**已改文件**

- `main.py`
- `pre_send_cleanliness.py`
- `admin_report.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- `content_issue_rewrite` 或 `p0 repair` 之后，会重新同步：
  - `brief`
  - `plain_text`
  - `html_body`
  - `content_quality`
  - `quality_gate`
  保证最终候选件里保存的是修复后的最终产物，而不是“摘要说修了，但正文还没换”。
- 如果 `content_issue_rewrite` 导致内容质量分数明显下降，会整轮回滚，并把该轮 rewrite 标记为 `rolled_back`；被回滚的 rewrite 不再继续污染最终质量卡和候选件摘要。
- `merge_rewrite_results` 会跳过已回滚轮次，`admin_report.py` 会对自动修复摘要去重，避免同一条修复在质量卡里重复展示两次。
- `pre_send_cleanliness.py` 补充了字段级兜底：
  - `today_takeaway.framework` 纳入正文型字段清洁范围
  - `daily_question.thirty_second_answer`
  - `daily_question.output_sentence_template`
  如果只剩末尾分号，会直接字段级改成句号，而不是为这一个标点问题重写整个 `daily_question`
- `main.py` 在发送前清洁度守卫之后也会重新评估 `content_quality`，避免质量门禁仍沿用清洁前的旧结果。

**后续注意事项**

1. 以后凡是新增“自动修复但不一定重写全文”的字段级清洁逻辑，都要确认 `latest.json`、`plain_text`、`html_body`、`quality_card` 四份产物是否同步更新。
2. 如果后续再出现“质量卡说修了，但邮件里没修”的问题，优先排查写回顺序、回滚标记和摘要去重，而不是先怀疑单条 Prompt。

### 2026-05-25｜新增正文型字段句末标点守卫与半截句尾检测

**改动原因**

用户反馈生成邮件里经常出现“像字段拼接结果”的正文：有些展示型内容缺句号，有些句子停在“可落地”“有助于”“关键在于”“从而”等明显半截尾巴上，还有个别 30 秒参考句式只剩一个分号结尾。需要在发送前增加确定性的正文收口规则，先把成品感和截断风险稳住。

**已改文件**

- `pre_send_cleanliness.py`
- `main.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- 发送前清洁度守卫会对以下正文型字段自动补中文句号：只要字段结尾不是 `。！？；.!?」』）】》`，就补成完整句，覆盖范围包括：
  - `today_focus`
  - `must_remember_sentence`
  - `featured_article.one_sentence`
  - `original_reading_focus`
  - `three_useful_points`
  - `exam_use / usable_for_exam`
  - `rewritable_expression`
  - `daily_question.exam_focus`
  - `daily_question.breaking_hint`
  - `daily_question.candidate_answer`
  - `daily_question.output_sentence_template`
  - `daily_question.thirty_second_answer`
  - `today_takeaway.framework`
  - `today_takeaway.common_knowledge_points`
  - `today_takeaway.golden_sentences[*].sentence`
  - `quick_reads[*].one_sentence`
  - `quick_reads[*].exam_value`
- 如果正文型字段以“可落地、可以用于、适合转化为、有助于、体现出、关键在于、主要包括、从而、进而、同时、并且”等高风险尾巴结束，会记为 `suspected_truncated_sentence`，并进入质量门禁。
- 今日一题的 `thirty_second_answer` / `output_sentence_template` 如果只剩末尾分号，会在字段级直接改成句号，避免因为一个尾标点重写整个题目模块。
- `main.py` 已把 `suspected_truncated_sentence` 纳入 `quality_gate` 的 P0 集合，确保这类明显半截句不会被放过。

**后续注意事项**

1. 这套规则只负责“收尾”和“识别明显半截句”，不代替内容重写；如果正文逻辑本身不通顺，仍要走原有 rewrite / 质量门禁链路。
2. 后续如果新增正文型字段，需要同步加入 `BODY_TEXT_PATHS`，否则不会自动补句号或识别半截尾巴。

### 2026-05-25｜新增基层身份越权作答风险质检

**改动原因**

用户指出，今日一题如果题干身份是基层、街道、社区、市场监管所、城管、工作人员等，答案里却直接写“制定行业标准”“修改包装”“推行包装标识”甚至“无明确违法依据处罚普通高糖高油食品商户”，会形成明显越权甚至违法表述。这类问题不能只当普通表达瑕疵处理，需要单独拦截。

**已改文件**

- `question_quality.py`
- `main.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- `question_quality.py` 新增 `grassroots_authority_overreach` 检查：当题干命中基层身份语境时，会联动扫描 `answer_framework` 与 `candidate_answer`。
- 对以下高风险表述直接按高风险拦截：
  - `依法处理持续售卖普通高糖高油食品商户`
  - `无明确违法依据处罚`
  - `处罚普通高糖高油食品`
  - `查处普通高糖高油食品`
  - `取缔售卖普通高糖高油食品`
- 对以下“把上级权限写成基层直接权限”的表述按中风险提示：
  - `制定行业标准`
  - `修改包装`
  - `推行包装标识`
  - `统一包装标识`
  - `强制包装标识`
  - `要求商户修改包装`
- 如果这些表述前面明确写了“建议上级 / 报请上级 / 推动完善 / 上报”等限定语，规则会尽量识别为“建议上级做”，不误伤。
- `main.py` 已把 `grassroots_authority_overreach` 纳入 `quality_gate` 的 P0 集合。对于基层身份题，这类越权答案不能直接放行。

**后续注意事项**

1. 这条规则的核心不是“越保守越好”，而是明确区分三层权限：基层可直接做、建议上级做、只有明确违法时才依法查处。
2. 如果后续扩展到教育、住建、市场监管等更多身份题型，应继续补充越权关键词和合法限定语，而不是只靠现有几个示例词。

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
### 2026-06-01｜政策坐标使用历史与 14 天去重
**改动原因**

“今日政策坐标”已经接入 JSON、渲染和质检，需要再加一层“使用历史 + 近 14 天去重”，避免连续多天重复使用同一政策原文、同一条《求是》表达或同一专题框架。
**已改文件**

- `policy_coordinate_usage_history.py`
- `policy_coordinate_matcher.py`
- `main.py`
- `scripts/check_policy_coordinate_usage_history.py`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- 新增 `data/policy_coordinate_usage_history.jsonl` 的独立 JSONL 历史管理模块，缺文件时自动使用空历史，坏行会跳过并返回 warning，不会中断主流程。
- `match_policy_coordinate_candidates(...)` 新增 `recent_usage` 参数：近 14 天内重复 `matched_policy_id` / `matched_qiushi_quote_id` 会强降权，同一 `matched_framework_id` 连续使用会降权，前两次主题相同时也会避免第 3 天继续用同一主题。
- 如果没有其他合适材料，允许低优先级重复，但会在 `debug_scores.usage_history.selected_repeat_notes` 和运行日志中说明为什么还是选了重复项。
- 新增 `build_policy_coordinate_usage_record(...)`，在整封邮件最终通过质检后，单独写入 `policy_coordinate` 使用历史，不影响 `sent_history.json` 原有逻辑。
- `nightly candidate`、手动测试和被 quality gate 阻断的运行会显示 skip reason，不写入此次去重历史。
- JSONL 写入失败时只记日志 warning，不会中断生成、发送或其他归档链路。
**后续注意事项**

1. 当前 usage history 故意不和 `sent_history.json` 共享存储，后续如需 OSS 化，应单独设计新的存储模式，不要直接搬用 `sent_history` 逻辑。
2. 目前去重历史只针对非 candidate / 非测试 / 非整体阻断运行进行记录，如果后续希望让 preview 也参与去重，应单独评估是否影响正式晨发。
### 2026-06-02｜政策坐标主题试跑与接入报告
**改动原因**

在前 7 个任务完成后，需要做 3 个主题试跑，验证 `policy_coordinate` 在 daily JSON、HTML、plain_text、质检和近 14 天去重链路中的实际表现，并沉淀一份可交接的接入报告。
**已改文件**

- `main.py`
- `scripts/run_policy_coordinate_trials.py`
- `docs/POLICY_COORDINATE_INTEGRATION_REPORT.md`
- `output/policy_coordinate_trials/*`
- `CHANGELOG_HARNESS.md`

**最新版行为**

- 新增 `scripts/run_policy_coordinate_trials.py`，复用 `candidates/latest.json` 的完整 brief 结构，构造 3 组模拟主题输入并走现有政策匹配、渲染和质检链路。
- 试跑主题覆盖：基层治理 / 新就业群体 / 城市治理；高质量发展 / 新质生产力；民生保障 / 就业。
- 试跑会输出 `daily.json`、`email.html`、`plain_text.txt`、`quality.json`、`run.log` 到 `output/policy_coordinate_trials/<slug>/`。
- 试跑使用隔离的 `policy_coordinate_usage_history.jsonl`，验证 14 天去重逻辑可运行，同时不污染正式生产历史。
- `main.py` 增加了对 `exam_transfer` 的二次兜底：当匹配到的政策语料 `exam_usage` 过于展示化、缺少具体答题角度时，会回退为程序生成的结构化考场迁移句。
- 自动生成 `docs/POLICY_COORDINATE_INTEGRATION_REPORT.md`，汇总文件改动、知识库读取、字段、渲染位置、质检规则、3 个样例结果、风险与 OSS 切换说明。
**后续注意事项**

1. 当前试跑验证的是“政策坐标接入链路”而不是“真实选文质量”，后续上线前仍应结合真实抓取文章抽样复核几轮。
2. 如果后续实现知识库 OSS 读取，建议同步把试跑脚本改成可切换 `local/oss` 两种模式，避免报告与生产行为分叉。
