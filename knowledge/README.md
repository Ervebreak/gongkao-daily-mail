# Knowledge Base

本目录用于沉淀公考晨读邮件项目的可复用样例和反例。它不是运行必需文件，但属于 Harness 的长期护城河：每次质检、人工复盘、用户反馈后，都应把高价值经验沉淀到这里。

## 目录结构

```text
knowledge/
  README.md
  weekly_log.md
  quality_issues.jsonl
  regression_cases/
    half_sentence/
    label_leak/
    policy_weak_match/
    lite_cta_salesy/
    weekly_pdf_path_error/
    internal_trace_leak/
    daily_question_mismatch/
  good_examples/
    daily_question.md
    framework_map.md
    today_takeaway.md
    full_email.md
  bad_examples/
    daily_question.md
    framework_map.md
    today_takeaway.md
    quick_reads.md
  exam_patterns/
    shenlun_patterns.md
    interview_patterns.md
    article_to_question.md
```

## 沉淀规则

- 每周至少新增 2 个 `bad_examples`。
- 每周至少新增 1 个 `good_examples`。
- 有稳定转化方法时，补进 `exam_patterns`。
- 反例必须写清楚：坏在哪里、为什么坏、怎么改。
- 好例必须写清楚：好在哪里、可复用规则是什么、适用边界是什么。
- 不要只保存成品句子，要保存“判断依据”和“迁移方法”。

可用以下命令检查本周是否满足最低沉淀要求：

```powershell
python scripts\check_knowledge_base.py
```

可用以下命令生成周度质量复盘：

```powershell
python scripts\weekly_quality_review.py --metrics output\harness_metrics.jsonl
```

可用以下命令运行历史问题回归样例：

```powershell
python scripts\run_regression_cases.py
```

## 使用方式

修改 Prompt、质检规则、模块生成逻辑前，先读对应样例：

- 今日一题：读 `good_examples/daily_question.md`、`bad_examples/daily_question.md`、`exam_patterns/article_to_question.md`。
- 框架图：读 `good_examples/framework_map.md`、`bad_examples/framework_map.md`。
- 今日可带走：读 `good_examples/today_takeaway.md`、`bad_examples/today_takeaway.md`。
- 速读：读 `bad_examples/quick_reads.md`。
- 题型转换：读 `exam_patterns/shenlun_patterns.md`、`exam_patterns/interview_patterns.md`、`exam_patterns/article_to_question.md`。

## 与现有文件关系

- `quality_issues.jsonl`：历史质量问题流水，适合保留原始问题和处理状态。
- `bad_examples/`：从质量问题中提炼出来的稳定反例。
- `good_examples/`：人工认可或线上表现好的正例。
- `exam_patterns/`：从多次正反例中抽象出的题型和转化方法。

## 质量问题流水字段

新增质量问题时，优先使用以下字段，便于后续自动统计和 few-shot 检索：

- `id`：唯一编号，例如 `QI-20260513-011`。
- `date`：问题发生或沉淀日期。
- `module`：出问题的模块或链路，例如 `today_takeaway.golden_sentences`、`quick_reads`、`deployment`。
- `issue_type`：问题类型，例如 `truncated_sentence`、`label_leak`、`unsupported_claim`。
- `source`：来源，例如 `user_feedback`、`internal_review`、`blocked_run`。
- `bad_example`：原始坏输出或症状。
- `reason`：根因判断，区分模型、schema、渲染、repair、部署或流程问题。
- `fix_rule`：应沉淀成的规则。
- `related_rule`：关联规则或文档。
- `checker_to_add`：是否需要脚本化检测或已由哪个质检覆盖。
- `status`：`new`、`converted_to_rule`、`covered_by_checker`、`needs_checker`、`blocked_workflow`。
- `severity`：`P0`、`P1`、`P2` 或 `high`、`medium`、`low`。

## 2026-05 重点沉淀方向

2026-05-12 至 2026-05-14 的问题优先沉淀到四类资产：

- 规则：`content_harness/content_rules.md`、`display_rules.md`、`fact_safety_rules.md`、`deployment_rules.md`。
- 质检：`brief_quality.py`、`expression_quality.py`、`quick_reads_quality.py`、`takeaway_quality.py`、`scripts/validate_daily_brief.py`。
- 修复闭环：`content_harness/p0_repair_workflow.md`、`llm_client.py`、`main.py`。
- 案例库：`quality_issues.jsonl` 和 `bad_examples/`。
