# 技能内容审核与程序门禁

公考晨读生成审核技能由当前对话模型完成语义审核，不需要再请求 Qwen API。
这是显式的审核提供者选择，不是关闭审稿。程序自主生成/发送流程默认仍使用原 API 审稿，未经迁移不会自动信任候选中的审核标记。

## 执行

1. 按 schema 规范化最终 brief，运行清洁度处理，重新渲染 plain/Full/Lite。
2. 技能阅读完整原文、最终 brief 和 Full/Lite 后，写实际审核记录 `skill_content_review_YYYY-MM-DD.json`。不得生成固定分数或预设 PASS；测试 fixture 不能用作生产记录。
3. 用 `skill_content_review.review_binding(brief)` 获取最终指纹，将其写入记录。指纹工具只绑定版本，不生成审稿结论，也不能证明审稿真实完成。
4. 运行：

```bash
python scripts/validate_daily_brief.py --input candidate.json --skill-review skill_content_review_YYYY-MM-DD.json --output repo_gate_report.json
```

此路径没有额外模型请求，也不会在记录缺失/无效时回退调用 API。默认不传 `--skill-review` 的行为不变。

构建 canonical candidate 时，用同一记录执行 `evaluate_all_quality(..., content_review_mode="skill", skill_review=review)`，从真实结果构建 quality 和 gate；不能运行 API 后覆盖其失败结果。统一验证仅生成报告，不自动修改输入 candidate。候选和报告的 quality/fact-review 必须同步，且所有正式 artifact 必须从最终 brief 重新派生。

## 审核记录合同

- `schema_version`: 1；`review_origin`: `skill`；`delivery_date`: 与 brief.date 一致。
- `reviewer`: `name` 和实际 `model`；`reviewed_at`: 带时区的实际审稿时间。
- `binding`: `review_binding()` 返回的完整字典，绑定 source_set_hash、candidate_fact_hash、candidate_content_hash、plain_text_hash、full_html_hash、lite_payload_hash。
- `dimension_reviews`: 八维，每维提供整数 `score` 和具体 `reason`：topic_fit 20、user_safety 15、exam_value 20、source_alignment 15、information_gain 10、naturalness 10、module_coherence 5、cleanliness 5。
- `overall_score`: 八项明细之和；`risk_level`: low/medium/high；`one_sentence_judgment`: 实际结论。
- `section_checks`: source_facts、selection、modules、full、lite、cta。每项有 `status`（pass/review/block）和具体 `reason`。
- `issues`: 实际问题列表，每项至少有 severity（high/medium/low）、code、message；没有问题才用空列表。

证据未 verified、记录缺失、日期/版本不符、评分依据不全、保存的正文不等于当前渲染结果，均阻断。低分沿用原审稿阈值；高风险、Lite 泄漏仍阻断；必须修复的问题仍返回 review/block。最终 PASS 要求统一报告 pass、P0=0、必须修复 P1=0、Skill 硬门禁通过。

审核记录保留在 `quality.content_quality.skill_audit`，不得渲染到邮件正文。修改正文、原文证据或渲染结果后必须重审。记录是受信技能的审计输入，不是密码学签名；不得让程序凭哈希自动宣称内容正确。

## 发布边界

Publisher 和 OSS 写入流程不变：仅在全部门禁通过、fact review 绑定当前、候选冻结后调用 publishDailyCandidate；确认 dated/latest 双写成功。没有新增 FC 函数，没有 SMTP 或订阅表操作。
