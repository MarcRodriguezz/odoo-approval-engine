# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError


@tagged("approval", "post_install", "-at_install")
class TestApprovalModels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model_partner = cls.env["ir.model"]._get("res.partner")
        cls.group = cls.env.ref("base.group_user")

    def _make_rule(self, levels=1):
        level_vals = [
            (
                0,
                0,
                {
                    "sequence": i + 1,
                    "name": "Level %s" % (i + 1),
                    "approver_type": "group",
                    "approver_group_id": self.group.id,
                },
            )
            for i in range(levels)
        ]
        return self.env["approval.rule"].create(
            {
                "name": "Test Rule",
                "model_id": self.model_partner.id,
                "trigger_event": "on_confirm",
                "level_ids": level_vals,
            }
        )

    def test_rule_with_levels_persists(self):
        rule = self._make_rule(levels=2)
        self.assertEqual(len(rule.level_ids), 2)
        self.assertEqual(rule.model_name, "res.partner")

    def test_rule_without_levels_raises(self):
        with self.assertRaises(ValidationError):
            self.env["approval.rule"].create(
                {
                    "name": "No Levels",
                    "model_id": self.model_partner.id,
                    "trigger_event": "on_confirm",
                }
            )

    def test_duplicate_level_sequence_raises(self):
        with self.assertRaises(ValidationError):
            self.env["approval.rule"].create(
                {
                    "name": "Dup Levels",
                    "model_id": self.model_partner.id,
                    "trigger_event": "on_confirm",
                    "level_ids": [
                        (0, 0, {"sequence": 1, "approver_type": "group",
                                "approver_group_id": self.group.id}),
                        (0, 0, {"sequence": 1, "approver_type": "group",
                                "approver_group_id": self.group.id}),
                    ],
                }
            )

    def test_request_sequence_assigned(self):
        rule = self._make_rule()
        request = self.env["approval.request"].create(
            {
                "rule_id": rule.id,
                "res_model": "res.partner",
                "res_id": self.env.user.partner_id.id,
            }
        )
        self.assertNotEqual(request.name, "/")
        self.assertTrue(request.name.startswith("APR/"))

    def test_min_approvals_constraint(self):
        with self.assertRaises(ValidationError):
            self.env["approval.rule"].create(
                {
                    "name": "Bad Min",
                    "model_id": self.model_partner.id,
                    "trigger_event": "on_confirm",
                    "level_ids": [
                        (0, 0, {"sequence": 1, "approver_type": "group",
                                "approver_group_id": self.group.id,
                                "min_approvals": 0}),
                    ],
                }
            )
