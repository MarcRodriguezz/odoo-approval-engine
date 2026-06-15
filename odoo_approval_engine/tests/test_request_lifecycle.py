# -*- coding: utf-8 -*-
"""Tests for the approval.request state machine.

Tests drive the lifecycle through ``approval.request`` methods directly
(action_submit, _register_decision, _advance_level, _finalize) combined with
manually created rules/lines so that no UI or wizard layer is required.

The ``_on_approval_approved`` / ``_on_approval_rejected`` hooks are tested
via a sentinel flag on the source record's class; we monkey-patch a simple
``res.partner`` record to record calls.
"""
from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import UserError


@tagged("approval", "post_install", "-at_install")
class TestRequestLifecycle(TransactionCase):
    """State-machine tests for approval.request."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model_partner = cls.env["ir.model"]._get("res.partner")
        cls.group = cls.env.ref("base.group_user")

        # Two dedicated approver users (avoid OdooBot/superuser, which is not
        # materialized as a regular group member).
        cls.approver = cls.env["res.users"].create(
            {
                "name": "Approver One",
                "login": "approver1_lifecycle@test.local",
                "group_ids": [(4, cls.env.ref("base.group_user").id)],
            }
        )
        cls.approver2 = cls.env["res.users"].create(
            {
                "name": "Approver Two",
                "login": "approver2_lifecycle@test.local",
                "group_ids": [(4, cls.env.ref("base.group_user").id)],
            }
        )

        # Source partner record
        cls.partner = cls.env["res.partner"].create({"name": "Lifecycle Partner"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_rule(self, levels=1, min_approvals=1):
        """Create a rule with *levels* levels, each requiring *min_approvals*."""
        level_vals = [
            (
                0,
                0,
                {
                    "sequence": i + 1,
                    "name": "Level %s" % (i + 1),
                    "approver_type": "group",
                    "approver_group_id": self.group.id,
                    "min_approvals": min_approvals,
                },
            )
            for i in range(levels)
        ]
        return self.env["approval.rule"].create(
            {
                "name": "Lifecycle Rule",
                "model_id": self.model_partner.id,
                "trigger_event": "on_confirm",
                "level_ids": level_vals,
            }
        )

    def _make_draft_request(self, rule):
        """Create a draft approval.request for the test partner."""
        return self.env["approval.request"].create(
            {
                "rule_id": rule.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "state": "draft",
            }
        )

    def _make_pending_request(self, rule):
        """Create a pending approval.request with level-1 lines already generated."""
        request = self._make_draft_request(rule)
        request.action_submit()
        return request

    def _approve_line(self, request, approver, comment=None):
        """Find the first pending line for *approver* and approve it."""
        line = request.line_ids.filtered(
            lambda l: l.approver_id == approver and l.decision == "pending"
        )
        if not line:
            raise AssertionError(
                "No pending line found for approver %s on request %s"
                % (approver.name, request.name)
            )
        request._register_decision(line[0], "approved", comment=comment)

    def _reject_line(self, request, approver, comment=None):
        """Find the first pending line for *approver* and reject it."""
        line = request.line_ids.filtered(
            lambda l: l.approver_id == approver and l.decision == "pending"
        )
        if not line:
            raise AssertionError(
                "No pending line found for approver %s on request %s"
                % (approver.name, request.name)
            )
        request._register_decision(line[0], "rejected", comment=comment)

    # ------------------------------------------------------------------
    # Tests: action_submit
    # ------------------------------------------------------------------

    def test_action_submit_creates_level1_lines(self):
        """action_submit: draft → pending and creates level-1 lines."""
        rule = self._make_rule()
        request = self._make_draft_request(rule)

        self.assertEqual(request.state, "draft")
        self.assertFalse(request.line_ids, "Draft request should have no lines.")

        request.action_submit()

        self.assertEqual(request.state, "pending")
        self.assertTrue(request.line_ids, "Lines should be created on submit.")
        for line in request.line_ids:
            self.assertEqual(line.level, 1)
            self.assertEqual(line.decision, "pending")

    def test_action_submit_non_draft_raises(self):
        """action_submit on a non-draft request must raise UserError."""
        rule = self._make_rule()
        request = self._make_pending_request(rule)
        with self.assertRaises(UserError):
            request.action_submit()

    # ------------------------------------------------------------------
    # Tests: single-level approval → 'approved'
    # ------------------------------------------------------------------

    def test_single_level_approve_reaches_approved(self):
        """Single-level request: approve → state 'approved'."""
        rule = self._make_rule(levels=1)
        request = self._make_pending_request(rule)

        # Approve the first (and only) level-1 line
        line = request.line_ids[0]
        request._register_decision(line, "approved")

        self.assertEqual(request.state, "approved")

    def test_single_level_approve_calls_on_approval_approved(self):
        """_on_approval_approved must be called on the source record."""
        rule = self._make_rule(levels=1)
        request = self._make_pending_request(rule)

        approved_flag = []

        def fake_approved(self_record):
            approved_flag.append(True)
            return True

        with patch.object(
            type(self.partner), "_on_approval_approved", fake_approved, create=True
        ):
            line = request.line_ids[0]
            request._register_decision(line, "approved")

        self.assertTrue(approved_flag, "_on_approval_approved was not called.")

    # ------------------------------------------------------------------
    # Tests: two-level sequential approval
    # ------------------------------------------------------------------

    def test_two_level_sequential_approve(self):
        """Two-level rule: level-1 approval advances to level 2; level-2
        approval finalizes as 'approved'."""
        rule = self._make_rule(levels=2)
        request = self._make_pending_request(rule)

        # State after submit
        self.assertEqual(request.state, "pending")
        self.assertEqual(request.current_level, 1)

        # Approve level-1 line
        line1 = request.line_ids.filtered(lambda l: l.level == 1)[0]
        request._register_decision(line1, "approved")

        # Should now be at level 2, not yet finalized
        self.assertEqual(request.state, "pending",
                         "Request should remain pending after level-1 approval.")
        self.assertEqual(request.current_level, 2,
                         "current_level should advance to 2.")

        # Level-2 lines should exist
        level2_lines = request.line_ids.filtered(lambda l: l.level == 2)
        self.assertTrue(level2_lines, "Level-2 lines must be generated after advancing.")

        # Approve level-2 line
        line2 = level2_lines[0]
        request._register_decision(line2, "approved")

        self.assertEqual(request.state, "approved",
                         "Request should be approved after all levels pass.")

    def test_two_level_only_approves_after_both(self):
        """Level-1 approval alone must NOT finalize a two-level request."""
        rule = self._make_rule(levels=2)
        request = self._make_pending_request(rule)

        line1 = request.line_ids.filtered(lambda l: l.level == 1)[0]
        request._register_decision(line1, "approved")

        # Must still be pending, not approved
        self.assertNotEqual(request.state, "approved",
                            "Request should not be approved after only level-1.")
        self.assertEqual(request.state, "pending")

    # ------------------------------------------------------------------
    # Tests: rejection
    # ------------------------------------------------------------------

    def test_reject_at_level1_finalizes_rejected(self):
        """Rejection at level 1 must immediately set state to 'rejected'."""
        rule = self._make_rule(levels=2)
        request = self._make_pending_request(rule)

        line1 = request.line_ids.filtered(lambda l: l.level == 1)[0]
        request._register_decision(line1, "rejected", comment="Not acceptable.")

        self.assertEqual(request.state, "rejected")

    def test_reject_calls_on_approval_rejected(self):
        """_on_approval_rejected must be called on the source record."""
        rule = self._make_rule(levels=1)
        request = self._make_pending_request(rule)

        rejected_flag = []

        def fake_rejected(self_record):
            rejected_flag.append(True)
            return True

        with patch.object(
            type(self.partner), "_on_approval_rejected", fake_rejected, create=True
        ):
            line = request.line_ids[0]
            request._register_decision(line, "rejected")

        self.assertTrue(rejected_flag, "_on_approval_rejected was not called.")

    def test_reject_comment_stored_on_line(self):
        """Rejection comment is persisted on the line."""
        rule = self._make_rule(levels=1)
        request = self._make_pending_request(rule)

        line = request.line_ids[0]
        request._register_decision(line, "rejected", comment="Too expensive.")

        self.assertEqual(line.comment, "Too expensive.")

    # ------------------------------------------------------------------
    # Tests: min_approvals = 2
    # ------------------------------------------------------------------

    def test_min_approvals_2_requires_two_approvals(self):
        """With min_approvals=2, a single approval must not advance/finalize."""
        # Create a rule where level 1 requires 2 approvals
        # We need 2 approvers in the group; use a group that has ≥2 users.
        # Create a dedicated group with exactly our two test users.
        group2 = self.env["res.groups"].create(
            {"name": "Two Approver Group (lifecycle test)"}
        )
        group2.write(
            {
                "user_ids": [
                    (4, self.approver.id),
                    (4, self.approver2.id),
                ]
            }
        )

        rule = self.env["approval.rule"].create(
            {
                "name": "MinApprovals2 Rule",
                "model_id": self.model_partner.id,
                "trigger_event": "on_confirm",
                "level_ids": [
                    (
                        0,
                        0,
                        {
                            "sequence": 1,
                            "name": "Level 1 (needs 2)",
                            "approver_type": "group",
                            "approver_group_id": group2.id,
                            "min_approvals": 2,
                        },
                    )
                ],
            }
        )

        request = self._make_draft_request(rule)
        request.action_submit()

        self.assertEqual(request.state, "pending")

        # Find lines for each approver
        line_approver1 = request.line_ids.filtered(
            lambda l: l.approver_id == self.approver
        )
        line_approver2 = request.line_ids.filtered(
            lambda l: l.approver_id == self.approver2
        )

        self.assertTrue(line_approver1, "Line for approver1 should exist.")
        self.assertTrue(line_approver2, "Line for approver2 should exist.")

        # First approval — should NOT finalize (min_approvals=2)
        request._register_decision(line_approver1[0], "approved")
        self.assertEqual(
            request.state,
            "pending",
            "Request must remain pending after only 1 of 2 required approvals.",
        )

        # Second approval — should finalize
        request._register_decision(line_approver2[0], "approved")
        self.assertEqual(
            request.state,
            "approved",
            "Request should be approved after 2 of 2 required approvals.",
        )

    # ------------------------------------------------------------------
    # Tests: action_cancel
    # ------------------------------------------------------------------

    def test_action_cancel(self):
        """action_cancel sets state to 'cancelled'."""
        rule = self._make_rule()
        request = self._make_pending_request(rule)
        request.action_cancel()
        self.assertEqual(request.state, "cancelled")

    # ------------------------------------------------------------------
    # Tests: decision on non-pending request raises UserError
    # ------------------------------------------------------------------

    def test_decision_on_cancelled_raises(self):
        """_register_decision on a cancelled request must raise UserError."""
        rule = self._make_rule()
        request = self._make_pending_request(rule)
        line = request.line_ids[0]
        request.action_cancel()

        with self.assertRaises(UserError):
            request._register_decision(line, "approved")

    # ------------------------------------------------------------------
    # Tests: _advance_level helper directly
    # ------------------------------------------------------------------

    def test_advance_level_creates_new_lines(self):
        """_advance_level bumps current_level and creates lines for next level."""
        rule = self._make_rule(levels=2)
        request = self._make_pending_request(rule)

        self.assertEqual(request.current_level, 1)
        initial_line_count = len(request.line_ids)

        request._advance_level()

        self.assertEqual(request.current_level, 2)
        self.assertGreater(
            len(request.line_ids),
            initial_line_count,
            "New lines should be added for level 2.",
        )
        level2_lines = request.line_ids.filtered(lambda l: l.level == 2)
        self.assertTrue(level2_lines)

    # ------------------------------------------------------------------
    # Tests: _finalize sets state and date
    # ------------------------------------------------------------------

    def test_finalize_approved_state(self):
        """_finalize(True) sets state 'approved'."""
        rule = self._make_rule()
        request = self._make_pending_request(rule)
        request._finalize(approved=True)
        self.assertEqual(request.state, "approved")

    def test_finalize_rejected_state(self):
        """_finalize(False) sets state 'rejected'."""
        rule = self._make_rule()
        request = self._make_pending_request(rule)
        request._finalize(approved=False)
        self.assertEqual(request.state, "rejected")
