# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ApprovalRequestLine(models.Model):
    """One line per APPROVAL STAGE (not per candidate user).

    A stage lists its *candidate* approvers (a group / expression) and records
    who actually approved (``approved_by_ids``). The stage is cleared once
    ``min_approvals`` distinct candidates have approved.
    """

    _name = "approval.engine.request.line"
    _description = "Approval Request Stage"
    _order = "level, id"

    request_id = fields.Many2one(
        "approval.engine.request", string="Request",
        required=True, ondelete="cascade",
    )
    level = fields.Integer(string="Stage Order", required=True, default=1)
    min_approvals = fields.Integer(string="Required Approvals", default=1)
    approver_group_id = fields.Many2one(
        "res.groups", string="Approver group",
        help="Any member of this group (incl. implied membership) may approve "
        "this stage — evaluated live, so adding a user to the group lets them "
        "approve immediately.",
    )
    candidate_user_ids = fields.Many2many(
        "res.users", "approval_line_candidate_rel", "line_id", "user_id",
        string="Can approve",
        help="Explicit users allowed to approve (used for expression-based "
        "approvers; group approvers are matched live via approver_group_id).",
    )
    approved_by_ids = fields.Many2many(
        "res.users", "approval_line_approved_rel", "line_id", "user_id",
        string="Approved by", copy=False,
        help="Users who have approved this stage so far.",
    )
    approver_id = fields.Many2one(
        "res.users", string="Decided by", copy=False,
        help="User who closed this stage (last approval, or the rejecter).",
    )
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
    stage_label = fields.Char(
        string="Stage", compute="_compute_stage_label",
        help="The approval stage this line belongs to.",
    )

    @api.depends("request_id.res_model", "request_id.res_id")
    def _compute_source_document(self):
        for line in self:
            record = line.request_id._get_source_record() if line.request_id else False
            line.source_document = record.sudo().display_name if record else ""

    @api.depends("level", "request_id.rule_id")
    def _compute_stage_label(self):
        for line in self:
            lvl = line.request_id.rule_id.level_ids.filtered(
                lambda l: l.sequence == line.level
            )[:1]
            line.stage_label = (lvl.name if lvl and lvl.name
                                else _("Stage %s") % line.level)

    # --- Candidate resolution (live) ---------------------------------------
    def _effective_candidate_users(self):
        """Users who may currently approve these stages: live members of the
        approver group (explicit + implied) plus any explicit candidates."""
        users = self.env["res.users"]
        for line in self:
            line = line.with_context(active_test=False)
            users |= line.candidate_user_ids
            if line.approver_group_id:
                users |= line.approver_group_id.all_user_ids
        return users

    # --- Permission helper --------------------------------------------------
    def _check_can_decide(self):
        """Only someone who may currently approve this stage (or an Approvals
        Manager) may decide."""
        self.ensure_one()
        user = self.env.user
        if user.has_group("odoo_approval_engine.group_approval_manager"):
            return
        if user not in self._effective_candidate_users():
            raise UserError(_("You are not an approver for this stage."))
        if user in self.with_context(active_test=False).approved_by_ids:
            raise UserError(_("You have already approved this stage."))

    # --- One-click inbox actions -------------------------------------------
    def action_quick_approve(self):
        """Approve this stage in one click (no comment)."""
        self.ensure_one()
        self._check_can_decide()
        actor = self.env.user
        # sudo: advancing the workflow creates the next stage's line, which a
        # plain approver could not do under their own rights.
        self.request_id.sudo()._register_decision(
            self.sudo(), "approved", False, actor=actor,
        )
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
        """Open the decision dialog pre-filled for this stage (Reject / comment)."""
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
