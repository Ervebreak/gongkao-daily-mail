"""本地运行入口：python -m agent.run_local --date 2026-09-16 [--test]

用法：
  python -m agent.run_local --date 2026-09-16 --test
    （test 模式：TEST_LLM_MODEL=mock 时用确定性 Planner，不调用模型）
  python -m agent.run_local --date 2026-09-16
    （生产模式：需要 DASHSCOPE_API_KEY 等环境变量）

输出：状态机推进结果；候选通过门禁后保存到正式候选存储（OSS/本地），
发送预览邮件到 SMTP_USER，进入 PUBLISHED（次日早晨由现有发送链路自动发送）。
"""
from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="公考晨读 Agent 本地运行入口")
    parser.add_argument("--date", required=True, help="投递日期 YYYY-MM-DD")
    parser.add_argument("--test", action="store_true", help="test 模式（mock 模型则走确定性策略）")
    parser.add_argument("--cancel", action="store_true", help="模拟管理员点击取消次日发送（仅测试用）")
    args = parser.parse_args()

    from agent.orchestrator import run

    result = run(args.date, test_mode=args.test)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.cancel and result.get("status") == "published":
        from agent.confirm import handle_confirm
        from agent.state import load_run

        state = load_run(args.date)
        page = handle_confirm(
            {
                "path": "/agent-confirm",
                "query": {
                    "date": args.date,
                    "action": "cancel",
                    "token": state.confirm_token if state else "",
                },
            }
        )
        print("=== cancel result ===")
        print(json.dumps(page, ensure_ascii=False, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
