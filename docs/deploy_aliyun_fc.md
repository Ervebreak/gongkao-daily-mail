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

## 9. Render 新加坡：30 秒申论表达教练（推荐）

当前阿里云事件函数默认公网地址会对自定义 HTTP 响应强制添加
`Content-Disposition: attachment`，浏览器会下载 `.customization` 文件，
因此正式训练网页改由 Render 新加坡 Web Service 承载。香港 FC 可以保留用于后端对照测试，
但不要把它的默认 `fcapp.run` 地址写入正式邮件。

仓库已经提供：

- `render_practice.py`：WSGI Web 入口；
- `requirements-render.txt`：Render 独立依赖；
- `render.yaml`：新加坡 Blueprint 配置，不包含真实密钥。

在 Render 创建 Blueprint，或手动创建 Web Service：

```text
Region: Singapore
Runtime: Python
Build Command: pip install -r requirements-render.txt
Start Command: gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 render_practice:app
Health Check Path: /healthz
```

Render 环境变量沿用下方训练变量。初次部署保持 `PRACTICE_COACH_MODE=mock`；
`/healthz` 和完整两次提交验收通过后再切换为 `api`。Render 会提供可直接浏览的
`onrender.com` HTTPS 地址，该地址填写到邮件主函数的 `PRACTICE_BASE_URL`。
Blueprint 默认 `plan: free` 只用于验收。Free Web Service 空闲后会休眠，正式邮件开放前
应切换为不会休眠的实例方案，否则当天第一位用户可能遇到明显冷启动等待。

## 10. 香港 FC 训练入口（仅保留测试）

训练页必须部署为独立“事件函数 + HTTP 触发器”，不与定时发送入口共用 handler：

- 地域：香港；
- 函数类型：事件函数；不要选择要求启动命令和监听端口的 Web 函数；
- 运行环境：Python 3.10；
- 部署包：与邮件函数相同的 `function.zip`；
- 请求处理程序：`fc_practice.handler`；
- 触发器：HTTP，开放 `GET` 和 `POST`；
- 超时：建议不少于 90 秒，覆盖模型接口的最坏响应时间；
- 公网地址：优先先用 FC 提供的 HTTPS 地址验收，不要求先绑定自有域名。

训练函数的必要环境变量：

```text
RUN_MODE=prod
CANDIDATE_STORAGE=oss
CANDIDATE_PREFIX=gongkao-morning-mailer/candidates
OSS_ENDPOINT=<Render 和香港函数均可访问的 OSS 公网 endpoint>
OSS_BUCKET=
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
PRACTICE_LINK_SECRET=<至少 32 字节高熵随机值>
PRACTICE_MAX_REVIEWS=2
PRACTICE_COACH_MODE=mock
PRACTICE_COACH_MODEL=qwen-plus
PRACTICE_COACH_TIMEOUT=60
PRACTICE_OSS_PREFIX=gongkao-morning-mailer/practice
```

如希望练习记录使用不同 bucket 或不同最小权限账号，可设置
`PRACTICE_OSS_ENDPOINT`、`PRACTICE_OSS_BUCKET`、
`PRACTICE_OSS_ACCESS_KEY_ID`、`PRACTICE_OSS_ACCESS_KEY_SECRET`；未设置时复用 `OSS_*`。
练习记录 bucket 必须处于“未开启版本控制”状态。阿里云 OSS 在 bucket 已开启或已暂停
版本控制时会忽略 `x-oss-forbid-overwrite`，无法保证两个并发请求只占用一个 slot；
如果现有候选 bucket 使用版本控制，必须为练习记录配置独立 bucket。

早晨发送函数需要同步设置：

```text
PRACTICE_ENABLED=true
PRACTICE_BASE_URL=<Render onrender.com HTTPS 地址，不带末尾斜杠>
PRACTICE_LINK_SECRET=<与 Render 服务完全相同>
PRACTICE_LINK_DAYS=7
```

Render 正式上线顺序：

1. 将包含 Render 入口的代码分支合并并推送到 GitHub，部署新加坡 Render Web Service。
2. 保持 `PRACTICE_COACH_MODE=mock` 配置 Render 服务。
3. 请求 `GET /healthz`，确认返回 `status=ok`。
4. 用测试订阅者执行一次测试晨发，点击专属链接，连续提交两次并确认 OSS 出现两个 slot 对象。
5. 确认第三次提交在调用模型前被拒绝，篡改链接或过期链接返回 403。
6. 设置 `PRACTICE_COACH_MODE=api` 和 `DASHSCOPE_API_KEY`，重新部署并做一次真实点评测试。
7. 最后保持早晨函数 `PRACTICE_ENABLED=true`；如需快速回滚，只需把该值改为 `false`，邮件正文和候选件不受影响。

练习记录对象按日期、题目版本和匿名用户哈希分目录，每次成功评价占用一个不可覆盖的 slot。
写入使用并正确签名 `x-oss-forbid-overwrite: true`，同名 slot 已存在时 OSS 返回 409，
避免两个 FC 实例并发覆盖同一次数。对象键和对象内容均不保存邮箱或原始 `uid`。
邮件候选件仍保持原有确定性渲染结果；CTA 只在早晨发送层注入并逐人签名。
