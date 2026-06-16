# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, Form
from odoo.tests import tagged


@tagged("approval", "post_install", "-at_install")
class TestPurchaseIntegration(TransactionCase):
    """purchase.order integration with the approval engine (2-step rule)."""

    def setUp(self):
        super().setUp()
        # Avoid interference from the shipped demo rule.
        self.env["approval.engine.rule"].search(
            [("model_name", "=", "purchase.order")]
        ).write({"active": False})

        self.group = self.env.ref("base.group_user")
        # Ensure the group has an explicit member so approver lines are generated.
        self.approver = self.env["res.users"].create({
            "name": "Test Buyer",
            "login": "buyer_purchase_test@example.com",
            "group_ids": [(4, self.group.id)],
        })
        purchase_model = self.env["ir.model"]._get("purchase.order")

        # A 2-step rule: both steps approvable by the admin (in base.group_user).
        self.rule = self.env["approval.engine.rule"].create({
            "name": "Test Purchase 2-step",
            "sequence": 1,
            "model_id": purchase_model.id,
            "trigger_event": "on_confirm",
            "condition_python": "record.amount_total > 1000",
            "level_ids": [
                (0, 0, {"sequence": 1, "name": "Buyer",
                        "approver_type": "group",
                        "approver_group_id": self.group.id, "min_approvals": 1}),
                (0, 0, {"sequence": 2, "name": "Manager",
                        "approver_type": "group",
                        "approver_group_id": self.group.id, "min_approvals": 1}),
            ],
        })

        self.vendor = self.env["res.partner"].create({"name": "Test Vendor"})
        self.product = self.env["product.product"].create({
            "name": "Test Purchased Product",
            "type": "service",
            "purchase_ok": True,
        })

    def _make_po(self, price):
        po_form = Form(self.env["purchase.order"])
        po_form.partner_id = self.vendor
        with po_form.order_line.new() as line:
            line.product_id = self.product
            line.product_qty = 1
            line.price_unit = price
        return po_form.save()

    def test_high_value_po_blocked_then_two_step_approved(self):
        order = self._make_po(price=2000.0)
        order.button_confirm()

        self.assertNotEqual(order.state, "purchase",
                            "High-value PO must wait for approval.")
        request = self.env["approval.engine.request"].search([
            ("res_model", "=", "purchase.order"), ("res_id", "=", order.id),
            ("state", "=", "pending"),
        ], limit=1)
        self.assertTrue(request)
        self.assertEqual(request.current_level, 1)

        # Step 1
        for line in request.line_ids.filtered(
                lambda l: l.level == 1 and l.decision == "pending"):
            request._register_decision(line, "approved")
        self.assertEqual(request.state, "pending")
        self.assertEqual(request.current_level, 2)
        self.assertNotEqual(order.state, "purchase")

        # Step 2
        for line in request.line_ids.filtered(
                lambda l: l.level == 2 and l.decision == "pending"):
            request._register_decision(line, "approved")
        self.assertEqual(request.state, "approved")
        self.assertEqual(order.state, "purchase")

    def test_low_value_po_passes_directly(self):
        order = self._make_po(price=100.0)
        order.button_confirm()
        self.assertEqual(order.state, "purchase")
        self.assertFalse(self.env["approval.engine.request"].search([
            ("res_model", "=", "purchase.order"), ("res_id", "=", order.id),
        ]))
