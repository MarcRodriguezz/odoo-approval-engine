# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "approval.engine.mixin"]

    def action_post(self):
        if self.env.context.get("approval_bypass"):
            return super().action_post()
        blocked = False
        for move in self:
            if move._evaluate_approval_rules("on_post"):
                blocked = True
        if blocked:
            return self._approval_block_action()
        return super().action_post()

    def _on_approval_approved(self):
        return self.with_context(approval_bypass=True).action_post()
