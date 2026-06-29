# Regression Cases

这个目录保存已经发生过的高频历史问题最小样例。

目录约定：

- 每个一级目录对应 1 类历史问题。
- 每类先放 1 个最小样例。
- 样例至少包含 `input.json`、`expected.json`、`README.md`。

运行方式：

```powershell
python scripts\run_regression_cases.py
```

当前覆盖：

- `half_sentence`
- `label_leak`
- `policy_weak_match`
- `lite_cta_salesy`
- `weekly_pdf_path_error`
- `internal_trace_leak`
- `daily_question_mismatch`
