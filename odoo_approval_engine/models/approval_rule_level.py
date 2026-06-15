# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ApprovalRuleLevel(models.Model):
    _name = "approval.engine.rule.level"
    _description = "Approval Rule Level"
    _order = "sequence, id"

    rule_id = fields.Many2one(
        "approval.engine.rule", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(string="Level", required=True, default=1)
    name = fields.Char()
    approver_type = fields.Selection(
        [("group", "User Group"), ("expression", "Python Expression")],
        required=True,
        default="group",
    )
    approver_group_id = fields.Many2one("res.groups", string="Approver Group")
    approver_expression = fields.Text(
        string="Approver Expression",
        help="safe_eval expression returning a res.users recordset. "
        "Context: record, user, env.",
    )
    min_approvals = fields.Integer(
        string="Minimum Approvals",
        default=1,
        help="Number of approvals required to clear this level.",
    )

    @api.constrains("approver_type", "approver_group_id", "approver_expression")
    def _check_approver_config(self):
        for level in self:
            if level.approver_type == "group" and not level.approver_group_id:
                raise ValidationError(
                    _("Level '%s' requires an approver group.")
                    % (level.name or level.sequence)
                )
            if level.approver_type == "expression" and not level.approver_expression:
                raise ValidationError(
                    _("Level '%s' requires an approver expression.")
                    % (level.name or level.sequence)
                )

    @api.constrains("min_approvals")
    def _check_min_approvals(self):
        for level in self:
            if level.min_approvals < 1:
                raise ValidationError(
                    _("Minimum approvals must be at least 1.")
                )
