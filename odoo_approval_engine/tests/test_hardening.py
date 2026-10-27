# -*- coding: utf-8 -*-
"""Hardening tests: nobody can approve their own request, rule code is
admin-only, broken rules fail closed, and rules respect companies."""
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

RULE_LOGGER = "odoo.addons.odoo_approval_engine.models.approval_rule"


@tagged("approval", "post_install", "-at_install")
class TestApprovalHardening(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model_partner = cls.env["ir.model"]._get("res.partner")
        group_user = cls.env.ref("base.group_user")
        cls.approver_group = cls.env["res.groups"].create({"name": "Hardening Approvers"})

        def user(login, groups):
            return cls.env["res.users"].create({
                "name": login, "login": login + "@hardening.test",
                "group_ids": [(6, 0, [g.id for g in groups])],
            })

        cls.requester = user("requester", [group_user])
        cls.outsider = user("outsider", [group_user])
        cls.approver = user("approver", [group_user, cls.approver_group])
        cls.manager = user(
            "manager", [cls.env.ref("odoo_approval_engine.group_approval_manager")]
        )
        cls.partner = cls.env["res.partner"].create({"name": "Hardening Partner"})

    def _make_rule(self, **vals):
        return self.env["approval.engine.rule"].create({
            "name": "Hardening Rule",
            "model_id": self.model_partner.id,
            "trigger_event": "on_confirm",
            "level_ids": [(0, 0, {
                "sequence": 1, "name": "L1", "approver_type": "group",
                "approver_group_id": self.approver_group.id,
            })],
            **vals,
        })

    def _request_by_requester(self, rule=None):
        rule = rule or self._make_rule()
        return self.env["approval.engine.request"].with_user(
            self.requester
        )._create_request_for(self.partner, rule)

    # --- Nobody can approve their own request -------------------------------

    def test_requester_cannot_add_self_as_approver(self):
        request = self._request_by_requester()
        line = request.line_ids.with_user(self.requester)
        with self.assertRaises(AccessError):
            line.write({"candidate_user_ids": [(4, self.requester.id)]})
        with self.assertRaises(AccessError):
            line.write({"min_approvals": 0, "decision": "approved"})

    def test_requester_cannot_edit_request(self):
        request = self._request_by_requester()
        with self.assertRaises(AccessError):
            request.with_user(self.requester).write({"state": "approved"})
        self.assertEqual(request.state, "pending")

    def test_requester_cannot_approve_own_request(self):
        request = self._request_by_requester()
        with self.assertRaises(UserError):
            request.line_ids.with_user(self.requester).action_quick_approve()
        self.assertEqual(request.state, "pending")

    def test_approver_can_still_approve(self):
        request = self._request_by_requester()
        request.line_ids.with_user(self.approver).action_quick_approve()
        self.assertEqual(request.state, "approved")

    def test_requester_can_comment_in_chatter(self):
        request = self._request_by_requester()
        request.with_user(self.requester).message_post(body="Any news?")
        self.assertIn("Any news?", request.message_ids.mapped("body")[0])

    # --- Step back / cancel -------------------------------------------------

    def test_user_cannot_step_back(self):
        request = self._request_by_requester()
        with self.assertRaises(AccessError):
            request.with_user(self.approver).action_step_back()

    def test_requester_can_cancel_own_pending_request(self):
        request = self._request_by_requester()
        request.with_user(self.requester).action_cancel()
        self.assertEqual(request.state, "cancelled")

    def test_other_user_cannot_cancel_request(self):
        request = self._request_by_requester()
        with self.assertRaises(AccessError):
            request.with_user(self.approver).action_cancel()
        self.assertEqual(request.state, "pending")

    def test_manager_can_step_back_and_cancel(self):
        request = self._request_by_requester()
        request.with_user(self.manager).action_step_back()
        self.assertEqual(request.state, "pending")
        request.with_user(self.manager).action_cancel()
        self.assertEqual(request.state, "cancelled")

    # --- Rule code is admin-only --------------------------------------------

    def test_manager_cannot_set_python_condition(self):
        rule = self._make_rule()
        with self.assertRaises(AccessError):
            rule.with_user(self.manager).write({"condition_python": "True"})

    def test_manager_cannot_set_approver_expression(self):
        rule = self._make_rule()
        with self.assertRaises(AccessError):
            rule.level_ids.with_user(self.manager).write({
                "approver_type": "expression",
                "approver_expression": "env['res.users'].search([])",
            })

    def test_manager_can_still_manage_rules(self):
        rule = self._make_rule()
        rule.with_user(self.manager).write({
            "name": "Renamed", "condition_domain": "[('name', 'ilike', 'Hardening')]",
        })
        self.assertEqual(rule.name, "Renamed")

    def test_admin_can_set_python_condition(self):
        admin = self.env["res.users"].create({
            "name": "Hardening Admin", "login": "admin@hardening.test",
            "group_ids": [(6, 0, [
                self.env.ref("base.group_system").id,
                self.env.ref("odoo_approval_engine.group_approval_manager").id,
            ])],
        })
        rule = self._make_rule()
        rule.with_user(admin).write(
            {"condition_python": "record.name == 'Hardening Partner'"}
        )
        self.assertTrue(rule._match_record(self.partner))

    # --- Validation on save + fail closed at runtime ------------------------

    def test_invalid_domain_rejected_on_save(self):
        with self.assertRaises(ValidationError):
            self._make_rule(condition_domain="[('no_such_field', '=', 1)]")
        with self.assertRaises(ValidationError):
            self._make_rule(condition_domain="'not a list'")

    def test_invalid_python_rejected_on_save(self):
        with self.assertRaises(ValidationError):
            self._make_rule(condition_python="record.name ==")

    def test_invalid_approver_expression_rejected_on_save(self):
        rule = self._make_rule()
        with self.assertRaises(ValidationError):
            rule.level_ids.write({
                "approver_type": "expression", "approver_expression": "env[",
            })

    def test_runtime_error_requires_approval(self):
        """A condition that breaks at runtime holds the document instead of
        silently letting it through (and the error is logged)."""
        rule = self._make_rule(condition_python="record.no_such_field > 1")
        with self.assertLogs(RULE_LOGGER, level="ERROR"):
            self.assertTrue(rule._match_record(self.partner))
        with self.assertLogs(RULE_LOGGER, level="ERROR"):
            self.assertTrue(
                self.env["approval.engine.request"]._evaluate_rules_for(
                    self.partner, "on_confirm"
                )
            )

    def test_false_condition_does_not_match(self):
        rule = self._make_rule(condition_python="record.name == 'Someone else'")
        self.assertFalse(rule._match_record(self.partner))

    # --- Bypass flag ---------------------------------------------------------

    def test_forged_bypass_context_does_not_skip_on_create_rule(self):
        """The generic create hook ignores an ``approval_bypass`` value sent by
        a client; only the engine's own (secret) value skips evaluation."""
        self._make_rule(trigger_event="on_create")
        partner = self.env["res.partner"].with_context(approval_bypass=True).create(
            {"name": "Forged Bypass Partner"}
        )
        self.assertTrue(self.env["approval.engine.request"].search([
            ("res_model", "=", "res.partner"), ("res_id", "=", partner.id),
        ]))

    # --- Multi-company --------------------------------------------------------

    def test_rules_respect_company(self):
        company_a = self.env.company
        company_b = self.env["res.company"].create({"name": "Hardening Company B"})
        self.partner.company_id = company_a
        Request = self.env["approval.engine.request"]

        self._make_rule(company_id=company_b.id)
        self.assertFalse(Request._evaluate_rules_for(self.partner, "on_confirm"),
                         "A rule of company B must not hold a company A document.")

        self._make_rule(company_id=False)
        self.assertTrue(Request._evaluate_rules_for(self.partner, "on_confirm"),
                        "A company-less rule applies to every company.")
        request = Request.search([("res_model", "=", "res.partner"),
                                  ("res_id", "=", self.partner.id)])
        self.assertEqual(request.company_id, company_a,
                         "The request belongs to the document's company.")
