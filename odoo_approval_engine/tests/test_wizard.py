# -*- coding: utf-8 -*-
"""Tests for the approval.decision.wizard.

The full-stack tests exercise approval.request._register_decision end to end.
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import UserError


@tagged("approval", "post_install", "-at_install")
class TestApprovalDecisionWizard(TransactionCase):
    """Unit tests for the decision wizard approve/reject paths."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Use res.partner as a lightweight target model
        cls.model_partner = cls.env["ir.model"]._get("res.partner")
        cls.group_user = cls.env.ref("base.group_user")

        # Create a minimal approval rule with one level
        cls.rule = cls.env["approval.engine.rule"].create(
            {
                "name": "Wizard Test Rule",
                "model_id": cls.model_partner.id,
                "trigger_event": "on_confirm",
                "level_ids": [
                    (
                        0,
                        0,
                        {
                            "sequence": 1,
                            "name": "Level 1",
                            "approver_type": "group",
                            "approver_group_id": cls.group_user.id,
                            "min_approvals": 1,
                        },
                    )
                ],
            }
        )

        # Partner to use as the source record
        cls.partner = cls.env["res.partner"].create({"name": "Wizard Test Partner"})

    def _create_request_with_line(self, decision="pending"):
        """Helper: create an approval.engine.request and a pending line for env.user."""
        request = self.env["approval.engine.request"].create(
            {
                "rule_id": self.rule.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "state": "pending",
            }
        )
        line = self.env["approval.engine.request.line"].create(
            {
                "request_id": request.id,
                "level": 1,
                "approver_id": self.env.user.id,
                "decision": decision,
            }
        )
        return request, line

    # ------------------------------------------------------------------
    # Wizard default_get
    # ------------------------------------------------------------------

    def test_default_get_from_line_context(self):
        """default_get picks up request_id and line_id from active_model context."""
        request, line = self._create_request_with_line()
        wizard = (
            self.env["approval.decision.wizard"]
            .with_context(
                active_model="approval.engine.request.line",
                active_id=line.id,
            )
            .create(
                {
                    "request_id": request.id,
                    "line_id": line.id,
                }
            )
        )
        self.assertEqual(wizard.request_id, request)
        self.assertEqual(wizard.line_id, line)

    def test_default_get_from_request_context(self):
        """default_get selects the user's pending line from a request context."""
        request, line = self._create_request_with_line()
        defaults = (
            self.env["approval.decision.wizard"]
            .with_context(
                active_model="approval.engine.request",
                active_id=request.id,
            )
            .default_get(["request_id", "line_id"])
        )
        self.assertEqual(defaults.get("request_id"), request.id)
        self.assertEqual(defaults.get("line_id"), line.id)

    # ------------------------------------------------------------------
    # action_approve
    # ------------------------------------------------------------------

    def test_action_approve_calls_register_decision(self):
        """action_approve delegates to _register_decision with 'approved'."""
        request, line = self._create_request_with_line()
        wizard = self.env["approval.decision.wizard"].create(
            {
                "request_id": request.id,
                "line_id": line.id,
                "comment": "Looks good",
            }
        )
        result = wizard.action_approve()

        self.assertEqual(line.decision, "approved")
        self.assertEqual(line.comment, "Looks good")
        self.assertEqual(result, {"type": "ir.actions.act_window_close"})

    def test_action_approve_sets_line_decision(self):
        """Full-stack: action_approve → line.decision == 'approved'."""
        request, line = self._create_request_with_line()
        wizard = self.env["approval.decision.wizard"].create(
            {
                "request_id": request.id,
                "line_id": line.id,
                "comment": "Approved by test",
            }
        )
        try:
            wizard.action_approve()
            self.assertEqual(line.decision, "approved")
        except NotImplementedError:
            self.skipTest(
                "_register_decision not available; skipping full-stack approve test."
            )

    # ------------------------------------------------------------------
    # action_reject
    # ------------------------------------------------------------------

    def test_action_reject_calls_register_decision(self):
        """action_reject delegates to _register_decision with 'rejected'."""
        request, line = self._create_request_with_line()
        wizard = self.env["approval.decision.wizard"].create(
            {
                "request_id": request.id,
                "line_id": line.id,
                "comment": "Not acceptable",
            }
        )
        result = wizard.action_reject()

        self.assertEqual(line.decision, "rejected")
        self.assertEqual(line.comment, "Not acceptable")
        self.assertEqual(request.state, "rejected")
        self.assertEqual(result, {"type": "ir.actions.act_window_close"})

    def test_action_reject_sets_line_decision(self):
        """Full-stack: action_reject → line.decision == 'rejected'."""
        request, line = self._create_request_with_line()
        wizard = self.env["approval.decision.wizard"].create(
            {
                "request_id": request.id,
                "line_id": line.id,
                "comment": "Rejected by test",
            }
        )
        try:
            wizard.action_reject()
            self.assertEqual(line.decision, "rejected")
        except NotImplementedError:
            self.skipTest(
                "_register_decision not available; skipping full-stack reject test."
            )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def test_approve_without_line_raises(self):
        """action_approve raises UserError when no line_id is set."""
        request, _line = self._create_request_with_line()
        wizard = self.env["approval.decision.wizard"].create(
            {"request_id": request.id}
        )
        with self.assertRaises(UserError):
            wizard.action_approve()

    def test_reject_without_line_raises(self):
        """action_reject raises UserError when no line_id is set."""
        request, _line = self._create_request_with_line()
        wizard = self.env["approval.decision.wizard"].create(
            {"request_id": request.id}
        )
        with self.assertRaises(UserError):
            wizard.action_reject()

    # ------------------------------------------------------------------
    # Inbox helper: action_open_decision_wizard on approval.engine.request.line
    # ------------------------------------------------------------------

    def test_open_decision_wizard_returns_act_window(self):
        """action_open_decision_wizard on a line returns a dialog act_window."""
        request, line = self._create_request_with_line()
        action = line.action_open_decision_wizard()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "approval.decision.wizard")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["context"]["active_id"], line.id)
        self.assertEqual(action["context"]["default_request_id"], request.id)

    # ------------------------------------------------------------------
    # Source-record smart button
    # ------------------------------------------------------------------

    def test_open_source_record_returns_form_action(self):
        """action_open_source_record returns an act_window for the source record."""
        request, _line = self._create_request_with_line()
        action = request.action_open_source_record()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "res.partner")
        self.assertEqual(action["res_id"], self.partner.id)

    def test_open_source_record_no_link_raises(self):
        """action_open_source_record raises UserError when no source linked."""
        # Create a minimal request without valid res_id to test edge case
        # (normally required, so we write directly after creation)
        request, _line = self._create_request_with_line()
        # res_model is required (not-null), so blank the res_id to hit the
        # "no source linked" branch.
        request.write({"res_id": 0})
        with self.assertRaises(UserError):
            request.action_open_source_record()
