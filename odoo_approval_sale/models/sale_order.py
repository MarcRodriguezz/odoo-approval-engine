# -*- coding: utf-8 -*-
from odoo import models, _


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "approval.engine.mixin"]
    _description = "Sale Order (with Approval)"

    def action_confirm(self):
        """Override to intercept confirmation and route through the approval engine.

        When *approval_bypass* is in context (set by ``_on_approval_approved``),
        the evaluation is skipped so that an already-approved request does not
        trigger a second one (the duplicate guard only catches *pending* requests).
        """
        if self.env.context.get("approval_bypass"):
            return super().action_confirm()

        blocked = False
        for order in self:
            if order._evaluate_approval_rules("on_confirm"):
                blocked = True

        if blocked:
            return self._approval_block_action()

        return super().action_confirm()

    def _on_approval_approved(self):
        """Called by the engine when the approval request is fully approved.

        Re-invokes action_confirm with the *approval_bypass* flag so the order
        is actually confirmed without re-triggering rule evaluation.
        """
        return self.with_context(approval_bypass=True).action_confirm()
