# -*- coding: utf-8 -*-
from odoo import models, _


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "approval.engine.mixin"]
    _description = "Sale Order (with Approval)"

    def action_confirm(self):
        """Override to intercept confirmation and route through the approval engine.

        When the engine runs the action after approval (``_approval_bypass``),
        the evaluation is skipped so that an already-approved request does not
        trigger a second one (the duplicate guard only catches *pending* requests).
        """
        if self._approval_is_bypassed():
            return super().action_confirm()

        blocked = self._approval_split_blocked("on_confirm")
        if not blocked:
            return super().action_confirm()
        # Confirm the orders that need no approval; hold only the others.
        to_confirm = self - blocked
        if to_confirm:
            super(SaleOrder, to_confirm).action_confirm()
        return blocked._approval_block_action(done=to_confirm)

    def _on_approval_approved(self):
        """Called by the engine when the approval request is fully approved.

        Re-invokes action_confirm in the engine's bypass context so the order
        is actually confirmed without re-triggering rule evaluation.
        """
        return self._approval_bypass().action_confirm()
