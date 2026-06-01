# Stage 4 质量修复闭环计划

第四阶段目标：把质检、字段级修复、模块重写、重渲染、最终复检和门禁展示串成稳定闭环。

## 核心链路

1. 质检发现问题。
2. 字段级修复或模块重写。
3. 写回 brief。
4. 重新渲染 plain_text 和 html_body。
5. 对最终 plain_text/html_body 做复检。
6. quality_gate、quality.final、quality_card_markdown 只展示最终状态。

## 修复重点

- 避免 brief 修了但 plain_text/html_body 没同步。
- 避免 quality_gate、quality.gate、quality.final 出现状态不一致。
- 避免 quality_card_markdown 展示 initial 或 before 的旧问题。
- 避免自动修复后没有二次复检。

## 不改范围

- 不改发送时间和发送模式。
- 不改模型配置。
- 不绕过门禁。
- 不做大范围重构。
