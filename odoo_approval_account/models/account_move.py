# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "approval.engine.mixin"]

    def action_post(self):
        if self._approval_is_bypassed():
            return super().action_post()
        blocked = self._approval_split_blocked("on_post")
        if not blocked:
            return super().action_post()
        to_post = self - blocked
        if to_post:
            super(AccountMove, to_post).action_post()
        return blocked._approval_block_action(done=to_post)

    def _post(self, soft=True):
        # Besides the Post button, Odoo posts entries from the auto-post cron
        # and the "Post entries" list action, both straight through _post().
        # Those paths set ``approval_gate_post`` so they are gated too.
        if not self.env.context.get("approval_gate_post") or self._approval_is_bypassed():
            return super()._post(soft)
        blocked = self._approval_split_blocked("on_post")
        if blocked:
            # Leave the auto-post queue: the engine posts them once approved,
            # and the cron must not pick them up again on every run.
            blocked.filtered(lambda m: m.auto_post != "no").auto_post = "no"
        to_post = self - blocked
        return super(AccountMove, to_post)._post(soft) if to_post else to_post

    def _autopost_draft_entries(self, batch_size=100):
        return super(
            AccountMove, self.with_context(approval_gate_post=True)
        )._autopost_draft_entries(batch_size=batch_size)

    def _on_approval_approved(self):
        return self._approval_bypass().action_post()
