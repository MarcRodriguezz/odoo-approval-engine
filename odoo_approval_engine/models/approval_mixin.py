# -*- coding: utf-8 -*-
from odoo import models, fields, _


class ApprovalEngineMixin(models.AbstractModel):
    """Optional mixin for models that want to *block* a business action
    (e.g. confirmation) until approved, and expose approval_state in their UI.

    NOTE: the matching engine itself is generic and also runs on ANY model for
    on_create / on_write rules via the global ``base`` hook (see base_approval.py)
    — inheriting this mixin is only required to (a) gate a custom action and
    (b) show the approval state on the record's own views.
    """

    _name = "approval.engine.mixin"
    _description = "Approval Engine Mixin"

    approval_request_ids = fields.One2many(
        "approval.engine.request",
        compute="_compute_approval_requests",
        string="Approval Requests",
    )
    approval_state = fields.Selection(
        [
            ("none", "No Approval"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        compute="_compute_approval_requests",
        string="Approval State",
    )

    def _compute_approval_requests(self):
        # sudo: display-only field; any user who can see the record can compute
        # it. The approval.engine.request views still enforce their own rules.
        Request = self.env["approval.engine.request"].sudo()
        for record in self:
            requests = Request.search(
                [("res_model", "=", record._name), ("res_id", "=", record.id)]
            )
            record.approval_request_ids = requests
            if not requests:
                record.approval_state = "none"
            elif requests.filtered(lambda r: r.state == "pending"):
                record.approval_state = "pending"
            elif requests.filtered(lambda r: r.state == "rejected"):
                record.approval_state = "rejected"
            elif requests.filtered(lambda r: r.state == "approved"):
                record.approval_state = "approved"
            else:
                record.approval_state = "none"

    # --- Engine entry points (delegate to the shared engine) ----------------
    def _evaluate_approval_rules(self, trigger_event):
        """Return True if the business action must be blocked pending approval."""
        self.ensure_one()
        return self.env["approval.engine.request"]._evaluate_rules_for(
            self, trigger_event
        )

    def _approval_match_domain(self, rule):
        """Kept for backward compatibility; delegates to the rule."""
        return rule._match_record(self)

    def _approval_create_request(self, rule):
        return self.env["approval.engine.request"]._create_request_for(self, rule)

    # --- Source-record hooks (overridden by integration modules) ------------
    def _on_approval_approved(self):
        """Called by the engine when a request is fully approved."""
        return True

    def _on_approval_rejected(self):
        """Called by the engine when a request is rejected."""
        return True

    def _approval_block_action(self):
        """Return a notification telling the user the operation is pending."""
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Approval Required"),
                "message": _("This operation requires approval and is now pending."),
                "type": "warning",
                "sticky": False,
            },
        }
