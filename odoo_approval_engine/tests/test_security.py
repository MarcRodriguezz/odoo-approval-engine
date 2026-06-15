# -*- coding: utf-8 -*-
"""
Security tests.

Verify that:
  - A non-manager user cannot create or write approval.engine.rule (AccessError).
  - A manager user can create approval.engine.rule.
  - An approver cannot read an approval.engine.request they are not involved in (AccessError).
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("approval", "post_install", "-at_install")
class TestApprovalSecurity(TransactionCase):
    """Security access control tests for the approval engine."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Resolve group references once
        cls.group_user = cls.env.ref("odoo_approval_engine.group_approval_user")
        cls.group_approver = cls.env.ref("odoo_approval_engine.group_approval_approver")
        cls.group_manager = cls.env.ref("odoo_approval_engine.group_approval_manager")

        # Resolve a valid ir.model for use in approval.engine.rule creation
        cls.ir_model = cls.env["ir.model"].search(
            [("model", "=", "approval.engine.request")], limit=1
        )

        # ---- create users ----

        # User who is only an approver (implied: group_approval_user too)
        cls.user_approver = cls.env["res.users"].create(
            {
                "name": "Test Approver",
                "login": "test_approver_wt3@example.com",
                "group_ids": [(6, 0, [cls.group_approver.id])],
            }
        )

        # User who is a manager (implied: approver + user)
        cls.user_manager = cls.env["res.users"].create(
            {
                "name": "Test Manager",
                "login": "test_manager_wt3@example.com",
                "group_ids": [(6, 0, [cls.group_manager.id])],
            }
        )

        # A third user who creates a request that approver has no connection to
        cls.user_other = cls.env["res.users"].create(
            {
                "name": "Test Other",
                "login": "test_other_wt3@example.com",
                "group_ids": [(6, 0, [cls.group_user.id])],
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_rule(self, env=None):
        """Create a minimal approval.engine.rule using the given environment."""
        env = env or self.env
        return env["approval.engine.rule"].create(
            {
                "name": "Test Rule WT3",
                "model_id": self.ir_model.id,
                "trigger_event": "on_confirm",
                "level_ids": [(0, 0, {
                    "sequence": 1,
                    "name": "L1",
                    "approver_type": "group",
                    "approver_group_id": self.group_user.id,
                })],
            }
        )

    def _make_request(self, env=None):
        """Create a minimal approval.engine.request owned by user_other."""
        env = env or self.env
        # We need at least one rule to reference
        rule = self._make_rule()
        return env["approval.engine.request"].create(
            {
                "rule_id": rule.id,
                "res_model": "approval.engine.request",
                "res_id": 1,
                "requested_by": self.user_other.id,
            }
        )

    # ------------------------------------------------------------------
    # Tests: approval.engine.rule access
    # ------------------------------------------------------------------

    def test_non_manager_cannot_create_approval_rule(self):
        """An approver (non-manager) must not be able to create an approval.engine.rule."""
        with self.assertRaises(AccessError):
            self._make_rule(env=self.env(user=self.user_approver))

    def test_non_manager_cannot_write_approval_rule(self):
        """An approver (non-manager) must not be able to write to an approval.engine.rule."""
        # Manager creates the rule first
        rule = self._make_rule()
        self.env.cr.flush()
        self.env.invalidate_all()

        with self.assertRaises(AccessError):
            rule.with_user(self.user_approver).write({"name": "Hacked Name"})

    def test_manager_can_create_approval_rule(self):
        """A manager must be able to create an approval.engine.rule without error."""
        rule = self._make_rule(env=self.env(user=self.user_manager))
        self.assertTrue(rule.id, "Manager should be able to create an approval.engine.rule")

    # ------------------------------------------------------------------
    # Tests: approval.engine.request record rules
    # ------------------------------------------------------------------

    def test_approver_cannot_read_unrelated_request(self):
        """
        An approver who is neither the requester nor an approver on any line
        of a given approval.engine.request must receive an AccessError when reading it.
        """
        # Create request as superuser (owned by user_other, no approver lines)
        request = self._make_request()
        self.env.cr.flush()
        self.env.invalidate_all()

        # user_approver has no connection to this request → must be invisible
        with self.assertRaises(AccessError):
            # browse + read triggers the record rule check
            request.with_user(self.user_approver).read(["name"])

    def test_requester_can_read_own_request(self):
        """The user who created (requested_by) the request must be able to read it."""
        request = self._make_request()
        self.env.cr.flush()
        self.env.invalidate_all()

        # user_other is requested_by → should be visible
        result = request.with_user(self.user_other).read(["name"])
        self.assertTrue(result, "Requester should be able to read their own request")

    def test_manager_can_read_any_request(self):
        """A manager must be able to read any approval.engine.request."""
        request = self._make_request()
        self.env.cr.flush()
        self.env.invalidate_all()

        result = request.with_user(self.user_manager).read(["name"])
        self.assertTrue(result, "Manager should be able to read any approval.engine.request")
