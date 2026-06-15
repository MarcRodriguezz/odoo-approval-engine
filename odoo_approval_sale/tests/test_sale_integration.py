# -*- coding: utf-8 -*-
"""Integration tests for odoo_approval_sale.

Tests cover:
1. High-value order: action_confirm is blocked; an approval.engine.request in state
   'pending' is created; order.approval_state == 'pending'.
2. Full approval cycle: approving the request triggers _on_approval_approved
   which calls action_confirm(approval_bypass=True) -> order.state == 'sale'.
3. Low-value order: action_confirm passes through immediately; no request is
   created; order.state == 'sale'.
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("approval", "post_install", "-at_install")
class TestSaleIntegration(TransactionCase):
    """Test sale.order integration with the approval engine."""

    def setUp(self):
        super().setUp()

        # ------------------------------------------------------------------
        # Approver user and group
        # ------------------------------------------------------------------
        # Use base.group_user so that admin (which is in that group) is
        # automatically resolved as an approver, allowing tests to register
        # decisions without needing a separate login.
        self.approver_group = self.env.ref("base.group_user")

        # A dedicated approver user so we can resolve approvers deterministically.
        self.approver_user = self.env["res.users"].create({
            "name": "Test Approver",
            "login": "test_approver_sale@example.com",
            "email": "test_approver_sale@example.com",
            "group_ids": [(4, self.approver_group.id)],
        })

        # ------------------------------------------------------------------
        # Approval rule for sale.order (on_confirm, amount_total > 10000)
        # ------------------------------------------------------------------
        sale_model = self.env["ir.model"].search(
            [("model", "=", "sale.order")], limit=1
        )
        self.rule = self.env["approval.engine.rule"].create({
            "name": "Test Sale High Value",
            "active": True,
            "sequence": 1,
            "model_id": sale_model.id,
            "trigger_event": "on_confirm",
            "condition_python": "record.amount_total > 10000",
            "level_ids": [(0, 0, {
                "sequence": 1,
                "name": "Level 1 — Internal User Approval",
                "approver_type": "group",
                "approver_group_id": self.approver_group.id,
                "min_approvals": 1,
            })],
        })

        # ------------------------------------------------------------------
        # Shared fixtures: partner and product
        # ------------------------------------------------------------------
        self.partner = self.env["res.partner"].create({
            "name": "Test Customer",
            "customer_rank": 1,
        })
        self.product = self.env["product.product"].create({
            "name": "Test Product",
            "list_price": 1.0,
            "type": "service",
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_order(self, unit_price, qty=1):
        """Create a sale.order with a single line at *unit_price* x *qty*."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": qty,
                "price_unit": unit_price,
                "name": self.product.name,
                # Clear taxes so amount_total is deterministic in tests.
                "tax_ids": [(6, 0, [])],
            })],
        })
        return order

    # ------------------------------------------------------------------
    # Test 1: high-value order is blocked and a pending request is created
    # ------------------------------------------------------------------
    def test_high_value_order_is_blocked(self):
        """action_confirm on a high-value order must NOT move it to 'sale'."""
        order = self._make_order(unit_price=15000.0, qty=1)
        self.assertAlmostEqual(order.amount_total, 15000.0, places=2)

        result = order.action_confirm()

        # Order must NOT be confirmed
        self.assertNotEqual(
            order.state, "sale",
            "High-value order must stay in draft/sent while awaiting approval.",
        )
        # approval_state must be 'pending'
        self.assertEqual(
            order.approval_state, "pending",
            "approval_state must be 'pending' after rule match.",
        )
        # Exactly one approval.engine.request must exist for this order
        requests = self.env["approval.engine.request"].search([
            ("res_model", "=", "sale.order"),
            ("res_id", "=", order.id),
        ])
        self.assertEqual(len(requests), 1, "Exactly one approval.engine.request expected.")
        self.assertEqual(requests.state, "pending")

        # The block action must be a client action (notification)
        self.assertEqual(result.get("type"), "ir.actions.client")

    # ------------------------------------------------------------------
    # Test 2: approving the request triggers real confirmation
    # ------------------------------------------------------------------
    def test_approve_request_confirms_order(self):
        """Full approval cycle: after approval, order.state must be 'sale'."""
        order = self._make_order(unit_price=20000.0, qty=1)
        order.action_confirm()

        request = self.env["approval.engine.request"].search([
            ("res_model", "=", "sale.order"),
            ("res_id", "=", order.id),
            ("state", "=", "pending"),
        ], limit=1)
        self.assertTrue(request, "Approval request not found.")

        # Register an approval decision for each pending level-1 line
        level1_lines = request.line_ids.filtered(
            lambda l: l.level == 1 and l.decision == "pending"
        )
        self.assertTrue(level1_lines, "No pending level-1 lines found.")

        for line in level1_lines:
            request._register_decision(line, "approved")

        # After all level-1 lines are approved the request must be 'approved'
        self.assertEqual(request.state, "approved")

        # And the sale order must now be in 'sale' state
        self.assertEqual(
            order.state, "sale",
            "Order must be confirmed after approval.",
        )

    # ------------------------------------------------------------------
    # Test 2b: realistic multi-level scenario (end-to-end)
    # ------------------------------------------------------------------
    def test_two_level_sale_approval_e2e(self):
        """End-to-end: a 2-level rule blocks confirmation until BOTH levels
        approve, then the order confirms for real."""
        # Archive the single-level setUp rule so only the 2-level rule fires.
        self.rule.active = False

        manager_group = self.env.ref("base.group_system")
        rule2 = self.env["approval.engine.rule"].create({
            "name": "Two-Level Sale Rule",
            "sequence": 1,
            "model_id": self.env["ir.model"]._get("sale.order").id,
            "trigger_event": "on_confirm",
            "condition_python": "record.amount_total > 10000",
            "level_ids": [
                (0, 0, {
                    "sequence": 1, "name": "User",
                    "approver_type": "group",
                    "approver_group_id": self.approver_group.id,
                    "min_approvals": 1,
                }),
                (0, 0, {
                    "sequence": 2, "name": "Manager",
                    "approver_type": "group",
                    "approver_group_id": manager_group.id,
                    "min_approvals": 1,
                }),
            ],
        })
        self.assertTrue(rule2.id)

        order = self._make_order(unit_price=50000.0, qty=1)
        order.action_confirm()
        self.assertNotEqual(order.state, "sale")

        request = self.env["approval.engine.request"].search([
            ("res_model", "=", "sale.order"), ("res_id", "=", order.id),
            ("state", "=", "pending"),
        ], limit=1)
        self.assertTrue(request)
        self.assertEqual(request.current_level, 1)

        # Approve level 1 -> advances, still pending
        for line in request.line_ids.filtered(
                lambda l: l.level == 1 and l.decision == "pending"):
            request._register_decision(line, "approved")
        self.assertEqual(request.state, "pending")
        self.assertEqual(request.current_level, 2)
        self.assertNotEqual(order.state, "sale")

        # Approve level 2 -> approved, order confirms
        for line in request.line_ids.filtered(
                lambda l: l.level == 2 and l.decision == "pending"):
            request._register_decision(line, "approved")
        self.assertEqual(request.state, "approved")
        self.assertEqual(order.state, "sale")

    # ------------------------------------------------------------------
    # Test 2c: a salesperson WITHOUT approval rights can still trigger it
    # ------------------------------------------------------------------
    def test_salesperson_without_approval_rights_can_confirm(self):
        """Regression: confirming a high-value order as a plain salesperson
        (not in any approval group) must NOT raise AccessError; the engine
        creates the request on their behalf via sudo."""
        salesperson = self.env["res.users"].create({
            "name": "Plain Salesperson",
            "login": "plain_salesperson_sale@example.com",
            "group_ids": [(4, self.env.ref("sales_team.group_sale_salesman").id)],
        })
        order = self._make_order(unit_price=25000.0, qty=1)
        order.partner_id = self.partner

        # Act as the salesperson — this used to raise AccessError on the
        # approval_request_ids compute / rule search.
        order_as_user = order.with_user(salesperson)
        order_as_user.action_confirm()  # must not raise

        self.assertNotEqual(order_as_user.state, "sale")
        self.assertEqual(order_as_user.approval_state, "pending")

    # ------------------------------------------------------------------
    # Test 3: low-value order bypasses approval entirely
    # ------------------------------------------------------------------
    def test_low_value_order_passes_directly(self):
        """Low-value orders must not be intercepted; no approval.engine.request created."""
        order = self._make_order(unit_price=500.0, qty=1)
        self.assertAlmostEqual(order.amount_total, 500.0, places=2)

        order.action_confirm()

        # Order must be confirmed immediately
        self.assertEqual(
            order.state, "sale",
            "Low-value order must be confirmed without approval.",
        )

        # No approval.engine.request should have been created
        requests = self.env["approval.engine.request"].search([
            ("res_model", "=", "sale.order"),
            ("res_id", "=", order.id),
        ])
        self.assertFalse(
            requests,
            "No approval.engine.request must be created for a low-value order.",
        )

        # approval_state must be 'none'
        self.assertEqual(order.approval_state, "none")
