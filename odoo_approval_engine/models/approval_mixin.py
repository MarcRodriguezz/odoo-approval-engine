# -*- coding: utf-8 -*-
import secrets

from odoo import models, fields, _

# Value of the ``approval_bypass`` context key that lets the engine run a held
# action after approval. A per-process secret instead of ``True``: a client can
# put any JSON value in the context of an RPC call, but cannot guess this one.
APPROVAL_BYPASS_TOKEN = secrets.token_urlsafe(32)


def approval_bypassed(env):
    """True when the current call was started by the engine itself."""
    return env.context.get("approval_bypass") == APPROVAL_BYPASS_TOKEN


class ApprovalEngineMixin(models.AbstractModel):
    """Optional mixin for models that want to *block* a business action
    (e.g. confirmation) until approved, and expose approval_engine_state in their UI.

    NOTE: the matching engine itself is generic and also runs on ANY model for
    on_create / on_write rules via the global ``base`` hook (see base_approval.py)
    — inheriting this mixin is only required to (a) gate a custom action and
    (b) show the approval state on the record's own views.
    """

    _name = "approval.engine.mixin"
    _description = "Approval Engine Mixin"

    approval_engine_request_ids = fields.One2many(
        "approval.engine.request",
        compute="_compute_approval_requests",
        string="Approval Requests",
    )
    approval_engine_state = fields.Selection(
        [
            ("none", "No Approval"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        compute="_compute_approval_requests",
        string="Engine Approval State",
    )

    def _compute_approval_requests(self):
        # sudo: display-only field; any user who can see the record can compute
        # it. The approval.engine.request views still enforce their own rules.
        # One query for the whole recordset (list views show this column).
        Request = self.env["approval.engine.request"].sudo()
        ids = [rid for rid in self._origin.ids if rid]
        by_res_id = {}
        if ids:
            for request in Request.search(
                [("res_model", "=", self._name), ("res_id", "in", ids)]
            ):
                by_res_id.setdefault(request.res_id, []).append(request.id)
        for record in self:
            requests = Request.browse(by_res_id.get(record._origin.id, []))
            record.approval_engine_request_ids = requests
            states = set(requests.mapped("state"))
            if "pending" in states:
                record.approval_engine_state = "pending"
            elif "rejected" in states:
                record.approval_engine_state = "rejected"
            elif "approved" in states:
                record.approval_engine_state = "approved"
            else:
                record.approval_engine_state = "none"

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

    # --- Bypass flag used to run the held action after approval ------------
    def _approval_is_bypassed(self):
        """True when the engine is running the action after approval; gated
        methods then call ``super()`` without re-evaluating the rules."""
        return approval_bypassed(self.env)

    def _approval_bypass(self):
        """Return ``self`` in the context that runs the gated action for real."""
        return self.with_context(approval_bypass=APPROVAL_BYPASS_TOKEN)

    # --- Source-record hooks (overridden by integration modules) ------------
    def _on_approval_approved(self):
        """Called by the engine when a request is fully approved."""
        return True

    def _on_approval_rejected(self):
        """Called by the engine when a request is rejected."""
        return True

    def _approval_split_blocked(self, trigger_event):
        """Evaluate the rules for every record and return the ones that must
        wait for approval. Integrations run the real action on the rest, so a
        batch action only holds the documents that actually need approval."""
        blocked = self.browse()
        for record in self:
            if record._evaluate_approval_rules(trigger_event):
                blocked |= record
        return blocked

    def _approval_block_action(self, done=None):
        """Notification telling the user which documents are held for approval.

        :param done: optional recordset of documents processed normally in the
                     same batch (mentioned so the user knows they went through).
        """
        names = ", ".join(self.mapped("display_name"))
        if done:
            message = _(
                "Held for approval: %(held)s. The other %(count)s document(s) were processed.",
                held=names, count=len(done),
            )
        elif len(self) > 1:
            message = _("Held for approval: %s.", names)
        else:
            message = _("This operation requires approval and is now pending.")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Approval Required"),
                "message": message,
                "type": "warning",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }
