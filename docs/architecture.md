# 当前运行架构

本文档描述当前公考晨读邮件项目的入口、路由和关键链路。后续拆分 `main.py` 时，应保持本文件中的行为边界不变。

## 1. 总入口

阿里云函数计算入口：

```text
main.handler
```

本地测试入口：

```powershell
python main.py
```

`handler(event, context)` 负责解析事件并按模式分发。普通 HTTP 请求必须被阻断，不能触发每日生成或正式发送。

## 2. 路由概览

```text
定时触发器 / 手动测试 / HTTP 请求
          |
          v
main.handler
          |
          +-- feedback 请求 -> handle_feedback
          |
          +-- 普通 HTTP 请求 -> http_block_response
          |
          +-- feedback 测试邮件 -> send_feedback_test_email
          |
          +-- 周报 PDF 候选 -> generate_weekly_pdf_candidate
          |
          +-- 周报 PDF 发送 -> run_weekly_pdf / send_weekly_pdf_candidate
          |
          +-- 早晨发送 -> send_saved_candidate
          |
          +-- 夜间候选 / 普通生成 -> run_daily_brief
```

## 3. 夜间候选链路

事件：

```json
{"mode":"nightly_candidate"}
```

职责：

- 抓取和筛选候选文章。
- 调用大模型生成结构化 brief。
- 执行 schema 校验、渲染、质量评估和质量门禁。
- 必要时执行模块重写、content issue rewrite、P0 二次修复。
- 保存候选件和质量报告。
- 可选发送管理员质检报告。

安全边界：

- 不给普通用户发送邮件。
- 不写正式发送历史。
- P0 fail 时保存失败留档并阻断候选发送。

## 4. 早晨发送链路

事件：

```json
{"mode":"morning_send"}
```

职责：

- 读取当天候选件。
- 复核候选件日期和质量门禁。
- 只有 `quality_gate.overall == "ok"` 时才发送。
- 发送成功后再写历史和归档。

安全边界：

- 候选件缺失时 blocked。
- 日期不匹配时 blocked。
- 质量门禁失败时 blocked。
- 不允许早晨临时生成正文并正式发送。
- `SEND_EMAIL=false` 时不得真实发送。

## 5. 周报 PDF 链路

周报能力包含：

- 生成周报 PDF 候选。
- 读取候选件中的 PDF 附件路径。
- 发送带附件的周报邮件。
- 在附件缺失或读取失败时返回明确错误，不发送空附件。

周报 fallback 代码属于生产安全能力，不能为了精简而删除。

## 6. 质量门禁链路

当前质量体系包括：

- `brief_quality.py`
- `question_quality.py`
- `framework_quality.py`
- `takeaway_quality.py`
- `quick_reads_quality.py`
- `duplication_quality.py`
- `expression_quality.py`
- `module_redundancy_quality.py`
- `content_risk_quality.py`
- `content_quality_reviewer.py`
- `pre_send_cleanliness.py`
- `scripts/validate_daily_brief.py`

质量门禁职责：

- 汇总 P0/P1/P2 问题。
- 决定是否允许发送。
- 触发必要的重写和 P0 二次修复。
- 产出 `latest_quality.json`、管理员报告和 Harness 指标。

后续优化只能抽函数或移动文件，不能删除、弱化或短路这些规则。

## 7. 数据与产物

常见运行产物：

- `latest_articles.json`
- `latest_brief.json`
- `latest_quality.json`
- `latest_email.html`
- `latest_email.txt`
- `latest_run.log`
- `latest_candidate_send.log`
- `candidates/YYYY-MM-DD.json`
- `blocked_runs/YYYY-MM-DD/`
- `harness_metrics.jsonl`
- `sent_history.json`

这些产物不应提交到 GitHub。真实用户邮箱、发送历史、归档产物和密钥也不得提交。

## 8. 后续拆分建议

推荐后续按低风险到高风险拆分：

1. `entrypoint_utils.py`：事件解析、HTTP 判断、路由辅助函数。
2. `run_summary.py`：运行摘要和 LLM trace 汇总。
3. `weekly_pipeline.py` / `attachment_utils.py`：周报与附件读取。
4. `candidate_send_pipeline.py`：早晨候选发送。
5. `quality_pipeline.py` / `quality_gate.py`：统一质量计算和门禁构造。
6. `daily_pipeline.py`：每日生成主流程。

每一步都应保持字段、事件模式、发送判断和失败语义不变。
