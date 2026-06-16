# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ApprovalRequestLine(models.Model):
    _name = "approval.engine.request.line"
    _description = "Approval Request Line"
    _order = "level, id"

    request_id = fields.Many2one(
        "approval.engine.request", string="Request",
        required=True, ondelete="cascade",
    )
    level = fields.Integer(string="Step", required=True, default=1)
    approver_id = fields.Many2one("res.users", string="Approver", required=True)
    decision = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="pending",
        required=True,
    )
    decision_date = fields.Datetime(string="Decision Date")
    comment = fields.Text(string="Comment")

    # --- Display helpers (related/computed) for a friendly, generic inbox ---
    rule_id = fields.Many2one(related="request_id.rule_id", string="Rule", store=True)
    requested_by = fields.Many2one(
        related="request_id.requested_by", string="Requested by", store=True,
    )
    request_date = fields.Datetime(related="request_id.request_date", string="Requested on")
    request_state = fields.Selection(related="request_id.state", string="Request Status")
    company_id = fields.Many2one(related="request_id.company_id", store=True)
    source_document = fields.Char(
        string="Document", compute="_compute_source_document",
        help="The business document this approval is about.",
    )

    @api.depends("request_id.res_model", "request_id.res_id")
    def _compute_source_document(self):
        for line in self:
            record = line.request_id._get_source_record() if line.request_id else False
            line.source_document = record.sudo().display_name if record else ""

    # --- One-click inbox actions -------------------------------------------
    def _check_can_decide(self):
        """Only the assigned approver (or an Approvals Manager) may decide."""
        self.ensure_one()
        is_manager = self.env.user.has_group(
            "odoo_approval_engine.group_approval_manager"
        )
        if self.env.user != self.approver_id and not is_manager:
            raise UserError(
                _("Only the assigned approver can decide on this step.")
            )

    def action_quick_approve(self):
        """Approve this step in one click (no comment)."""
        self.ensure_one()
        self._check_can_decide()
        # sudo: the approval is the authorization; advancing the workflow
        # generates lines for the next step's approvers, which a plain user
        # could not create under their own rights.
        self.request_id.sudo()._register_decision(self.sudo(), "approved", False)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Approved"),
                "message": _("Your approval has been recorded."),
                "type": "success",
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_open_decision_wizard(self):
        """Open the decision dialog pre-filled for this line (used for Reject
        and for adding a comment)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Review Approval"),
            "res_model": "approval.decision.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "approval.engine.request.line",
                "active_id": self.id,
                "default_line_id": self.id,
                "default_request_id": self.request_id.id,
            },
        }

    def action_open_document(self):
        """Open the underlying business document (sale order, etc.)."""
        self.ensure_one()
        return self.request_id.action_open_source_record()
