# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "approval.engine.mixin"]

    def action_post(self):
        if self.env.context.get("approval_bypass"):
            return super().action_post()
        blocked = self._approval_split_blocked("on_post")
        if not blocked:
            return super().action_post()
        to_post = self - blocked
        if to_post:
            super(AccountMove, to_post).action_post()
        return blocked._approval_block_action(done=to_post)

    def _on_approval_approved(self):
        return self.with_context(approval_bypass=True).action_post()
