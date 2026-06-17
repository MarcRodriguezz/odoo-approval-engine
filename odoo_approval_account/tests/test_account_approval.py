# -*- coding: utf-8 -*-
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
        req._register_decision(line, "approved")
        self.assertEqual(req.state, "approved")
        self.assertEqual(inv.state, "posted")

    def test_low_value_invoice_posts_directly(self):
        inv = self.init_invoice(
            "out_invoice", partner=self.partner_a, amounts=[100]
        )
        inv.action_post()
        self.assertEqual(inv.state, "posted")
        self.assertFalse(self.env["approval.engine.request"].search([
            ("res_model", "=", "account.move"), ("res_id", "=", inv.id),
        ]))
