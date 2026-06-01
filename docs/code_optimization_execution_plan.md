# 公考晨读邮件代码优化可执行计划

生成日期：2026-05-28  
评估基准：GitHub 远端 `origin/main`，已 fetch 到 `5bf4603`  
适用仓库：`Ervebreak/gongkao-daily-mail`

## 结论

原 `gongkao_mail_code_optimization_4_stage_plan.md` 的方向是合理的：先稳住部署和文档，再抽重复质检逻辑，最后拆 `main.py`。这比一次性大重构更安全，也符合当前项目已有真实发送链路、质量门禁、候选件、OSS/归档、管理员报告和周报 PDF 的现状。

但原方案需要补充几处执行层修正：

1. 当前 `main.py` 在 `origin/main` 仍承担入口、HTTP 防误触发、夜间候选、早晨发送、周报、每日生成、质量门禁和运行摘要，确实应该拆，但不能第一步就拆。
2. 当前 `main.py` 中质检调用重复明显，应先抽统一质量计算函数，再移动文件。
3. README 写的是上传 `gongkao-morning-mailer.zip`，Bash 打包脚本输出 `function.zip`，PowerShell 打包脚本默认输出 `_release\gongkao-morning-mailer.zip`，部署包名必须先统一。
4. `requirements.txt` 里 `reportlab` 未锁版本，仓库又跟踪了 `reportlab/` 目录。这里不能简单删除，必须先确认 FC 打包和 PDF 生成依赖策略：要么固定 pip 依赖并移除 vendored 目录，要么明确保留 vendored 目录并在文档解释原因。
5. 当前没有 `docs/` 和 `.github/workflows/`，文档与 CI 需要分阶段补，避免把“文档、清理、重构、测试”混成一个 PR。

## 不变红线

任何阶段都不得改变以下行为：

- 普通 HTTP 请求不能触发每日生成或正式发送。
- `SEND_EMAIL=false`、`RUN_MODE=test`、`TEST_LLM_MODEL=mock` 必须继续阻断真实发送。
- 早晨发送必须只读取候选件，不能因为候选件缺失临时生成并正式发送。
- `quality_gate.overall != "ok"` 的候选件不得发给用户。
- 夜间候选不得写入正式发送历史。
- 管理员报告不得发给普通订阅列表。
- 不得删除或弱化 `brief_quality.py`、`question_quality.py`、`framework_quality.py`、`takeaway_quality.py`、`quick_reads_quality.py`、`duplication_quality.py`、`expression_quality.py`、`module_redundancy_quality.py`、`content_risk_quality.py`、`content_quality_reviewer.py`、`pre_send_cleanliness.py`。
- 不得删除 `content_harness/`、`knowledge/`、`tests/quality_cases/`、`candidate_store.py`、`weekly_report.py`、`weekly_typst_export.py`。
- 所有行为变化必须追加记录到 `CHANGELOG_HARNESS.md`。

## 阶段 0：基线确认

分支：不建业务分支，先只做检查。

目标：确认要优化的是 GitHub 当前代码，而不是本地旧副本或未提交修改。

执行步骤：

1. 检查本地状态：
   ```powershell
   git status --short
   git branch --show-current
   git remote -v
   ```
2. 同步远端信息：
   ```powershell
   git fetch origin
   git diff --stat HEAD..origin/main
   git diff --name-status HEAD..origin/main
   ```
3. 如果本地有未提交文件，例如 `CHANGELOG_HARNESS.md`，先确认是否属于当前任务。无关则不修改、不回滚。
4. 阅读必读文件：
   ```powershell
   Get-Content -Raw CHANGELOG_HARNESS.md
   Get-Content -Raw AGENTS.md
   Get-Content -Raw content_harness\00_index.md
   ```

验收标准：

- 明确当前工作基准是 `origin/main` 还是本地 `HEAD`。
- 明确本地未提交改动是否需要保留。
- 后续每个 PR 都从干净分支开始。

## 阶段 1：部署和仓库卫生统一

分支：`chore/docs-and-deploy-cleanup`

目标：不碰主流程代码，只修正部署说明、包名、依赖策略和忽略规则。

执行步骤：

1. 统一部署包名。建议选择一个标准名称，并同步修改 README、Bash 脚本、PowerShell 脚本。
   推荐标准：`function.zip`，因为 `scripts/build_fc_package.sh` 当前已经输出该名称，且适合 FC 上传说明。
2. 如果保留 PowerShell 打包脚本，调整默认输出到仓库根目录：
   ```powershell
   .\scripts\build_fc_package.ps1 -OutputZip .\function.zip
   ```
   或者在脚本默认值中直接改为 `Join-Path $root "function.zip"`。
3. 新增 `docs/deploy_aliyun_fc.md`，写清：
   - GitHub 拉取方式。
   - Bash 和 PowerShell 两种打包命令。
   - FC 入口必须是 `main.handler`。
   - 环境变量只在 FC 控制台配置，密钥不得提交。
   - Windows 优先使用 `scripts/build_fc_package.ps1`，Linux/WSL/Git Bash 可用 `scripts/build_fc_package.sh`。
4. 新增 `docs/architecture.md`，画清：
   - `main.handler` 路由。
   - HTTP 普通请求阻断。
   - feedback 入口。
   - 夜间候选。
   - 早晨候选发送。
   - 周报 PDF 候选和发送。
   - 每日生成主流程。
5. 处理依赖策略：
   - 先通过当前成功打包或 FC 成功运行版本确认 `reportlab` 实际版本。
   - 将 `requirements.txt` 中的 `reportlab` 固定为已验证版本，例如 `reportlab==4.5.1` 或 FC 当前稳定版本。
   - 决定是否移除仓库中已跟踪的 `reportlab/` 目录。
   - 如果移除，必须先验证 `python -m pip install -r requirements.txt -t build` 后 PDF 相关代码仍可 import。
6. 补 `.gitignore`：
   ```gitignore
   chardet/
   reportlab/
   ```
   注意：如果最终决定继续跟踪 `reportlab/`，不要加入 `reportlab/`。
7. 不删除任何业务代码。

验证命令：

```powershell
python -m py_compile main.py config.py scripts\validate_daily_brief.py
python -m py_compile weekly_report.py weekly_typst_export.py
.\scripts\build_fc_package.ps1 -OutputZip .\function.zip
```

验收标准：

- README、`docs/deploy_aliyun_fc.md` 和脚本输出包名一致。
- `function.zip` 可以生成。
- 包内包含 `main.py`、`requirements.txt`、`scripts/validate_daily_brief.py`、`data/question_bank/shenlun_question_bank_v3_a.csv`。
- 包内不包含 `.git`、`__pycache__`、`.pyc`、本地输出、真实订阅用户、发送历史。
- 本阶段没有修改 `main.py` 业务逻辑。

## 阶段 2：抽统一质量计算，不拆文件

分支：`refactor/quality-evaluation-helpers`

目标：减少 `main.py` 中重复的“渲染 + 质检 + 门禁”代码，但先不移动到多个模块。

当前依据：

- `origin/main:main.py` 中多处重复调用 `evaluate_daily_question`、`evaluate_framework_map`、`evaluate_takeaway`、`evaluate_brief_cleanliness`、`evaluate_quick_reads`、`evaluate_duplication`、`evaluate_expression_quality`、`evaluate_module_redundancy`、`evaluate_content_risks`、`evaluate_content_quality`。
- 重复位置覆盖候选评估、初次生成、模块重写、minor fix、P0 repair、pre-send cleanliness guard。

执行步骤：

1. 在 `main.py` 内先新增轻量 helper，不急着新建文件：
   - `render_brief_outputs(brief, subject)`
   - `evaluate_all_quality(brief, plain_text, html_body, *, test_invocation, selection_quality=None, cleanliness_quality=None)`
   - `build_gate_from_quality_map(quality)`
2. 再新增核心 helper：
   - `recompute_after_brief_change(brief, today, *, test_invocation, logger, reason, selection_quality=None, cleanliness_quality=None)`
3. 每替换一处重复代码就运行一次 `py_compile`。
4. 替换顺序从低风险到高风险：
   - 候选件当前质量复核。
   - 初次生成后的质量计算。
   - minor auto fix 后重算。
   - content issue rewrite 后重算。
   - pre-send cleanliness guard 后重算。
   - P0 repair 后重算。
5. 保持 `quality_gate` 输出字段名不变，保持 `latest_quality.json` 结构兼容。

验证命令：

```powershell
python -m py_compile main.py config.py
python -m py_compile brief_quality.py question_quality.py framework_quality.py takeaway_quality.py
python -m py_compile quick_reads_quality.py duplication_quality.py expression_quality.py module_redundancy_quality.py
python -m py_compile content_risk_quality.py content_quality_reviewer.py pre_send_cleanliness.py
$env:RUN_MODE="test"; $env:TEST_LLM_MODEL="mock"; $env:SEND_EMAIL="false"; python main.py
```

验收标准：

- `latest_quality.json` 仍生成。
- `quality_gate` 仍包含 `overall`、P0/P1/P2 问题列表和发送判断所需字段。
- P0 fail 仍阻断发送。
- 夜间候选仍只保存候选件，不写正式历史。
- 管理员报告逻辑不变。
- 本阶段不新拆 `daily_pipeline.py` 等大模块。

## 阶段 3：拆入口和纯工具函数

分支：`refactor/split-entrypoint-utils`

目标：先拆不会触发真实发送的入口解析、HTTP 判断和摘要工具，降低 `main.py` 顶层复杂度。

执行步骤：

1. 新建 `entrypoint_utils.py`，移动：
   - `normalize_event`
   - `_context_value`
   - `extract_request_id`
   - `extract_trigger_name`
   - `extract_trigger_time`
   - `build_log_context`
   - `event_mode`
   - `is_test_invocation`
   - `_http_query_params`
   - `_http_path`
   - `is_http_invocation`
   - `is_feedback_like_invocation`
   - `http_block_response`
   - `is_feedback_test_email_invocation`
   - `is_weekly_pdf_invocation`
   - `is_nightly_candidate_invocation`
   - `is_morning_candidate_send_invocation`
   - `is_weekly_pdf_candidate_invocation`
   - `resolve_delivery_date`
   - `should_generate_weekly_pdf_candidate_today`
2. 新建 `run_summary.py`，移动：
   - `summarize_llm_trace`
   - `build_run_summary`
3. `main.py` 只改 import 和调用，不改判断顺序。
4. 不移动 `run_daily_brief`、`send_saved_candidate`、`generate_weekly_pdf_candidate`。

验证命令：

```powershell
python -m py_compile main.py entrypoint_utils.py run_summary.py config.py
python -m py_compile scripts\validate_daily_brief.py
```

回归检查：

```powershell
$env:RUN_MODE="test"; $env:SEND_EMAIL="false"; $env:TEST_LLM_MODEL="mock"; python main.py
```

验收标准：

- 普通 HTTP 事件仍返回 block response，不触发生成。
- feedback-like 事件仍进入 feedback 路由。
- `{"mode":"nightly_candidate"}` 路由判断不变。
- `{"mode":"morning_send"}` 路由判断不变。

## 阶段 4：拆周报和附件读取

分支：`refactor/split-weekly-pipeline`

目标：移动相对独立的周报 PDF 候选和附件读取逻辑。

执行步骤：

1. 新建 `attachment_utils.py`，移动：
   - `_read_oss_bytes_from_path`
   - `weekly_pdf_attachment_from_candidate`
2. 新建 `weekly_pipeline.py`，移动：
   - `build_weekly_pdf_candidate_message`
   - `generate_weekly_pdf_candidate`
   - `send_weekly_pdf_candidate`
3. 保持周报 fallback、附件字段、OSS 路径解析和返回结构不变。
4. 不移动每日邮件主流程。

验证命令：

```powershell
python -m py_compile main.py weekly_pipeline.py attachment_utils.py weekly_report.py weekly_typst_export.py
python -m py_compile email_sender.py candidate_store.py config.py
```

验收标准：

- 周报 PDF 候选仍能生成。
- 周报候选发送仍能带附件。
- 附件读取失败时仍返回原有错误结构，不导致误发空附件。
- 非周报路径不受影响。

## 阶段 5：拆早晨候选发送

分支：`refactor/split-candidate-send-pipeline`

目标：移动早晨读取候选件、复核质量、发送和写历史的逻辑。

执行步骤：

1. 新建 `candidate_send_pipeline.py`，移动：
   - `evaluate_candidate_with_current_quality`
   - `send_saved_candidate`
2. 保持以下行为不变：
   - 候选件缺失时 blocked。
   - 日期不匹配时 blocked。
   - `quality_gate.overall != "ok"` 时 blocked。
   - `SEND_EMAIL=false` 时不真实发送。
   - 发送成功后才写历史和归档。
3. 对 candidate send 相关 import 做最小化整理。

验证命令：

```powershell
python -m py_compile main.py candidate_send_pipeline.py candidate_store.py email_sender.py history.py daily_archive.py
```

回归检查：

```powershell
$env:RUN_MODE="test"; $env:SEND_EMAIL="false"; $env:TEST_LLM_MODEL="mock"; python main.py
```

验收标准：

- `morning_send` 没候选件时不会临时生成并发送。
- `quality_gate.fail` 不发送。
- `SEND_EMAIL=false` 不发送。
- 管理员报告不会进入普通用户列表。

## 阶段 6：拆质量门禁和质量管线

分支：`refactor/split-quality-pipeline`

目标：把第 2 阶段抽出的质量 helper 移到独立模块，并移动质量门禁相关函数。

执行步骤：

1. 新建 `quality_pipeline.py`，移动：
   - `render_brief_outputs`
   - `evaluate_all_quality`
   - `build_gate_from_quality_map`
   - `recompute_after_brief_change`
2. 新建 `quality_gate.py`，移动：
   - `_quality_issue_signature`
   - `apply_manual_quality_override`
   - `build_quality_gate`
   - `_quality_for_p0_repair`
   - `merge_rewrite_results`
   - `evaluate_selection_quality`
   - `SENSITIVE_TOPIC_TERMS`
   - `GENDER_SENSITIVE_EXPRESSIONS`
   - `_stringify_for_quality`
   - `_selection_sensitive_surface`
3. 注意不要和 `scripts/validate_daily_brief.py` 的总门禁概念混淆。文件名如冲突明显，可改为 `quality_gate_builder.py`。
4. 保持 `build_quality_gate(...)` 参数顺序兼容，避免一次性改所有调用方。

验证命令：

```powershell
python -m py_compile main.py quality_pipeline.py quality_gate.py
python -m py_compile brief_quality.py question_quality.py framework_quality.py takeaway_quality.py
python -m py_compile quick_reads_quality.py duplication_quality.py expression_quality.py module_redundancy_quality.py
python -m py_compile content_risk_quality.py content_quality_reviewer.py pre_send_cleanliness.py
```

验收标准：

- `latest_quality.json` 结构不变。
- P0 repair 前后对比仍生成。
- `scripts/validate_daily_brief.py` 不受影响。
- `harness_metrics.jsonl` 字段不丢失。

## 阶段 7：拆每日生成主流程

分支：`refactor/split-daily-pipeline`

目标：最后移动风险最高的每日生成主流程，让 `main.py` 真正变成入口文件。

执行步骤：

1. 新建 `daily_pipeline.py`，移动：
   - `run_daily_brief`
   - `build_history_records`
   - `summarize_final_selection`
   - `detect_theme_changes`
   - `compact_source_fetch_status`
   - `compact_article_stats`
   - `should_attach_weekly_pdf_today`
   - `save_json`
2. `main.py` 保留：
   - `handler(event, context)`
   - `if __name__ == "__main__"`
   - 入口路由 import。
3. 保持 handler 判断顺序不变。
4. 移动后用 `rg` 检查旧函数是否还有残留定义或错误引用。

验证命令：

```powershell
python -m py_compile main.py daily_pipeline.py entrypoint_utils.py candidate_send_pipeline.py weekly_pipeline.py quality_pipeline.py
python -m py_compile config.py fetch_articles.py article_filter.py llm_client.py prompt_templates.py brief_schema.py email_renderer.py
```

回归检查：

```powershell
$env:RUN_MODE="test"; $env:TEST_LLM_MODEL="mock"; $env:SEND_EMAIL="false"; python main.py
```

验收标准：

- 夜间候选仍能生成候选件。
- 每日正文、HTML、纯文本仍生成。
- 质量门禁仍运行。
- 失败留档仍保存。
- 早晨发送仍只读取候选件。
- `main.py` 只保留入口和路由，不再承载业务主体。

## 阶段 8：最小自动化回归

分支：`test/add-minimal-regression-checks`

目标：建立低成本 CI，防止后续修改破坏入口安全和质量门禁。

执行步骤：

1. 新增 `.github/workflows/python-check.yml`。
2. CI 第一版只做：
   - checkout。
   - setup Python 3.10。
   - pip install requirements。
   - 编译所有根目录 `.py` 和 `scripts/*.py`。
3. 新增 `tests/fixtures/`：
   - `good_brief_minimal.json`
   - `bad_brief_truncated_sentence.json`
   - `bad_brief_module_overlap.json`
4. 新增测试：
   - `tests/test_event_routing.py`
   - `tests/test_quality_gate.py`
   - `tests/test_render_and_quality.py`
5. 测试先覆盖最关键红线，不追求覆盖所有生成逻辑。

建议 CI 编译命令：

```yaml
- name: Compile Python files
  run: |
    python - <<'PY'
    from pathlib import Path
    import py_compile
    for pattern in ("*.py", "scripts/*.py"):
        for path in Path(".").glob(pattern):
            py_compile.compile(str(path), doraise=True)
    PY
```

验收标准：

- GitHub Actions 通过。
- 普通 HTTP 不触发 `run_daily_brief` 有测试覆盖。
- `quality_gate.fail` 不发送有测试覆盖。
- 省略号/半截句等坏样例能被质量检查拦截。
- `morning_send` 缺候选 blocked 有测试覆盖。

## 阶段 9：legacy 清理

分支：`chore/remove-confirmed-legacy`

目标：只删除已确认无引用、无部署依赖的旧代码。

执行步骤：

1. 检查 `_legacy_handler_unused`：
   ```powershell
   rg "_legacy_handler_unused"
   ```
2. 确认阿里云 FC 入口只配置 `main.handler`。
3. 如果只有定义处引用，则删除 `_legacy_handler_unused`。
4. 清理 README、部署文档中旧触发器、旧包名、旧预览说明。
5. 不删除 mock、知识库、质量模块、周报 fallback。

验证命令：

```powershell
python -m py_compile main.py
$env:RUN_MODE="test"; $env:SEND_EMAIL="false"; $env:TEST_LLM_MODEL="mock"; python main.py
```

验收标准：

- 删除 legacy 不影响 FC 入口。
- 文档中不再出现冲突部署包名。
- 所有红线测试仍通过。

## 推荐执行顺序

1. 先做阶段 0 和阶段 1，因为它们能立即降低部署风险。
2. 再做阶段 2，因为它能减少后续拆文件时的重复修改量。
3. 阶段 3 到阶段 7 必须拆成多个 PR，不要合并成一个大 PR。
4. 阶段 8 建议在阶段 3 后就开始做一部分，至少先保护入口路由。
5. 阶段 9 必须最后做，且只删已确认无引用 legacy。

## 暂不建议做的事

- 不建议现在引入大型框架、任务队列或数据库抽象。
- 不建议为了“干净”删除质量模块。
- 不建议一次性把 `main.py` 拆成 8 个文件。
- 不建议在没有 CI 和 mock 回归前删除 `_legacy_handler_unused`。
- 不建议在未确认 FC PDF 生成版本前直接删除 `reportlab/`。

