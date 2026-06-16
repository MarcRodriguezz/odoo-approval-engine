# -*- coding: utf-8 -*-
"""Unit tests for the rules-engine helpers.

The engine entry point ``_evaluate_approval_rules`` lives on the
``approval.engine.mixin`` AbstractModel and calls sibling mixin methods via
``self`` — so it can only run on a model that actually inherits the mixin.
The full matching + blocking flow is therefore covered end-to-end in the sale integration tests
against ``sale.order`` (a real governed model).

Here we unit-test the two helpers that have no inter-method ``self`` calls:

* ``_approval_match_domain`` — invoked *unbound* with a ``res.partner`` record
  as ``self`` (it only uses ``self.search_count`` + the rule).
* ``approval.engine.rule._approval_resolve_approvers`` — a concrete method on
  ``approval.engine.rule`` (group + expression resolution).
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError


@tagged("approval", "post_install", "-at_install")
class TestRuleEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model_partner = cls.env["ir.model"]._get("res.partner")
        cls.group = cls.env.ref("base.group_user")
        cls.MixinCls = type(cls.env["approval.engine.mixin"])
        cls.partner = cls.env["res.partner"].create({"name": "Test Partner Engine"})

    def _match_domain(self, record, rule):
        # Invoke the mixin method unbound with a real record as self.
        return self.MixinCls._approval_match_domain(record, rule)

    def _make_rule(self, **kw):
        level = (0, 0, {
            "sequence": 1, "name": "L1",
            "approver_type": "group", "approver_group_id": self.group.id,
        })
        vals = {
            "name": "Engine Test Rule",
            "model_id": self.model_partner.id,
            "trigger_event": "on_confirm",
            "level_ids": [level],
        }
        vals.update(kw)
        return self.env["approval.engine.rule"].create(vals)

    # --- _approval_match_domain ----------------------------------------

    def test_match_domain_empty_string_true(self):
        rule = self._make_rule(condition_domain="")
        self.assertTrue(self._match_domain(self.partner, rule))

    def test_match_domain_empty_list_true(self):
        rule = self._make_rule(condition_domain="[]")
        self.assertTrue(self._match_domain(self.partner, rule))

    def test_match_domain_matching_true(self):
        rule = self._make_rule(condition_domain="[('name', 'like', 'Test')]")
        self.assertTrue(self._match_domain(self.partner, rule))

    def test_match_domain_non_matching_false(self):
        rule = self._make_rule(condition_domain="[('name', '=', '__nope_xyz__')]")
        self.assertFalse(self._match_domain(self.partner, rule))

    def test_match_domain_unparseable_false(self):
        rule = self._make_rule(condition_domain="not a domain (")
        self.assertFalse(self._match_domain(self.partner, rule))

    # --- _approval_resolve_approvers -----------------------------------

    def test_resolve_approvers_group(self):
        group = self.env["res.groups"].create({"name": "Resolve Test Group"})
        u1 = self.env["res.users"].create({
            "name": "Resolver One", "login": "resolver1@test.local",
            "group_ids": [(4, group.id)],
        })
        rule = self._make_rule()
        rule.level_ids[0].write({
            "approver_type": "group", "approver_group_id": group.id,
        })
        approvers = rule._approval_resolve_approvers(rule.level_ids[0])
        self.assertIn(u1, approvers)

    def test_resolve_approvers_expression(self):
        admin = self.env.ref("base.user_admin")
        rule = self._make_rule()
        rule.level_ids[0].write({
            "approver_type": "expression",
            "approver_expression":
                "env['res.users'].browse(%s)" % admin.id,
        })
        approvers = rule._approval_resolve_approvers(
            rule.level_ids[0], record=self.partner
        )
        self.assertEqual(approvers, admin)

    # --- generic base hook (works on ANY model, no integration) ------------

    def test_generic_on_create_any_model(self):
        """An on_create rule on res.partner (no integration) still fires via
        the global base hook and creates a pending request."""
        self.env["approval.engine.rule"].create({
            "name": "Partner review",
            "model_id": self.model_partner.id,
            "trigger_event": "on_create",
            "level_ids": [(0, 0, {
                "sequence": 1, "name": "L1",
                "approver_type": "group", "approver_group_id": self.group.id,
            })],
        })
        partner = self.env["res.partner"].create({"name": "Generic Hook Partner"})
        req = self.env["approval.engine.request"].search([
            ("res_model", "=", "res.partner"), ("res_id", "=", partner.id),
        ])
        self.assertTrue(req, "on_create rule must fire on any model via base hook")
        self.assertEqual(req.state, "pending")

    def test_resolve_approvers_expression_bad_return(self):
        rule = self._make_rule()
        rule.level_ids[0].write({
            "approver_type": "expression",
            "approver_expression": "42",  # not a res.users recordset
        })
        with self.assertRaises(ValidationError):
            rule._approval_resolve_approvers(rule.level_ids[0])
