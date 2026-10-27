# -*- coding: utf-8 -*-
"""Tests for the approval.engine.request state machine.

Tests drive the lifecycle through ``approval.engine.request`` methods directly
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
    """State-machine tests for approval.engine.request."""

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
        return self.env["approval.engine.rule"].create(
            {
                "name": "Lifecycle Rule",
                "model_id": self.model_partner.id,
                "trigger_event": "on_confirm",
                "level_ids": level_vals,
            }
        )

    def _make_draft_request(self, rule):
        """Create a draft approval.engine.request for the test partner."""
        return self.env["approval.engine.request"].create(
            {
                "rule_id": rule.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "state": "draft",
            }
        )

    def _make_pending_request(self, rule):
        """Create a pending approval.engine.request with level-1 lines already generated."""
        request = self._make_draft_request(rule)
        request.action_submit()
        return request

    def _current_stage(self, request):
        return request.line_ids.filtered(
            lambda l: l.level == request.current_level and l.decision == "pending"
        )[:1]

    def _approve_line(self, request, approver, comment=None):
        """Approve the current pending stage as *approver*."""
        line = self._current_stage(request)
        if not line:
            raise AssertionError("No pending stage on request %s" % request.name)
        request._register_decision(line, "approved", comment=comment, actor=approver)

    def _reject_line(self, request, approver, comment=None):
        """Reject the current pending stage as *approver*."""
        line = self._current_stage(request)
        if not line:
            raise AssertionError("No pending stage on request %s" % request.name)
        request._register_decision(line, "rejected", comment=comment, actor=approver)

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

        rule = self.env["approval.engine.rule"].create(
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

        # One stage line, needing 2 distinct approvals.
        stage = request.line_ids.filtered(lambda l: l.level == 1)
        self.assertEqual(len(stage), 1, "Exactly one stage line expected.")
        self.assertEqual(stage.min_approvals, 2)
        # Group approvers are matched live (not snapshotted as candidates).
        self.assertEqual(stage.approver_group_id, group2)
        self.assertIn(self.approver, stage._effective_candidate_users())
        self.assertIn(self.approver2, stage._effective_candidate_users())

        # First approval — should NOT finalize (min_approvals=2)
        request._register_decision(stage, "approved", actor=self.approver)
        self.assertEqual(
            request.state, "pending",
            "Request must remain pending after only 1 of 2 required approvals.",
        )

        # Same user approving again must NOT count twice.
        request._register_decision(stage, "approved", actor=self.approver)
        self.assertEqual(request.state, "pending",
                         "Re-approval by the same user must not count.")

        # Second distinct approval — should finalize.
        request._register_decision(stage, "approved", actor=self.approver2)
        self.assertEqual(
            request.state, "approved",
            "Request should be approved after 2 of 2 required approvals.",
        )

    # ------------------------------------------------------------------
    # Tests: action_cancel
    # ------------------------------------------------------------------

    def test_group_membership_is_live(self):
        """Any current member of the stage's group can approve — including a
        user added to the group *after* the request was created."""
        group = self.env["res.groups"].create({"name": "Live Approvers"})
        rule = self.env["approval.engine.rule"].create({
            "name": "Live group rule",
            "model_id": self.model_partner.id,
            "trigger_event": "on_confirm",
            "level_ids": [(0, 0, {
                "sequence": 1, "name": "S1", "approver_type": "group",
                "approver_group_id": group.id, "min_approvals": 1,
            })],
        })
        request = self._make_draft_request(rule)
        request.action_submit()
        stage = request.line_ids[:1]
        self.assertEqual(stage.approver_group_id, group)

        newbie = self.env["res.users"].create({
            "name": "Newbie", "login": "newbie_live@test.local",
            "group_ids": [(4, self.env.ref("base.group_user").id)],
        })
        self.assertNotIn(newbie, stage._effective_candidate_users())

        # Add the user to the approver group -> they can approve immediately.
        newbie.group_ids = [(4, group.id)]
        stage.invalidate_recordset()
        self.assertIn(newbie, stage._effective_candidate_users())

    def test_action_cancel(self):
        """action_cancel sets state to 'cancelled'."""
        rule = self._make_rule()
        request = self._make_pending_request(rule)
        request.action_cancel()
        self.assertEqual(request.state, "cancelled")

    def test_step_back_cancelled_request_can_be_approved(self):
        """A cancelled request can be sent back and approved again."""
        rule = self._make_rule(levels=1)
        request = self._make_pending_request(rule)
        request.action_cancel()
        self.assertEqual(request.state, "cancelled")

        request.action_step_back()
        self.assertEqual(request.state, "pending")

        line = request.line_ids.filtered(
            lambda l: l.level == request.current_level and l.decision == "pending"
        )
        self.assertTrue(line, "Reopened request must have a pending stage again.")
        request._register_decision(line[0], "approved")
        self.assertEqual(request.state, "approved")

    def test_step_back_two_levels(self):
        """Step back returns to the previous stage and drops later ones."""
        rule = self._make_rule(levels=2)
        request = self._make_pending_request(rule)
        # advance to stage 2
        self._approve_line(request, self.approver)
        self.assertEqual(request.current_level, 2)
        # step back -> stage 1, no stage-2 line left
        request.action_step_back()
        self.assertEqual(request.current_level, 1)
        self.assertFalse(request.line_ids.filtered(lambda l: l.level == 2))
        self.assertEqual(request.state, "pending")

    def test_step_back_approved_request_raises(self):
        """An approved request already ran its held action: it cannot be
        reopened (re-approving would run the action twice)."""
        rule = self._make_rule(levels=1)
        request = self._make_pending_request(rule)
        request._register_decision(request.line_ids[0], "approved")
        self.assertEqual(request.state, "approved")
        with self.assertRaises(UserError):
            request.action_step_back()
        self.assertEqual(request.state, "approved")

    def test_step_back_rejected_request_reopens(self):
        """A rejected request can be reopened at the stage that rejected it."""
        rule = self._make_rule(levels=2)
        request = self._make_pending_request(rule)
        self._approve_line(request, self.approver)       # stage 1 -> stage 2
        self._reject_line(request, self.approver, "No")  # stage 2 rejects
        self.assertEqual(request.state, "rejected")
        request.action_step_back()
        self.assertEqual(request.state, "pending")
        self.assertEqual(request.current_level, 2)
        self.assertEqual(self._current_stage(request).decision, "pending")

    def test_cancel_approved_request_raises(self):
        """Approved (or otherwise closed) requests cannot be cancelled."""
        rule = self._make_rule(levels=1)
        request = self._make_pending_request(rule)
        request._register_decision(request.line_ids[0], "approved")
        with self.assertRaises(UserError):
            request.action_cancel()
        self.assertEqual(request.state, "approved")

    def test_step_back_cycles_never_duplicate_stages(self):
        """Repeated step-back / re-approve must keep exactly one line per stage."""
        rule = self._make_rule(levels=2)
        request = self._make_pending_request(rule)

        for _i in range(3):
            self._approve_line(request, self.approver)   # stage 1 -> stage 2
            self.assertEqual(request.current_level, 2)
            request.action_step_back()                   # back to stage 1
            self.assertEqual(request.current_level, 1)

        self._approve_line(request, self.approver)       # stage 1 -> stage 2
        self._approve_line(request, self.approver)       # stage 2 -> approved
        self.assertEqual(sorted(request.line_ids.mapped("level")), [1, 2],
                         "There must be exactly one line per stage.")
        self.assertEqual(request.state, "approved")

    def test_generate_lines_is_idempotent(self):
        """Generating a stage twice must not create a duplicate line."""
        rule = self._make_rule(levels=1)
        request = self._make_pending_request(rule)
        level = request._get_level_obj(1)
        request._generate_lines_for_level(level)
        request._generate_lines_for_level(level)
        self.assertEqual(
            len(request.line_ids.filtered(lambda l: l.level == 1)), 1
        )

    # ------------------------------------------------------------------
    # Tests: decision on non-pending request raises UserError
    # ------------------------------------------------------------------

    def test_closed_date_and_duration(self):
        """closed_date is set on finalize and approval_duration is computed."""
        rule = self._make_rule(levels=1)
        request = self._make_pending_request(rule)
        self.assertFalse(request.closed_date)
        request._register_decision(request.line_ids[0], "rejected", comment="No")
        self.assertTrue(request.closed_date)
        self.assertGreaterEqual(request.approval_duration, 0.0)
        # reopening clears the closed date
        request.action_step_back()
        self.assertFalse(request.closed_date)

    def test_decision_on_cancelled_raises(self):
        """_register_decision on a cancelled request must raise UserError."""
        rule = self._make_rule()
        request = self._make_pending_request(rule)
        line = request.line_ids[0]
        request.action_cancel()

        with self.assertRaises(UserError):
            request._register_decision(line, "approved")

    def test_decision_on_decided_stage_raises(self):
        """Re-deciding an already approved stage must not advance the request
        past the current stage (stale inbox / wizard)."""
        rule = self._make_rule(levels=2)
        request = self._make_pending_request(rule)
        line1 = self._current_stage(request)
        request._register_decision(line1, "approved", actor=self.approver)
        self.assertEqual(request.current_level, 2)

        with self.assertRaises(UserError):
            request._register_decision(line1, "approved", actor=self.approver2)
        with self.assertRaises(UserError):
            request._register_decision(line1, "rejected", actor=self.approver2)

        self.assertEqual(request.state, "pending")
        self.assertEqual(request.current_level, 2)
        self.assertEqual(self._current_stage(request).decision, "pending")

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
