# -*- coding: utf-8 -*-
from odoo.addons.hr_expense.tests.common import TestExpenseCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install", "approval")
class TestExpenseApproval(TestExpenseCommon):
    """hr.expense integration: high-value expenses need approval to be submitted."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["approval.engine.rule"].sudo().search(
            [("model_name", "=", "hr.expense")]
        ).write({"active": False})

        # Dedicated approver group (exactly one approver => one line).
        cls.appr_group = cls.env["res.groups"].create({"name": "Expense Approvers Test"})
        cls.appr_user = cls.env["res.users"].create({
            "name": "Expense Approver",
            "login": "expense_approver_test@example.com",
            "group_ids": [(4, cls.appr_group.id), (4, cls.env.ref("base.group_user").id)],
        })
        cls.rule = cls.env["approval.engine.rule"].sudo().create({
            "name": "Test Expense High Value",
            "sequence": 1,
            "model_id": cls.env["ir.model"]._get("hr.expense").id,
            "trigger_event": "on_submit",
            "condition_python": "record.total_amount_currency > 1000",
            "level_ids": [(0, 0, {
                "sequence": 1, "name": "Expense Approver",
                "approver_type": "group", "approver_group_id": cls.appr_group.id,
                "min_approvals": 1,
            })],
        })

    def test_high_value_expense_blocked_then_submitted(self):
        expense = self.create_expenses({"total_amount_currency": 2000.0})
        expense.action_submit()
        self.assertNotEqual(expense.state, "submitted",
                            "High-value expense must wait for approval.")
        req = self.env["approval.engine.request"].search([
            ("res_model", "=", "hr.expense"), ("res_id", "=", expense.id),
            ("state", "=", "pending"),
        ], limit=1)
        self.assertTrue(req)

        line = req.line_ids.filtered(lambda l: l.decision == "pending")[:1]
        self.assertTrue(line)
        req._register_decision(line, "approved")
        self.assertEqual(req.state, "approved")
        self.assertEqual(expense.state, "submitted")

    def test_low_value_expense_submits_directly(self):
        expense = self.create_expenses({"total_amount_currency": 500.0})
        expense.action_submit()
        self.assertEqual(expense.state, "submitted")
        self.assertFalse(self.env["approval.engine.request"].search([
            ("res_model", "=", "hr.expense"), ("res_id", "=", expense.id),
        ]))
