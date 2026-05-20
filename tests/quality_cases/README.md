# Quality Regression Cases

本目录保存内容风险质检与字段级小修的固定回归样本。

运行方式：

```powershell
python scripts\run_quality_regression.py
```

样本约定：

- `expected_issue_codes`：必须命中的问题 code。
- `unexpected_issue_codes`：不得误报的问题 code。
- `expect_changed`：字段级小修是否应该改动 brief。
- `fixed_must_contain`：小修后的 brief 必须包含的文本。
- `fixed_must_not_contain`：小修后的 brief 不得继续包含的文本。

新增质量规则时，优先同时补充一个坏样本和一个不应误杀的好样本。
