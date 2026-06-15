# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.tools.safe_eval import safe_eval


class ApprovalEngineMixin(models.AbstractModel):
    """Inherit this mixin in any model that should be governed by the
    approval engine.
    integration modules override the hooks at the bottom.
    """

    _name = "approval.engine.mixin"
    _description = "Approval Engine Mixin"

    approval_request_ids = fields.One2many(
        "approval.request",
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
        Request = self.env["approval.request"]
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

    # --- Engine entry points -----------------------------------------------

    def _evaluate_approval_rules(self, trigger_event):
        """Evaluate matching rules for this record and trigger_event.

        Returns True if the business action must be blocked (a rule matched
        and either an existing open request was found or a new one was
        created).  Returns False when no rule matched.
        """
        self.ensure_one()
        rules = self.env["approval.rule"].search(
            [
                ("model_name", "=", self._name),
                ("trigger_event", "=", trigger_event),
                ("active", "=", True),
            ],
            order="sequence, id",
        )

        ctx = {
            "record": self,
            "user": self.env.user,
            "datetime": datetime,
            "relativedelta": relativedelta,
        }

        for rule in rules:
            # 1. Domain check
            if not self._approval_match_domain(rule):
                continue

            # 2. Python condition check
            if rule.condition_python:
                try:
                    result = safe_eval(rule.condition_python, ctx)
                except Exception:
                    result = False
                if not result:
                    continue

            # 3. Duplicate open-request guard
            existing = self.env["approval.request"].search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("rule_id", "=", rule.id),
                    ("state", "=", "pending"),
                ],
                limit=1,
            )
            if existing:
                return True

            # 4. Create request and block the action
            self._approval_create_request(rule)
            return True

        return False

    def _approval_match_domain(self, rule):
        """Return True if this record matches *rule*'s condition_domain.

        An empty domain always matches.  Otherwise the stored domain string
        is parsed with safe_eval and evaluated via search_count so that
        Odoo's ORM access rules are respected.
        """
        if not rule.condition_domain or rule.condition_domain.strip() in ("", "[]"):
            return True

        try:
            domain = safe_eval(rule.condition_domain)
        except Exception:
            # Unparseable domain — treat as non-matching (safe default)
            return False

        if not isinstance(domain, list):
            return False

        full_domain = [("id", "=", self.id)] + domain
        return self.search_count(full_domain) > 0

    def _approval_create_request(self, rule):
        """Create an ``approval.request`` in state *pending* for this record
        under *rule*, generate level-1 lines, and notify approvers.

        Returns the newly created ``approval.request``.
        """
        request = self.env["approval.request"].create(
            {
                "rule_id": rule.id,
                "res_model": self._name,
                "res_id": self.id,
                "state": "pending",
                "current_level": 1,
                "requested_by": self.env.user.id,
            }
        )

        # Resolve and create lines for level 1
        level_1 = rule.level_ids.filtered(lambda l: l.sequence == 1)
        if level_1:
            level_1 = level_1[0]
            request._generate_lines_for_level(level_1)

        # Chatter message on the request
        request.message_post(
            body=_(
                "Approval request created for %s (rule: %s)."
            ) % (self.display_name, rule.name),
            subtype_xmlid="mail.mt_note",
        )

        # Notify approvers via activity / message
        approvers = self.env["approval.request.line"].search(
            [("request_id", "=", request.id), ("level", "=", 1)]
        ).mapped("approver_id")

        if approvers:
            request.message_post(
                body=_(
                    "Please review and approve the request: %s"
                ) % request.name,
                partner_ids=approvers.mapped("partner_id").ids,
                subtype_xmlid="mail.mt_comment",
            )

        return request

    # --- Source-record hooks (overridden by integration modules) --------
    def _on_approval_approved(self):
        """Called by the engine when a request is fully approved."""
        return True

    def _on_approval_rejected(self):
        """Called by the engine when a request is rejected."""
        return True

    def _approval_block_action(self):
        """Return an action/notification informing the user that the
        operation is pending approval."""
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
