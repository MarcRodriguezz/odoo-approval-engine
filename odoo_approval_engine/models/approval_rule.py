# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import ormcache
from odoo.tools.safe_eval import safe_eval, test_python_expr

_logger = logging.getLogger(__name__)


class ApprovalRule(models.Model):
    _name = "approval.engine.rule"
    _description = "Approval Rule"
    _order = "sequence, id"

    @api.model
    def _sync_trigger_event(self, vals):
        """Keep the technical matching key (trigger_event) in sync with the
        user-facing trigger_id selector."""
        if vals.get("trigger_id"):
            trig = self.env["approval.engine.trigger"].browse(vals["trigger_id"])
            vals["trigger_event"] = trig.code
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_trigger_event(vals)
        rules = super().create(vals_list)
        # @api.constrains on level_ids does not fire when the field is absent
        # from create vals, so enforce the "at least one level" rule here too.
        rules._check_levels()
        self.env.registry.clear_cache()
        return rules

    def write(self, vals):
        self._sync_trigger_event(vals)
        res = super().write(vals)
        # Rules changed -> the cache of "which models have rules" is stale.
        self.env.registry.clear_cache()
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res

    @api.model
    @ormcache("trigger_event")
    def _models_with_rules(self, trigger_event):
        """Cached set of model names that have at least one active rule for the
        given trigger_event. Lets the global base hook skip cheaply."""
        rules = self.sudo().search(
            [("trigger_event", "=", trigger_event), ("active", "=", True)]
        )
        return tuple(set(rules.mapped("model_name")))

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    # Only integrated models (those that expose an approvable action) can be
    # selected — see _compute_allowed_model_ids + the view domain.
    allowed_model_ids = fields.Many2many(
        "ir.model", compute="_compute_allowed_model_ids",
        string="Selectable Models",
    )
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
        help="Business document this rule applies to.",
    )
    model_name = fields.Char(
        related="model_id.model", string="Model Name", store=True, index=True
    )
    trigger_id = fields.Many2one(
        "approval.engine.trigger",
        string="Approvable Action",
        ondelete="restrict",
        help="Which action on the document requires approval.",
    )
    # Technical matching key, derived from trigger_id (kept for the engine).
    trigger_event = fields.Char(string="Trigger Code", readonly=True, copy=True)

    @api.depends_context("uid")
    def _compute_allowed_model_ids(self):
        triggers = self.env["approval.engine.trigger"].sudo().search(
            [("model_id", "!=", False)]
        )
        models_ = triggers.mapped("model_id")
        for rule in self:
            rule.allowed_model_ids = models_

    @api.onchange("model_id")
    def _onchange_model_id(self):
        # Reset the action when the model changes if it no longer matches.
        if self.trigger_id and self.trigger_id.model_id \
                and self.trigger_id.model_id != self.model_id:
            self.trigger_id = False

    @api.onchange("trigger_id")
    def _onchange_trigger_id(self):
        self.trigger_event = self.trigger_id.code or False

    condition_domain = fields.Char(
        string="Condition (Domain)",
        help="Odoo domain evaluated against the triggering record.",
    )
    # Python is evaluated by the engine with superuser rights, so only
    # administrators may author it (same policy as server actions).
    condition_python = fields.Text(
        string="Condition (Python)",
        groups="base.group_system",
        help="Optional boolean expression evaluated via safe_eval. "
        "Context: record, user, datetime, relativedelta.",
    )
    level_ids = fields.One2many(
        "approval.engine.rule.level", "rule_id", string="Approval Levels"
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company,
        help="Leave empty to apply the rule to documents of every company.",
    )

    @api.constrains("trigger_event")
    def _check_trigger(self):
        for rule in self:
            if not rule.trigger_event:
                raise ValidationError(
                    _("Please choose the action that requires approval.")
                )

    @api.constrains("condition_domain", "model_id")
    def _check_condition_domain(self):
        for rule in self:
            if not rule.condition_domain or rule.condition_domain.strip() == "[]":
                continue
            try:
                domain = safe_eval(rule.condition_domain)
                if not isinstance(domain, list):
                    raise ValueError(_("the condition must be a list"))
                self.env[rule.model_name].sudo().search_count(domain, limit=1)
            except Exception as exc:
                raise ValidationError(
                    _("Invalid condition on rule '%(rule)s': %(error)s",
                      rule=rule.name, error=exc)
                ) from exc

    @api.constrains("condition_python")
    def _check_condition_python(self):
        for rule in self.sudo():
            if rule.condition_python:
                error = test_python_expr(rule.condition_python.strip(), mode="eval")
                if error:
                    raise ValidationError(
                        _("Invalid Python condition on rule '%(rule)s': %(error)s",
                          rule=rule.name, error=error)
                    )

    @api.constrains("level_ids")
    def _check_levels(self):
        for rule in self:
            if not rule.level_ids:
                raise ValidationError(
                    _("Rule '%s' must define at least one approval level.", rule.name)
                )
            seqs = rule.level_ids.mapped("sequence")
            if len(seqs) != len(set(seqs)):
                raise ValidationError(
                    _("Approval levels in rule '%s' must have unique sequences.",
                      rule.name)
                )

    # --- Engine hooks -------------------------------------------------------

    def _match_record(self, record):
        """Return True if *record* matches this rule's conditions.

        Empty conditions always match. A condition that cannot be evaluated
        (e.g. it references a field that was later removed) *matches*: the
        engine fails closed, so a broken rule holds documents for approval
        instead of silently letting them through.
        """
        self.ensure_one()
        rule = self.sudo()
        domain_str = rule.condition_domain
        if domain_str and domain_str.strip() not in ("", "[]"):
            try:
                domain = safe_eval(domain_str)
                if not isinstance(domain, list):
                    raise ValueError("condition_domain is not a list")
                if not record.sudo().search_count([("id", "=", record.id)] + domain):
                    return False
            except Exception:
                _logger.exception(
                    "Approval rule %s: cannot evaluate condition_domain on %s; "
                    "requiring approval.", rule.id, record,
                )
                return True
        if rule.condition_python:
            ctx = {
                "record": record,
                "user": self.env.user,
                "datetime": datetime,
                "relativedelta": relativedelta,
            }
            try:
                return bool(safe_eval(rule.condition_python.strip(), ctx))
            except Exception:
                _logger.exception(
                    "Approval rule %s: cannot evaluate condition_python on %s; "
                    "requiring approval.", rule.id, record,
                )
                return True
        return True

    def _approval_resolve_approvers(self, level, record=None):
        """Return a ``res.users`` recordset for the given ``approval.engine.rule.level``.

        :param level: ``approval.engine.rule.level`` record (must belong to ``self``).
        :param record: optional source record used as ``record`` in expression
                       context.  Pass the governed record so that dynamic
                       expressions can reference it.
        :returns: ``res.users`` recordset (may be empty).
        """
        self.ensure_one()
        env = self.env
        level = level.sudo()

        if level.approver_type == "group":
            # all_user_ids = explicit + implied members (anyone who effectively
            # has the group). Odoo 19 renamed `users` -> user_ids/all_user_ids.
            return level.approver_group_id.all_user_ids if level.approver_group_id else env["res.users"]

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
                    _("Error evaluating approver expression on level '%(level)s': %(error)s",
                      level=level.name or level.sequence, error=exc)
                ) from exc

            if not isinstance(result, models.BaseModel) or result._name != "res.users":
                raise ValidationError(
                    _("Approver expression on level '%s' must return a res.users recordset.",
                      level.name or level.sequence)
                )
            return result

        return env["res.users"]
