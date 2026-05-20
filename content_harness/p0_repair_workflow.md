# P0 Repair Workflow

本文件沉淀 2026-05 内测中的 P0 修复闭环问题。凡修改 `main.py`、`llm_client.py`、`quality_gate`、模块重写和 blocked run 逻辑，应先读本文件。

## 1. 判断原则

1. `quality_gate.overall != ok` 时禁止发送。
2. 内容质量模型的 `can_send=true` 不能覆盖结构质检 P0。
3. P0 修复不能只“重新问模型一次”；必须跳出导致 P0 的原始机制。
4. 二次 repair 后仍 fail，应保存 blocked run，并写入质量案例库。

## 2. 标准流程

1. 聚合 `quality_gate.p0_issues`，按 module 分组。
2. 每个 P0 module 必须有 repair handler；无 handler 时走 deterministic fallback。
3. repair 后先重跑对应模块质检。
4. 对应模块通过后，再重跑全局质检。
5. 同一模块二次 repair 后仍 fail，保存 `blocked_runs` 并禁止发送。
6. blocked case 自动写入 `knowledge/quality_issues.jsonl` 或至少进入管理员报告，供周复盘沉淀。

## 3. 模块修复策略

| 模块 | 常见 P0 | 首选修复 | 兜底策略 |
| --- | --- | --- | --- |
| `today_takeaway` | 金句/适用场景半截句、事实风险 | 重写金句和常识点 | 使用固定安全模板替换半截句和未核实事实 |
| `quick_reads` | 缺 `one_sentence`、考试价值半截句 | 只重写 quick_reads | `one_sentence = summary > reason > exam_value` |
| `featured_article.exam_use` | 标签泄漏、混入可用表达 | 清理标签并重写为纯句子 | 删除标签前缀，保留完整句 |
| `article_framework_map` | 半截标题、孤立数字、考场迁移节点 | 重写或过滤异常 step | 保留原文结构节点，删除考场迁移节点 |
| `html_body/plain_text` | 三版本不同步 | 以 `brief` 重渲染 | 禁止手改 HTML |

## 4. 必须沉淀的 P0

以下问题一旦出现，应进入 `knowledge/quality_issues.jsonl`：

- 金句、适用场景、30 秒表达、速读价值半截句。
- 速读必填字段缺失。
- 事实安全风险。
- 依赖缺失导致 FC 启动失败。
- P0 repair 后仍失败。

---

## 6. 题库接入相关 P0 边界

题库读取失败本身不是 P0。

以下情况不应阻断发送：

- OSS 题库文件不存在；
- OSS 鉴权或网络读取失败；
- CSV 字段缺失；
- 匹配不到合适题目；
- 本地兜底文件不存在。

正确行为：

1. 记录 `question_bank_warnings`；
2. `question_bank_refs` 置空；
3. 继续旧版“今日一题”生成；
4. 质检只检查最终正文质量。

以下情况才属于 P0 或准 P0：

- 题库异常导致主程序退出；
- 题库异常导致候选邮件无法保存；
- 题库异常导致发送链路中断；
- 最终邮件正文泄漏真题元数据；
- 最终题干出现“根据材料/材料三”等材料依赖表达且自动修复失败。

材料依赖优先走局部修复：只重写 `daily_question`，不重写整封邮件。
