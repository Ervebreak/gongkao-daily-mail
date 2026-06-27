# Rule Registry

本表用于登记当前项目里的规则分层，避免把每天必须生效的红线、模块级触发规则、案例召回规则混在一起维护。

使用方式：

1. 改运行时 Prompt、质检、渲染边界前，先看本表确认规则属于 L1 / L2 / L3 哪一层。
2. 改高风险字段前，再查看 [field_impact_map.json](./field_impact_map.json)。
3. 如果新增规则进入运行时注入，需同步更新 `CHANGELOG_HARNESS.md`。

## L1：每天必须生效的质量红线

| 规则 | 当前来源 | 说明 |
| --- | --- | --- |
| 半截句禁止外发 | `quality_gate.py`, `pre_send_cleanliness.py`, `content_quality_reviewer.py`, `runtime_prompt_rules.md` | 最终 `plain_text` / `html_body` 不得出现可见截断、残句、尾部未收束。 |
| 字段标题泄漏禁止外发 | `content_quality_reviewer.py`, `lite_email_quality.py`, `weekly_pdf_quality.py`, `display_rules.md` | 不得把字段名、栏目名、内部 schema 标签直接暴露给用户。 |
| 内部痕迹禁止外发 | `weekly_pdf_quality.py`, `lite_email_quality.py`, `quality_gate.py` | 禁止出现 debug、candidate、quality gate、P0、JSON、后台字段、内部测试等词。 |
| quality gate 统一阻断 | `quality_gate.py`, `main.py`, `scripts/validate_daily_brief.py` | 主流程、脚本验证、早晨复检尽量共用同一套 gate 口径。 |
| 政策坐标弱匹配隐藏 | `policy_coordinate_quality.py`, `policy_coordinate_semantic_fit.py`, `quality_gate.py` | semantic fit 弱、policy match 低、连接泛泛时默认隐藏。 |
| 早晨发送前安全复检 | `main.py`, `pre_send_cleanliness.py`, `quality_gate.py` | 发送保存候选件前按当前代码再次检查，发现 drift 或 recheck error 时阻断正式发送。 |

## L2：模块触发规则

| 模块 | 当前来源 | 说明 |
| --- | --- | --- |
| 今日一题 | `daily_question_skill.md`, `question_quality.py`, `prompt_templates.py` | 题型、身份、场景、矛盾、任务、作答框架长度、30 秒表达等。 |
| 政策坐标 | `policy_coordinate_matcher.py`, `policy_coordinate_reranker.py`, `policy_coordinate_quality.py` | 权威表达优先、policy fallback、weak match 隐藏、日志与 rerank。 |
| 简版邮件 | `lite_email_renderer.py`, `lite_email_quality.py`, `lite_paid_cta.py` | 主文、3 步看懂、作答角度、CTA、退订、转化文案安全。 |
| 周 PDF | `weekly_report.py`, `weekly_typst_export.py`, `weekly_pdf_quality.py` | full / lite preview 分流、OSS 路径、前台文案清理、内部痕迹过滤。 |
| 到期提醒 | `email_sender.py` | `paid_trial` 的 d3 / d1 / d0 变体、提醒 banner、提醒去重。 |
| 推荐机制 | `email_sender.py`, `feedback.py`, `config.py` | `referral_code` / `referred_by` 字段支持，仅发送阶段个性化展示。 |

## L3：案例召回与记忆规则

| 规则 | 当前来源 | 说明 |
| --- | --- | --- |
| bad_examples / good_examples | `knowledge/` | 用于沉淀正反例，不直接替代运行时 gate。 |
| blocked_runs | `output/blocked_runs/` | 记录被阻断的运行，供 reflection、回归和人工复盘。 |
| regression_cases | `tests/`, `knowledge/quality_issues.jsonl` | 同类问题复现后应提升为自动化测试或样例。 |
| quality reflections | `quality_reflections.py`, `knowledge/quality_issues.jsonl` | 将真实故障转成 detector / auto_fix / promoted_to 等结构化记录。 |

## 当前阶段约束

- L1 规则优先于 L2 / L3，不允许为了通过某个模块而绕过每天必须生效的红线。
- L2 规则可以按模块演进，但高风险字段改动前必须先查 `field_impact_map.json`。
- L3 规则主要服务于沉淀、回归和审计，不直接改变用户可见内容，除非后续明确提升为 L1 / L2。
