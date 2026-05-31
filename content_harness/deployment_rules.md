# Deployment Rules

本文件沉淀 2026-05 内测中的部署依赖问题。凡打包、上传阿里云 FC、修改依赖或发布 zip，应先读本文件。

## 1. 部署前依赖自检

每次发布 zip 前，必须至少执行：

```powershell
python -m py_compile main.py config.py scripts\validate_daily_brief.py
python -c "from bs4 import BeautifulSoup; import requests; print('core deps ok')"
```

如启用 OSS、DashScope 或其他可选能力，还应检查：

```powershell
python -c "import oss2; print('oss2 ok')"
python -c "import dashscope; print('dashscope ok')"
```

## 2. 发布包检查

Windows 本地打包推荐直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_fc_package.ps1
```

默认输出：

```text
function.zip
```

该脚本会安装阿里云 FC Python 3.10 Linux x86_64 兼容依赖，并自动检查入口文件、题库兜底 CSV、Windows `.pyd`、`__pycache__` / `.pyc`。

发布包不得包含：

- `__pycache__`
- `.pytest_cache`
- 本地输出目录
- 临时坏样例
- 密钥、授权码、真实邮箱凭证

发布包必须包含：

- `requirements.txt`
- `content_harness/`
- `knowledge/`
- `knowledge_base/`
- 运行入口 `main.py`
- 质检入口 `scripts/validate_daily_brief.py`
- 如启用题库轻接入，必须包含 `question_bank.py`
- 如使用本地兜底题库，必须包含 `data/question_bank/shenlun_question_bank_v3_a.csv`
- 如启用本地知识库，必须包含 `knowledge_base/policy_corpus/policy_statements_core.jsonl` 和 `knowledge_base/topic_knowledge/article_index.jsonl`

## 3. 典型 P0

`ModuleNotFoundError: No module named bs4` 属于部署阻断级问题，不是内容问题。处理方式：

1. 先补依赖和打包链路。
2. 本地跑依赖导入自检。
3. 重新打包 zip。
4. 再触发 FC 测试。

不能通过关闭抓取、绕过质检或临时改发送逻辑来规避依赖错误。

## 4. 题库接入部署检查

题库接入相关环境变量：

```text
QUESTION_BANK_ENABLED=true
QUESTION_BANK_SOURCE=local|oss
QUESTION_BANK_LOCAL_PATH=data/question_bank/shenlun_question_bank_v3_a.csv
QUESTION_BANK_OSS_KEY=question_bank/shenlun_question_bank_v3_a.csv
QUESTION_BANK_MATCH_LIMIT=3
QUESTION_BANK_RECENT_DAYS_DEDUP=7
QUESTION_BANK_FAIL_OPEN=true
```

线上使用 OSS 时：

1. 不需要新建 bucket；
2. 使用现有 `OSS_BUCKET`；
3. `QUESTION_BANK_OSS_KEY` 是 bucket 内对象路径；
4. 上传位置应与环境变量完全一致。

发布前至少验证：

```powershell
python -m py_compile config.py question_bank.py prompt_templates.py llm_client.py question_quality.py main.py
python -c "from question_bank import load_shenlun_question_bank; rows, meta=load_shenlun_question_bank(); print(len(rows), meta)"
```

打包检查：

- zip 内不得含 `*.pyc` 或 `__pycache__`；
- zip 内应能看到 `question_bank.py`；
- zip 内应能看到本地兜底 CSV；
- 若 OSS 题库缺失，程序仍应生成候选邮件。

## 5. 知识库目录配置

政策原文语库和《求是》专题知识库相关环境变量：

```text
KNOWLEDGE_BASE_MODE=local
KNOWLEDGE_BASE_DIR=knowledge_base
KNOWLEDGE_OSS_PREFIX=
```

当前阶段只接入目录、配置和打包资产，不接入每日 JSON 生成、HTML 渲染、发送逻辑或质量门禁。

线上第一版默认使用本地知识库：

1. `KNOWLEDGE_BASE_MODE=local`；
2. `KNOWLEDGE_BASE_DIR=knowledge_base`；
3. 发布包内应包含 `knowledge_base/policy_corpus/` 和 `knowledge_base/topic_knowledge/`。

后续切换 OSS 时：

1. 将 `KNOWLEDGE_BASE_MODE` 改为 `oss`；
2. 将 `KNOWLEDGE_OSS_PREFIX` 设置为 bucket 内知识库对象前缀；
3. 继续复用现有 `OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`。
