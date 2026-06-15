# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class ApprovalRule(models.Model):
    _name = "approval.rule"
    _description = "Approval Rule"
    _order = "sequence, id"

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        # @api.constrains on level_ids does not fire when the field is absent
        # from create vals, so enforce the "at least one level" rule here too.
        rules._check_levels()
        return rules

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
        help="Model this rule applies to.",
    )
    model_name = fields.Char(
        related="model_id.model", string="Model Name", store=True, index=True
    )
    trigger_event = fields.Selection(
        [
            ("on_create", "On Create"),
            ("on_write", "On Write"),
            ("on_confirm", "On Confirm"),
        ],
        required=True,
        default="on_confirm",
    )
    condition_domain = fields.Char(
        string="Condition (Domain)",
        help="Odoo domain evaluated against the triggering record.",
    )
    condition_python = fields.Text(
        string="Condition (Python)",
        help="Optional boolean expression evaluated via safe_eval. "
        "Context: record, user, datetime, relativedelta.",
    )
    level_ids = fields.One2many(
        "approval.rule.level", "rule_id", string="Approval Levels"
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company
    )

    @api.constrains("level_ids")
    def _check_levels(self):
        for rule in self:
            if not rule.level_ids:
                raise ValidationError(
                    _("Rule '%s' must define at least one approval level.")
                    % rule.name
                )
            seqs = rule.level_ids.mapped("sequence")
            if len(seqs) != len(set(seqs)):
                raise ValidationError(
                    _("Approval levels in rule '%s' must have unique sequences.")
                    % rule.name
                )

    # --- Engine hooks -------------------------------------------------------

    def _approval_resolve_approvers(self, level, record=None):
        """Return a ``res.users`` recordset for the given ``approval.rule.level``.

        :param level: ``approval.rule.level`` record (must belong to ``self``).
        :param record: optional source record used as ``record`` in expression
                       context.  Pass the governed record so that dynamic
                       expressions can reference it.
        :returns: ``res.users`` recordset (may be empty).
        """
        self.ensure_one()
        env = self.env

        if level.approver_type == "group":
            # Odoo 19: res.groups explicit members are exposed via user_ids
            # (renamed from `users`). Implied-group membership is phase 2.
            return level.approver_group_id.user_ids if level.approver_group_id else env["res.users"]

        if level.approver_type == "expression":
            if not level.approver_expression:
                return env["res.users"]

            ctx = {
                "record": record,
                "user": env.user,
                "env": env,
            }
            try:
                result = safe_eval(level.approver_expression, ctx)
            except Exception as exc:
                raise ValidationError(
                    _("Error evaluating approver expression on level '%s': %s")
                    % (level.name or level.sequence, exc)
                )

            if not isinstance(result, models.BaseModel) or result._name != "res.users":
                raise ValidationError(
                    _("Approver expression on level '%s' must return a res.users recordset.")
                    % (level.name or level.sequence)
                )
            return result

        return env["res.users"]
