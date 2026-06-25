# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class ApprovalRequest(models.Model):
    _name = "approval.engine.request"
    _description = "Approval Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "request_date desc, id desc"

    name = fields.Char(
        default="/", required=True, copy=False, readonly=True, index=True
    )
    rule_id = fields.Many2one("approval.engine.rule", required=True, ondelete="restrict")
    res_model = fields.Char(string="Source Model", required=True, index=True)
    res_id = fields.Integer(string="Source ID", required=True, index=True)
    resource_ref = fields.Reference(
        selection="_selection_resource_ref",
        string="Source Record",
        compute="_compute_resource_ref",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    requested_by = fields.Many2one(
        "res.users", default=lambda self: self.env.user, tracking=True
    )
    request_date = fields.Datetime(default=fields.Datetime.now)
    current_level = fields.Integer(default=1)
    line_ids = fields.One2many(
        "approval.engine.request.line", "request_id", string="Approval Lines"
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company
    )

    @api.model
    def _selection_resource_ref(self):
        models_ = self.env["ir.model"].sudo().search([])
        return [(m.model, m.name) for m in models_]

    @api.depends("res_model", "res_id")
    def _compute_resource_ref(self):
        for rec in self:
            if rec.res_model and rec.res_id:
                rec.resource_ref = "%s,%s" % (rec.res_model, rec.res_id)
            else:
                rec.resource_ref = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "approval.engine.request"
                ) or "/"
        return super().create(vals_list)

    # --- Shared engine (used by the mixin AND the generic base hook) --------

    @api.model
    def _evaluate_rules_for(self, record, trigger_event):
        """Evaluate active rules for *record* and *trigger_event*.

        Generic: works for ANY model. Returns True if a matching rule fired
        (an open request already existed or a new one was created).
        """
        record.ensure_one()
        Rule = self.env["approval.engine.rule"].sudo()
        rules = Rule.search(
            [
                ("model_name", "=", record._name),
                ("trigger_event", "=", trigger_event),
                ("active", "=", True),
            ],
            order="sequence, id",
        )
        ctx = {
            "record": record,
            "user": self.env.user,
            "datetime": datetime,
            "relativedelta": relativedelta,
        }
        for rule in rules:
            if not rule._match_record(record):
                continue
            if rule.condition_python:
                try:
                    matched = bool(safe_eval(rule.condition_python, dict(ctx)))
                except Exception:
                    matched = False
                if not matched:
                    continue
            existing = self.sudo().search(
                [
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("rule_id", "=", rule.id),
                    ("state", "=", "pending"),
                ],
                limit=1,
            )
            if existing:
                return True
            self.sudo()._create_request_for(record, rule)
            return True
        return False

    @api.model
    def _create_request_for(self, record, rule):
        """Create a pending request for *record* under *rule*, generate the
        first step's lines and notify approvers. Returns the request."""
        request = self.sudo().create({
            "rule_id": rule.id,
            "res_model": record._name,
            "res_id": record.id,
            "state": "pending",
            "current_level": 1,
            "requested_by": self.env.user.id,
        })
        level_1 = rule.level_ids.filtered(lambda l: l.sequence == 1)
        if level_1:
            request._generate_lines_for_level(level_1[0])
        request.message_post(
            body=_("Approval request created for %s (rule: %s).")
            % (record.display_name, rule.name),
            subtype_xmlid="mail.mt_note",
        )
        approvers = request.line_ids.filtered(lambda l: l.level == 1).mapped(
            "approver_id"
        )
        if approvers:
            request.message_post(
                body=_("Please review and approve the request: %s") % request.name,
                partner_ids=approvers.mapped("partner_id").ids,
                subtype_xmlid="mail.mt_comment",
            )
        return request

    # --- Private helpers ----------------------------------------------------

    def _get_source_record(self):
        """Return the source record (governed model instance) or False."""
        self.ensure_one()
        if self.res_model and self.res_id:
            try:
                return self.env[self.res_model].browse(self.res_id)
            except Exception:
                return False
        return False

    def _get_level_obj(self, level_sequence):
        """Return the ``approval.engine.rule.level`` for *level_sequence* within rule."""
        self.ensure_one()
        levels = self.rule_id.level_ids.filtered(
            lambda l: l.sequence == level_sequence
        )
        return levels[0] if levels else False

    def _generate_lines_for_level(self, level_obj):
        """Ensure exactly ONE fresh pending stage line for *level_obj*.

        Idempotent: if a line already exists for this stage it is reset and
        reused (and any accidental duplicates removed), so the workflow can
        never accumulate duplicate stage lines.
        """
        self.ensure_one()
        source_record = self._get_source_record()
        candidates = self.rule_id._approval_resolve_approvers(
            level_obj, record=source_record
        )
        vals = {
            "min_approvals": level_obj.min_approvals or 1,
            "candidate_user_ids": [(6, 0, candidates.ids)],
            "approved_by_ids": [(5, 0, 0)],
            "approver_id": False,
            "decision": "pending",
            "decision_date": False,
            "comment": False,
        }
        existing = self.line_ids.filtered(lambda l: l.level == level_obj.sequence)
        if existing:
            existing[1:].unlink()  # drop any duplicates
            existing[0].write(vals)
            return existing[0]
        vals.update({"request_id": self.id, "level": level_obj.sequence})
        return self.env["approval.engine.request.line"].create(vals)

    # --- State machine ------------------------------------------------------

    def action_submit(self):
        """Move a draft request to pending and generate level-1 lines."""
        for request in self:
            if request.state != "draft":
                raise UserError(
                    _("Only draft requests can be submitted (request %s is '%s').")
                    % (request.name, request.state)
                )
            request.write({"state": "pending", "current_level": 1})

            level_1 = request._get_level_obj(1)
            if level_1:
                request._generate_lines_for_level(level_1)

            request.message_post(
                body=_("Request submitted for approval (level 1)."),
                subtype_xmlid="mail.mt_note",
            )

            # Notify level-1 approvers
            approver_lines = request.line_ids.filtered(lambda l: l.level == 1)
            approvers = approver_lines.mapped("candidate_user_ids")
            if approvers:
                request.message_post(
                    body=_("Your approval is required for request %s.") % request.name,
                    partner_ids=approvers.mapped("partner_id").ids,
                    subtype_xmlid="mail.mt_comment",
                )

    def _register_decision(self, line, decision, comment=False, actor=None):
        """Record a decision on a *stage* line by *actor*.

        Approve: the actor is added to ``approved_by_ids``; once the stage has
        ``min_approvals`` distinct approvals it is cleared and the request
        advances (or is finalized). Reject: the stage and the request are
        rejected immediately.
        """
        self.ensure_one()
        actor = actor or self.env.user

        if line.request_id != self:
            raise UserError(_("This line does not belong to the current request."))
        if self.state != "pending":
            raise UserError(
                _("Cannot register a decision on a request that is not pending.")
            )

        # --- Rejection: immediate ------------------------------------------
        if decision == "rejected":
            line.write({
                "decision": "rejected",
                "approver_id": actor.id,
                "decision_date": fields.Datetime.now(),
                "comment": comment or False,
            })
            self.message_post(
                body=_("%(user)s rejected stage “%(stage)s”.%(comment)s") % {
                    "user": actor.name,
                    "stage": line.stage_label,
                    "comment": (" — " + comment) if comment else "",
                },
                subtype_xmlid="mail.mt_note",
            )
            self._finalize(approved=False)
            return

        # --- Approval ------------------------------------------------------
        # active_test=False so archived users (incl. the test superuser) are
        # counted; approvers are normally active so this is a no-op in prod.
        already = line.with_context(active_test=False).approved_by_ids
        if actor not in already:
            line.approved_by_ids = [(4, actor.id)]
        vals = {"decision_date": fields.Datetime.now()}
        if comment:
            vals["comment"] = comment
        line.write(vals)
        self.message_post(
            body=_("%(user)s approved stage “%(stage)s”.%(comment)s") % {
                "user": actor.name,
                "stage": line.stage_label,
                "comment": (" — " + comment) if comment else "",
            },
            subtype_xmlid="mail.mt_note",
        )

        # Enough approvals for this stage?
        approved_count = len(line.with_context(active_test=False).approved_by_ids)
        if approved_count < (line.min_approvals or 1):
            return  # stage stays pending, more approvals needed

        line.write({"decision": "approved", "approver_id": actor.id})
        next_levels = self.rule_id.level_ids.filtered(
            lambda l: l.sequence > self.current_level
        ).sorted("sequence")
        if next_levels:
            self._advance_level()
        else:
            self._finalize(approved=True)

    def _advance_level(self):
        """Bump ``current_level`` to the next level and generate its lines."""
        self.ensure_one()

        next_levels = self.rule_id.level_ids.filtered(
            lambda l: l.sequence > self.current_level
        ).sorted("sequence")

        if not next_levels:
            # Nothing to advance to; finalize
            self._finalize(approved=True)
            return

        next_level = next_levels[0]
        self.write({"current_level": next_level.sequence})
        self._generate_lines_for_level(next_level)

        self.message_post(
            body=_("Advanced to approval level %s.") % next_level.sequence,
            subtype_xmlid="mail.mt_note",
        )

        # Notify next-level approvers
        approver_lines = self.line_ids.filtered(
            lambda l: l.level == next_level.sequence
        )
        approvers = approver_lines.mapped("candidate_user_ids")
        if approvers:
            self.message_post(
                body=_("Your approval is required for request %s (level %s).")
                % (self.name, next_level.sequence),
                partner_ids=approvers.mapped("partner_id").ids,
                subtype_xmlid="mail.mt_comment",
            )

    def _finalize(self, approved):
        """Set the terminal state and call source-record hooks.

        :param approved: ``True`` → state ``approved``; ``False`` → ``rejected``.
        """
        self.ensure_one()
        new_state = "approved" if approved else "rejected"
        self.write({"state": new_state})

        # Post chatter message
        if approved:
            self.message_post(
                body=_("Request fully approved."),
                subtype_xmlid="mail.mt_note",
            )
        else:
            self.message_post(
                body=_("Request rejected."),
                subtype_xmlid="mail.mt_note",
            )

        # Notify requester
        if self.requested_by and self.requested_by.partner_id:
            self.message_post(
                body=_(
                    "Your approval request %s has been %s."
                ) % (self.name, _("approved") if approved else _("rejected")),
                partner_ids=[self.requested_by.partner_id.id],
                subtype_xmlid="mail.mt_comment",
            )

        # Call source-record hook (governed models carry it via the mixin;
        # guard so requests against non-governed models stay robust).
        # sudo: the approval itself is the authorization, so the held action
        # runs regardless of the approver's rights on the source model.
        source = self._get_source_record()
        if source:
            source = source.sudo()
            if approved and hasattr(source, "_on_approval_approved"):
                source._on_approval_approved()
            elif not approved and hasattr(source, "_on_approval_rejected"):
                source._on_approval_rejected()

    def action_cancel(self):
        for request in self:
            request.write({"state": "cancelled"})
            request.message_post(
                body=_("Approval request cancelled."),
                subtype_xmlid="mail.mt_note",
            )

    def action_step_back(self):
        """Send the request back one stage ("undo"). Press repeatedly to go
        further back. From a finished/cancelled state it reopens the current
        (last) stage; from a pending state it returns to the previous stage,
        dropping any later stages.
        """
        for request in self:
            if request.state in ("approved", "rejected", "cancelled"):
                target = max(1, request.current_level)
                request.state = "pending"
            else:
                target = max(1, request.current_level - 1)

            # Drop any stage lines after the target, then (re)build the target.
            request.line_ids.filtered(lambda l: l.level > target).unlink()
            level = request._get_level_obj(target) or request._get_level_obj(1)
            request.current_level = level.sequence if level else target
            tline = request._generate_lines_for_level(level) if level else False

            request.message_post(
                body=_("Sent back to stage “%s”.")
                % (tline.stage_label if tline else target),
                subtype_xmlid="mail.mt_note",
            )
