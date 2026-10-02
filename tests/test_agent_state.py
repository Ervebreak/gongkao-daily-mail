"""Agent 单元测试：状态机、结构化输出、确认 token。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.schemas import parse_decision, parse_issue
from agent.state import (
    IllegalTransitionError,
    RunState,
    STATE_AUDITING,
    STATE_BLOCKED,
    STATE_CREATED,
    STATE_SEARCHING,
    STATE_SENT,
    assert_transition,
    default_run_dir,
    load_run,
    save_run,
)
from agent.confirm import build_confirm_token, verify_confirm_token


class TestParseDecision(unittest.TestCase):
    def test_normal(self):
        d = parse_decision(
            {
                "decision": "REPAIR",
                "next_tool": "repair_candidate",
                "arguments": {"delivery_date": "2026-09-16"},
                "reason": "框架图不够清晰",
                "issues": [{"module": "framework_map", "severity": "P1", "reason": "结构不完整"}],
            }
        )
        self.assertEqual(d.decision, "REPAIR")
        self.assertEqual(d.next_tool, "repair_candidate")
        self.assertEqual(d.arguments["delivery_date"], "2026-09-16")
        self.assertEqual(d.issues[0].module, "framework_map")
        self.assertEqual(d.issues[0].severity, "P1")

    def test_invalid_decision_blocks(self):
        """模型输出非法决策时，禁止发明状态，回退为 BLOCKED。"""
        d = parse_decision({"decision": "SEND_NOW_WITHOUT_APPROVAL"})
        self.assertEqual(d.decision, "BLOCKED")

    def test_missing_fields_defaults(self):
        self.assertEqual(parse_decision(None).decision, "BLOCKED")
        self.assertEqual(parse_decision({}).decision, "BLOCKED")
        self.assertEqual(parse_decision({"decision": "pass"}).decision, "PASS")

    def test_issue_severity_normalized(self):
        self.assertEqual(parse_issue({"severity": "p0"}).severity, "P0")
        self.assertEqual(parse_issue({"severity": "HIGH"}).severity, "P2")
        self.assertEqual(parse_issue("纯文本问题").reason, "纯文本问题")


class TestStateMachine(unittest.TestCase):
    def test_transition_valid_path(self):
        assert_transition(STATE_CREATED, STATE_SEARCHING)
        assert_transition(STATE_AUDITING, STATE_BLOCKED)

    def test_transition_invalid_path_raises(self):
        with self.assertRaises(IllegalTransitionError):
            assert_transition(STATE_CREATED, STATE_SENT)
        with self.assertRaises(IllegalTransitionError):
            assert_transition(STATE_SENT, STATE_CREATED)

    def test_run_state_roundtrip(self):
        state = RunState(run_id="2026-09-16-agent-v1", delivery_date="2026-09-16")
        state.transition(STATE_SEARCHING, note="start")
        state.repair_round = 1
        state.selected_article_ids = [0, 1, 2]
        restored = RunState.from_dict(state.to_dict())
        self.assertEqual(restored.delivery_date, "2026-09-16")
        self.assertEqual(restored.state, STATE_SEARCHING)
        self.assertEqual(restored.repair_round, 1)
        self.assertEqual(restored.selected_article_ids, [0, 1, 2])
        self.assertEqual(len(restored.history), 1)

    def test_state_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = default_run_dir

            def fake_run_dir():
                return Path(tmp)

            import agent.state as state_module

            state_module.default_run_dir = fake_run_dir
            try:
                st = RunState(run_id="r1", delivery_date="2026-09-16")
                st.transition(STATE_SEARCHING)
                save_run(st)
                loaded = load_run("2026-09-16")
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded.state, STATE_SEARCHING)
            finally:
                state_module.default_run_dir = original


class TestConfirmToken(unittest.TestCase):
    def test_roundtrip(self):
        import os

        os.environ["AGENT_CONFIRM_SECRET"] = "test-secret"
        try:
            token = build_confirm_token("2026-09-16", "cancel")
            self.assertTrue(verify_confirm_token("2026-09-16", "cancel", token))
            self.assertFalse(verify_confirm_token("2026-09-16", "cancel", "wrong"))
            self.assertFalse(verify_confirm_token("2026-09-16", "approve", token))
        finally:
            os.environ.pop("AGENT_CONFIRM_SECRET", None)

    def test_requires_secret(self):
        import os

        os.environ.pop("AGENT_CONFIRM_SECRET", None)
        with self.assertRaises(RuntimeError):
            build_confirm_token("2026-09-16", "cancel")


if __name__ == "__main__":
    unittest.main()
