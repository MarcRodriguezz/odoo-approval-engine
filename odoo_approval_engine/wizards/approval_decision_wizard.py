# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ApprovalDecisionWizard(models.TransientModel):
    """Friendly approve/reject dialog. Delegates the state-machine work to
    approval.engine.request._register_decision."""

    _name = "approval.decision.wizard"
    _description = "Approval Decision Wizard"

    request_id = fields.Many2one(
        "approval.engine.request", required=True, readonly=True,
    )
    line_id = fields.Many2one("approval.engine.request.line", readonly=True)
    comment = fields.Text(string="Comment / Reason")

    # Read-only context for the approver (so they know what they decide on).
    document = fields.Char(related="line_id.source_document", string="Document")
    rule_id = fields.Many2one(related="line_id.rule_id", string="Rule")
    requested_by = fields.Many2one(related="line_id.requested_by", string="Requested by")
    level = fields.Integer(related="line_id.level", string="Step")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        active_model = ctx.get("active_model")
        active_id = ctx.get("active_id")

        if active_model == "approval.engine.request.line" and active_id:
            line = self.env["approval.engine.request.line"].browse(active_id)
            res.setdefault("line_id", line.id)
            res.setdefault("request_id", line.request_id.id)

        elif active_model == "approval.engine.request" and active_id:
            request = self.env["approval.engine.request"].browse(active_id)
            res.setdefault("request_id", request.id)
            pending_line = request.line_ids.filtered(
                lambda l: l.decision == "pending"
                and self.env.user in l._effective_candidate_users()
            )
            if pending_line:
                res.setdefault("line_id", pending_line[0].id)

        return res

    def action_approve(self):
        """Register an 'approved' decision for this line."""
        self.ensure_one()
        if not self.line_id:
            raise UserError(_("No approval step selected."))
        self.line_id._check_can_decide()
        actor = self.env.user
        # sudo: see approval.engine.request.line.action_quick_approve.
        self.request_id.sudo()._register_decision(
            self.line_id.sudo(), "approved", self.comment, actor=actor
        )
        return {"type": "ir.actions.act_window_close"}

    def action_reject(self):
        """Register a 'rejected' decision for this line. A reason is required."""
        self.ensure_one()
        if not self.line_id:
            raise UserError(_("No approval step selected."))
        self.line_id._check_can_decide()
        if not (self.comment and self.comment.strip()):
            raise UserError(_("Please provide a reason for rejecting this request."))
        actor = self.env.user
        self.request_id.sudo()._register_decision(
            self.line_id.sudo(), "rejected", self.comment, actor=actor
        )
        return {"type": "ir.actions.act_window_close"}


class ApprovalRequestSourceButton(models.Model):
    """Smart-button helper to open the source record from a request. Generic:
    works for any governed model (sale.order, purchase.order, ...)."""

    _inherit = "approval.engine.request"

    def action_open_source_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            raise UserError(_("No source record linked to this request."))
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }
