# 阿里云函数计算部署说明

本文档记录当前公考晨读邮件项目的标准部署流程。部署、依赖或打包逻辑变更时，应同步更新 `README.md`、`content_harness/deployment_rules.md` 和 `CHANGELOG_HARNESS.md`。

## 1. 拉取最新代码

在本地仓库执行：

```powershell
git pull origin main
```

如果正在做功能分支，先确认当前分支和未提交变更：

```powershell
git status --short
git branch --show-current
```

## 2. 本地基础检查

打包前至少执行：

```powershell
python -m py_compile main.py config.py scripts\validate_daily_brief.py
python -m py_compile weekly_report.py weekly_typst_export.py
python -c "from bs4 import BeautifulSoup; import requests; import reportlab; print('core deps ok')"
```

如启用 OSS 或其他可选能力，再按 `content_harness/deployment_rules.md` 执行额外依赖检查。

## 3. 生成部署包

部署包统一命名为：

```text
function.zip
```

Windows 本地推荐使用 PowerShell 脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_fc_package.ps1
```

如需显式指定输出路径：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_fc_package.ps1 -OutputZip .\function.zip
```

Linux / WSL / Git Bash 可使用 Bash 脚本：

```bash
bash scripts/build_fc_package.sh
```

注意：Bash 脚本依赖 `rsync` 和 `zip`。如果 Windows Git Bash 缺少这些命令，优先使用 PowerShell 脚本、WSL 或 GitHub Actions。

## 4. 上传阿里云 FC

阿里云函数计算配置：

- 运行环境：Python 3.10
- 请求处理程序：`main.handler`
- 部署包：上传仓库根目录生成的 `function.zip`
- 环境变量：在 FC 控制台配置，不要写进代码或提交到 GitHub

必要环境变量以 `.env.example` 为准，常用关键项包括：

```text
RUN_MODE=prod
DASHSCOPE_API_KEY=
SMTP_HOST=
SMTP_PORT=465
SMTP_USER=
SMTP_PASSWORD=
MAIL_FROM=
RECIPIENTS=
SEND_MODE=bcc
SEND_EMAIL=true
```

真实密钥、授权码、真实用户邮箱、发送历史和归档产物不得提交到 GitHub。

## 5. 触发器配置

当前推荐两段式交付：

- 夜间候选：每天 22:00，北京时间，事件 `{"mode":"nightly_candidate"}`
- 早晨发送：每天 08:00，北京时间，事件 `{"mode":"morning_send"}`

早晨发送链路只能读取候选件。候选件缺失、日期不匹配或 `quality_gate.overall != "ok"` 时必须阻断发送，不能临时生成并正式发送。

## 6. 发布后验证

FC 上传后先执行测试事件，不要直接依赖正式触发器。

建议先测夜间候选：

```json
{"mode":"nightly_candidate"}
```

确认候选件、`latest_quality.json` 和管理员报告逻辑正常后，再测早晨发送：

```json
{"mode":"morning_send"}
```

如需本地 dry run：

```powershell
$env:RUN_MODE="test"
$env:TEST_LLM_MODEL="mock"
$env:SEND_EMAIL="false"
python main.py
```

## 7. 发布包不得包含

- `.git/`
- `__pycache__/`
- `*.pyc`
- `.pytest_cache/`
- `subscribers.csv`
- `sent_history/`
- `archive/`
- `output/`
- `logs/`
- `tmp/`
- 旧 zip、PDF、Excel、本地调试产物

## 8. 回滚

阶段 1 只涉及部署文档、依赖锁定和打包输出名，不修改主流程逻辑。如发布包异常，优先回退本次 PR，并恢复上一版已验证部署包。
