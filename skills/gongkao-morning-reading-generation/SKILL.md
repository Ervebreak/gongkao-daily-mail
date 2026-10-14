---
name: gongkao-morning-reading-generation
description: Generate a complete, structured daily public-service-exam morning-reading email from authoritative articles. Use when creating a new daily candidate; do not use for final review, sending, subscription operations, or weekly PDF generation.
---

# 公考晨读邮件生成

生成一份可供渲染和审核的“每日晨读候选件”，把权威文章转化为申论、面试和考编可用的学习内容。

本技能只负责生成，不负责发送，也不替代独立的“公考晨读邮件审核”技能。生成后必须交由审核链路复检；审核未通过时，按问题定位重选文章或定点重写，不得绕过门禁。

## 开始前

在本项目中执行时，先读取：

- `content_harness/gongkao_morning_reading_production_standard.md`：唯一有效的生产与发布口径。
- `references/generation-contract.md`：本技能的输入、输出与边界。
- 只有在需要做具体内容决策时，再读取 `references/generation-rules.md`。

若输入文章缺少可信来源、发布时间、原始链接或足够完整的正文，停止生成并要求补齐或重新选文。

## 工作方式

1. 先筛选并确定 1 篇主文与至多 2 篇不重复的速读；主文不达最低标准时重新选择。
2. 忠实拆解主文，再把其具体场景、问题、机制转化为可迁移考点；不要先套考试模板再回填原文。
3. 生成结构化候选件：主文分析、原文结构图、考场转化、今日一题、今日可带走、速读及简版必要字段。
4. 统稿，确保各模块有唯一职责，不重复堆砌同一判断、比喻或对策。
5. 将候选件交给独立审核技能/项目质量门禁；若收到问题清单，只修复受影响字段，并重跑关联渲染与检查。

## 必守边界

- 不编造原文未提供的事实、数据、部门、文件、法律或权威表述。
- 政策坐标没有高度匹配且可核验的来源时，省略该模块。
- 情景实务题必须具备身份、场景、权限和任务；纯申论分析题不强制身份，但必须有明确对象、现象/矛盾和任务。
- 答题框架为 3—4 点，每点不超过 45 字；参考答案采用移动端短段。
- “今日可带走”固定为关键词、常识点、两句表达、方法框架。
- 产出仅为候选内容或可渲染 JSON；不得发送邮件、修改订阅者、写入发送历史或把审核告警降级。

## 交接

输出时明确：

- 主文与速读的来源及选择理由；
- 生成候选件；
- 需由审核技能核验的项目：事实与政策出处、题型/权限、断句、字段泄漏、重复、最终 HTML/纯文本/简版同步。

不要把质量卡或内部修复说明写进用户可见正文。


## 按需加载的细则

- 选择主文或速读时，读 `references/article-selection.md`。
- 从文章拆结构、提炼考点时，读 `references/article-to-exam.md`。
- 写各个邮件模块、CTA 或统稿时，读 `references/module-composition.md`。
- 对候选 JSON 做确定性校验、局部修复和回退时，读 `references/validation-and-repair.md` 并运行 `scripts/validate_candidate_contract.py`。

该脚本是生成前的辅助校验，不替代本项目的 `scripts/validate_daily_brief.py` 或独立审核技能。
