from __future__ import annotations

import unittest

from email_sender import build_recipient_delivery_plan


class RecipientTieringTests(unittest.TestCase):
    def test_paid_until_not_expired_gets_full(self) -> None:
        plan = build_recipient_delivery_plan(
            [{"email": "paid@example.com", "status": "active", "plan": "paid_trial", "paid_until": "2026-06-30"}],
            recipient_source="test",
            delivery_date="2026-06-07",
        )
        self.assertEqual(plan["full_emails"], ["paid@example.com"])

    def test_expired_paid_until_falls_back_to_lite(self) -> None:
        plan = build_recipient_delivery_plan(
            [{"email": "expired@example.com", "status": "active", "plan": "paid_monthly", "paid_until": "2026-06-06"}],
            recipient_source="test",
            delivery_date="2026-06-07",
        )
        self.assertEqual(plan["lite_emails"], ["expired@example.com"])

    def test_free_user_gets_lite(self) -> None:
        plan = build_recipient_delivery_plan(
            [{"email": "free@example.com", "status": "active", "plan": "free"}],
            recipient_source="test",
            delivery_date="2026-06-07",
        )
        self.assertEqual(plan["lite_emails"], ["free@example.com"])

    def test_unsubscribed_user_is_skipped(self) -> None:
        plan = build_recipient_delivery_plan(
            [{"email": "stop@example.com", "status": "unsubscribed", "plan": "paid_trial", "paid_until": "2026-06-30"}],
            recipient_source="test",
            delivery_date="2026-06-07",
        )
        self.assertEqual(plan["skipped_emails"], ["stop@example.com"])

    def test_missing_new_fields_defaults_to_lite(self) -> None:
        plan = build_recipient_delivery_plan(
            [{"email": "legacy@example.com"}],
            recipient_source="test",
            delivery_date="2026-06-07",
        )
        self.assertEqual(plan["lite_emails"], ["legacy@example.com"])


if __name__ == "__main__":
    unittest.main()
