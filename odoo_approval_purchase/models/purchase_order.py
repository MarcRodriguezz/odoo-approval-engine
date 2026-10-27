# -*- coding: utf-8 -*-
from odoo import models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "approval.engine.mixin"]

    def button_confirm(self):
        # Confirming after approval bypasses re-evaluation (see sale integration).
        if self.env.context.get("approval_bypass"):
            return super().button_confirm()
        blocked = self._approval_split_blocked("on_confirm")
        if not blocked:
            return super().button_confirm()
        to_confirm = self - blocked
        if to_confirm:
            super(PurchaseOrder, to_confirm).button_confirm()
        return blocked._approval_block_action(done=to_confirm)

    def _on_approval_approved(self):
        # Engine calls this when the request is fully approved -> confirm for real.
        return self.with_context(approval_bypass=True).button_confirm()
