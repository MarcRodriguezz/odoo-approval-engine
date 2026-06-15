# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ApprovalRequest(models.Model):
    _name = "approval.request"
    _description = "Approval Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "request_date desc, id desc"

    name = fields.Char(
        default="/", required=True, copy=False, readonly=True, index=True
    )
    rule_id = fields.Many2one("approval.rule", required=True, ondelete="restrict")
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
        "approval.request.line", "request_id", string="Approval Lines"
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
                    "approval.request"
                ) or "/"
        return super().create(vals_list)

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
        """Return the ``approval.rule.level`` for *level_sequence* within rule."""
        self.ensure_one()
        levels = self.rule_id.level_ids.filtered(
            lambda l: l.sequence == level_sequence
        )
        return levels[0] if levels else False

    def _generate_lines_for_level(self, level_obj):
        """Create ``approval.request.line`` records for *level_obj*.

        Resolves approvers via the rule's ``_approval_resolve_approvers`` and
        creates one line per approver at ``level_obj.sequence``.
        """
        self.ensure_one()
        source_record = self._get_source_record()
        approvers = self.rule_id._approval_resolve_approvers(level_obj, record=source_record)
        Line = self.env["approval.request.line"]
        for approver in approvers:
            Line.create(
                {
                    "request_id": self.id,
                    "level": level_obj.sequence,
                    "approver_id": approver.id,
                    "decision": "pending",
                }
            )

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
            approvers = approver_lines.mapped("approver_id")
            if approvers:
                request.message_post(
                    body=_("Your approval is required for request %s.") % request.name,
                    partner_ids=approvers.mapped("partner_id").ids,
                    subtype_xmlid="mail.mt_comment",
                )

    def _register_decision(self, line, decision, comment=False):
        """Record an approver decision and advance or finalize the request.

        :param line: ``approval.request.line`` to record decision on.
        :param decision: ``'approved'`` or ``'rejected'``.
        :param comment: optional free-text comment.
        """
        self.ensure_one()

        if line.request_id != self:
            raise UserError(_("This line does not belong to the current request."))

        if self.state != "pending":
            raise UserError(
                _("Cannot register a decision on a request that is not pending.")
            )

        # Write decision on the line
        line.write(
            {
                "decision": decision,
                "decision_date": fields.Datetime.now(),
                "comment": comment or False,
            }
        )

        # Post chatter message
        self.message_post(
            body=_(
                "%(approver)s %(verb)s level %(level)s.%(comment)s"
            ) % {
                "approver": line.approver_id.name,
                "verb": _("approved") if decision == "approved" else _("rejected"),
                "level": line.level,
                "comment": (" — " + comment) if comment else "",
            },
            subtype_xmlid="mail.mt_note",
        )

        # Handle rejection immediately
        if decision == "rejected":
            self._finalize(approved=False)
            return

        # Check if current level has enough approvals
        level_obj = self._get_level_obj(self.current_level)
        if not level_obj:
            # No matching level definition — finalize as approved (safety fallback)
            self._finalize(approved=True)
            return

        approved_count = len(
            self.line_ids.filtered(
                lambda l: l.level == self.current_level and l.decision == "approved"
            )
        )

        if approved_count >= level_obj.min_approvals:
            # Check if there is a next level
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
        approvers = approver_lines.mapped("approver_id")
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
        source = self._get_source_record()
        if source:
            if approved and hasattr(source, "_on_approval_approved"):
                source._on_approval_approved()
            elif not approved and hasattr(source, "_on_approval_rejected"):
                source._on_approval_rejected()

    def action_cancel(self):
        self.write({"state": "cancelled"})
