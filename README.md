# 公考晨读邮件程序

AI Coding / Codex / Cursor 接手项目时，请先看 `AGENTS.md`；内容 Harness 文档索引见 `content_harness/00_index.md`。

知识库样例沉淀见 `knowledge/README.md`。每周至少新增 2 个反例和 1 个正例，用于持续完善 Prompt、质检和题型转换方法。
可用 `python scripts\check_knowledge_base.py` 检查本周沉淀数量。

周度质量复盘可运行：

```powershell
python scripts\weekly_quality_review.py --metrics output\harness_metrics.jsonl
```

脚本会输出 `weekly_harness_review_YYYY-WW.md` 和同名 JSON，汇总 P0/P1/P2、模块分布、重写成功率、P0 二次修复成功率、管理员报告和早晨发送成功率，并形成下一周 Harness 升级清单。

这是阿里云函数计算 FC 可部署版本。入口函数为：

```text
main.handler
```

## 部署打包

部署包统一命名为：

```text
function.zip
```

Windows 本地推荐执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_fc_package.ps1
```

Linux / WSL / Git Bash 可执行：

```bash
bash scripts/build_fc_package.sh
```

生成 `function.zip` 后上传到阿里云函数计算。详细步骤见 `docs/deploy_aliyun_fc.md`。

## 必填环境变量

```text
RUN_MODE=prod
DASHSCOPE_API_KEY=你的百炼 API Key
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=发件 QQ 邮箱
SMTP_PASSWORD=QQ 邮箱 SMTP 授权码
MAIL_FROM=发件 QQ 邮箱
RECIPIENTS=收件人1@qq.com,收件人2@qq.com
SEND_MODE=bcc
ATTACH_DAILY_PDF=false
HISTORY_STORAGE=local
OSS_ENDPOINT=
OSS_BUCKET=
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_OBJECT_KEY=gongkao-morning-mailer/sent_history.json
BLOCK_TITLES=
BLOCK_URLS=
QWEN_MODEL=qwen-plus-2025-07-14
```

多个收件人用英文逗号分隔。为兼容旧版，也支持 `SMTP_PASS` 和 `MAIL_TO`。

`SEND_MODE=bcc` 会隐藏其他收件人邮箱；`SEND_MODE=individual` 会逐个单独发送。

可选：如果代码根目录存在 `subscribers.csv`，会优先读取其中 `status=active` 的邮箱；如果读取失败或文件不存在，则回退到 `RECIPIENTS`。

`sent_history.json` 默认保存在 `OUTPUT_DIR/sent_history.json`，用于最近 30 天文章去重。阿里云 FC 的本地文件不保证长期稳定，后续如需稳定商业化，应迁移到 OSS 或数据库。

如需让历史去重跨 FC 冷启动稳定生效，把 `HISTORY_STORAGE` 改为 `oss`，并填写 `OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`、`OSS_OBJECT_KEY`。

`ATTACH_DAILY_PDF=false` 已预留 PDF/打印版开关，本版本不会默认添加附件。

## 夜间候选 + 早晨发送

本版本支持两段式发送，不需要早上重新生成正文：

- 晚上 10 点触发：`{"mode":"nightly_candidate"}`。程序会生成邮件、质检、必要时重写、执行 P0 门禁，然后保存候选件；不会给用户发送，也不会写入正式历史。
- 早上 8 点触发：`{"mode":"morning_send"}`。程序会读取当天候选件；只有 `quality_gate.overall=ok` 才会发送给用户，发送成功后再写入历史和归档。

夜间候选默认交付日期是第二天。例如 2026-05-07 22:00 运行，会保存 `2026-05-08` 的候选件。早上 8 点运行时默认读取当天候选件。

候选件默认保存在 `OUTPUT_DIR/candidates/`。如果阿里云 FC 存在跨实例读取需求，建议设置：

```text
CANDIDATE_STORAGE=oss
CANDIDATE_PREFIX=gongkao-morning-mailer/candidates
```

如需晚上 10 点自动把质检报告发给管理员，配置：

```text
ADMIN_REPORT_ENABLED=true
ADMIN_REPORT_SEND_EMAIL=true
ADMIN_REPORT_EMAILS=管理员1@qq.com,管理员2@qq.com
```

管理员报告只发给 `ADMIN_REPORT_EMAILS`，不会读取用户订阅表；报告正文包含 P0 门禁、各模块质检结果、重写情况和候选件路径，并附带 `latest_quality.json`。

如果夜间候选最终 P0 fail，程序会额外保存失败样本：

```text
OUTPUT_DIR/blocked_runs/交付日期/
  articles.json
  brief_initial.json
  brief_final.json
  quality_initial.json
  quality_final.json
  latest_quality.json
  rewrite_comparison.json
  run_meta.json
  latest_email.html
  latest_email.txt
```

管理员报告会显示“自动修复前后对比”，并附带 `rewrite_comparison.json`。

在进入失败留档前，程序会先做一次 P0 自动二次修复：只针对 P0 涉及的模块再次定点重写，并重新跑质检和 P0 门禁。若二次修复后仍然 fail，才进入失败留档和阻断发送。

## 统一总门禁

可以用 `scripts/validate_daily_brief.py` 对任意 `brief.json` 跑统一 Harness 门禁：

```powershell
python scripts\validate_daily_brief.py --input output\latest_brief.json --output output\validate_report.json
```

输出包含：

- `overall`: `pass` / `review` / `block`
- `p0_count` / `p1_count` / `p2_count`
- `modules`: 今日一题、框架图、今日可带走、速读考试价值、跨模块重复、考生表达质感、整封邮件清洁度的分模块报告
- `send_decision`: `allow` / `allow_after_rewrite` / `block`
- `rewrite_required_modules`: 建议重写模块

退出码：

- `0`: pass
- `1`: review
- `2`: block

如只想生成报告、不让 PowerShell 因 review/block 退出码中断，可加：

```powershell
python scripts\validate_daily_brief.py --input output\latest_brief.json --no-exit-code
```

## Harness 指标统计

程序会默认追加写入：

```text
OUTPUT_DIR/harness_metrics.jsonl
```

夜间候选会记录：

- 交付日期、运行模式、是否测试模式
- `quality_gate`、`p0_count`
- 触发重写的模块
- 是否尝试 P0 二次修复、二次修复是否成功
- 各模块分数和状态
- 速读考试价值、跨模块重复、考生表达质感等高价值质检结果
- 候选件是否保存
- 管理员报告是否发送
- 失败留档是否保存
- 文章来源数量和历史去重数量

早晨发送会记录：

- 候选件是否读取成功
- 阻断原因：候选缺失、日期不匹配、质量门禁失败等
- 发送成功/失败数量
- 历史写入和归档状态

可通过环境变量控制：

```text
HARNESS_METRICS_ENABLED=true
HARNESS_METRICS_FILE=harness_metrics.jsonl
```

如果某篇文章在内测中反复出现，可临时用 `BLOCK_TITLES` 或 `BLOCK_URLS` 手动屏蔽；多个标题或链接用英文分号分隔。

## 本地测试

不调用大模型、不发邮件，只检查渲染：

```powershell
$env:RUN_MODE="test"
$env:SEND_EMAIL="false"
python main.py
```

输出会写入 `OUTPUT_DIR`，默认本地或 FC 的 `/tmp/gongkao-morning-mailer`。

## 阿里云 FC 配置

1. 运行环境选 Python 3.10。
2. 请求处理程序填写 `main.handler`。
3. 上传 `function.zip`。
4. 在“环境变量”里填写 `.env.example` 对应变量，不要把密钥写进代码。
5. 创建定时触发器，每天 08:00，北京时间。

## 说明

程序流程是：抓取人民日报/新华社候选文章 -> 规则筛选 -> 调用百炼兼容接口生成 JSON -> 校验 JSON -> 渲染 HTML 邮件 -> SMTP 发送。

大模型只生成 JSON，不直接生成 HTML，避免邮件样式失控。
