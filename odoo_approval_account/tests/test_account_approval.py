# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install", "approval")
class TestAccountApproval(AccountTestInvoicingCommon):
    """account.move integration: high-value invoices need approval before post."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["approval.engine.rule"].sudo().search(
            [("model_name", "=", "account.move")]
        ).write({"active": False})

        cls.group = cls.env.ref("base.group_user")
        cls.approver = cls.env["res.users"].create({
            "name": "Invoice Approver",
            "login": "invoice_approver_test@example.com",
            "group_ids": [(4, cls.group.id)],
        })
        cls.rule = cls.env["approval.engine.rule"].sudo().create({
            "name": "Test Invoice High Value",
            "sequence": 1,
            "model_id": cls.env["ir.model"]._get("account.move").id,
            "trigger_event": "on_post",
            "condition_python":
                "record.move_type == 'out_invoice' and record.amount_total > 5000",
            "level_ids": [(0, 0, {
                "sequence": 1, "name": "Accounting Manager",
                "approver_type": "group", "approver_group_id": cls.group.id,
                "min_approvals": 1,
            })],
        })

    def test_high_value_invoice_blocked_then_posted(self):
        inv = self.init_invoice(
            "out_invoice", partner=self.partner_a, amounts=[8000]
        )
        inv.action_post()
        self.assertNotEqual(inv.state, "posted",
                            "High-value invoice must wait for approval.")
        req = self.env["approval.engine.request"].search([
            ("res_model", "=", "account.move"), ("res_id", "=", inv.id),
            ("state", "=", "pending"),
        ], limit=1)
        self.assertTrue(req)
        line = req.line_ids.filtered(lambda l: l.decision == "pending")[:1]
        line.with_user(self.approver).action_quick_approve()
        self.assertEqual(req.state, "approved")
        self.assertEqual(inv.state, "posted")

    def _pending_request(self, move):
        return self.env["approval.engine.request"].search([
            ("res_model", "=", "account.move"), ("res_id", "=", move.id),
            ("state", "=", "pending"),
        ])

    def test_post_entries_action_does_not_bypass_approval(self):
        """The "Post entries" list action (validate.account.move) posts through
        _post(): it must hold high-value invoices and post the others."""
        big = self.init_invoice("out_invoice", partner=self.partner_a, amounts=[8000])
        small = self.init_invoice("out_invoice", partner=self.partner_a, amounts=[100])
        wizard = self.env["validate.account.move"].with_context(
            active_model="account.move", active_ids=(big | small).ids,
        ).create({})
        wizard.validate_move()
        self.assertEqual(big.state, "draft", "High-value invoice must wait for approval.")
        self.assertTrue(self._pending_request(big))
        self.assertEqual(small.state, "posted")

    def test_autopost_cron_does_not_bypass_approval(self):
        """Auto-posted invoices are held too, leave the auto-post queue (so the
        cron does not pick them up again) and are posted once approved."""
        today = fields.Date.context_today(self.env["account.move"])
        big = self.init_invoice("out_invoice", partner=self.partner_a, amounts=[8000],
                                invoice_date=today)
        small = self.init_invoice("out_invoice", partner=self.partner_a, amounts=[100],
                                  invoice_date=today)
        (big | small).write({"auto_post": "at_date", "date": today})

        # Outside a real cron run _commit_progress commits; not allowed in tests.
        with patch.object(type(self.env["ir.cron"]), "_commit_progress",
                          lambda self, *args, **kwargs: float("inf")):
            self.env["account.move"]._autopost_draft_entries()

        self.assertEqual(small.state, "posted")
        self.assertEqual(big.state, "draft")
        self.assertEqual(big.auto_post, "no")
        request = self._pending_request(big)
        self.assertTrue(request)

        request.line_ids.with_user(self.approver).action_quick_approve()
        self.assertEqual(big.state, "posted")

    def test_low_value_invoice_posts_directly(self):
        inv = self.init_invoice(
            "out_invoice", partner=self.partner_a, amounts=[100]
        )
        inv.action_post()
        self.assertEqual(inv.state, "posted")
        self.assertFalse(self.env["approval.engine.request"].search([
            ("res_model", "=", "account.move"), ("res_id", "=", inv.id),
        ]))
