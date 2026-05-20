# Weekly Knowledge Log

用于记录每周知识库新增情况。每周至少新增 2 个 bad example 和 1 个 good example。

## 2026-W19

### Good Examples

- `good_examples/daily_question.md#GQ-001`：场景化、矛盾化、任务明确的基层治理题。

### Bad Examples

- `bad_examples/daily_question.md#BQ-001`：过宏大题目，缺身份、场景、矛盾、任务。
- `bad_examples/framework_map.md#BF-001`：孤立数字框架，数字没有对象、单位、含义。
- `bad_examples/quick_reads.md#BR-001`：速读只有新闻摘要，没有考试价值。

### Patterns Updated

- `exam_patterns/article_to_question.md`：补充“文章到题目”的四步转换法。

## 2026-W20

### Rules Added

- `content_harness/display_rules.md`：沉淀模块边界、标签泄漏、框架图不加考场迁移、三版本同步规则。
- `content_harness/fact_safety_rules.md`：沉淀未核实政策事实的安全边界。
- `content_harness/deployment_rules.md`：沉淀 FC 发布前依赖自检。
- `content_harness/p0_repair_workflow.md`：沉淀 P0 repair 闭环和 blocked case 归档规则。

### Bad Examples

- `bad_examples/today_takeaway.md#BT-003`：金句和适用场景被截成半句话。
- `bad_examples/today_takeaway.md#BT-004`：未核实政策事实。
- `bad_examples/quick_reads.md#BR-003`：速读缺少一句话概括。
- `bad_examples/daily_question.md#BQ-003`：题型标注和题干气质错位。

### Good Examples

- `good_examples/today_takeaway.md#GT-002`：事实安全的时政常识表达，用机制表达替代未核实具体政策事实。

### Quality Issues Added

- `quality_issues.jsonl` 新增 `QI-20260513-011` 至 `QI-20260513-015`，覆盖金句截断、速读缺字段、事实风险。
- `quality_issues.jsonl` 新增 `QI-20260514-016` 至 `QI-20260514-019`，覆盖框架图重复、标题截断、标签泄漏、题型错位。
- `quality_issues.jsonl` 新增 `QI-20260513-020`，覆盖部署依赖缺失。
