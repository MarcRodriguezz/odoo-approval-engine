# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ApprovalDecisionWizard(models.TransientModel):
    """Approve/reject with comment.  Delegates the actual state-machine work
    to approval.engine.request._register_decision."""

    _name = "approval.decision.wizard"
    _description = "Approval Decision Wizard"

    request_id = fields.Many2one("approval.engine.request", required=True, readonly=True)
    line_id = fields.Many2one("approval.engine.request.line", readonly=True)
    comment = fields.Text(string="Comment")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        active_model = ctx.get("active_model")
        active_id = ctx.get("active_id")

        if active_model == "approval.engine.request.line" and active_id:
            line = self.env["approval.engine.request.line"].browse(active_id)
            if "line_id" in fields_list:
                res["line_id"] = line.id
            if "request_id" in fields_list:
                res["request_id"] = line.request_id.id

        elif active_model == "approval.engine.request" and active_id:
            request = self.env["approval.engine.request"].browse(active_id)
            if "request_id" in fields_list:
                res["request_id"] = request.id
            # Pick the current user's pending line, if any
            if "line_id" in fields_list:
                pending_line = request.line_ids.filtered(
                    lambda l: l.approver_id == self.env.user
                    and l.decision == "pending"
                )
                if pending_line:
                    res["line_id"] = pending_line[0].id

        return res

    def action_approve(self):
        """Register an 'approved' decision for this line."""
        self.ensure_one()
        if not self.line_id:
            raise UserError(_("No approval line selected."))
        self.request_id._register_decision(
            self.line_id, "approved", self.comment
        )
        return {"type": "ir.actions.act_window_close"}

    def action_reject(self):
        """Register a 'rejected' decision for this line."""
        self.ensure_one()
        if not self.line_id:
            raise UserError(_("No approval line selected."))
        self.request_id._register_decision(
            self.line_id, "rejected", self.comment
        )
        return {"type": "ir.actions.act_window_close"}


class ApprovalRequestLineInboxButton(models.Model):
    """Adds the inbox 'Decide' button helper to approval.engine.request.line.
    This is a pure UI/action method; business logic lives in approval.request."""

    _inherit = "approval.engine.request.line"

    def action_open_decision_wizard(self):
        """Open the decision wizard pre-filled for this line."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Record Decision"),
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


class ApprovalRequestSourceButton(models.Model):
    """Adds the 'Open Source Record' smart-button helper to approval.engine.request.
    This is a pure UI/navigation method."""

    _inherit = "approval.engine.request"

    def action_open_source_record(self):
        """Open the linked source record in a form view."""
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
