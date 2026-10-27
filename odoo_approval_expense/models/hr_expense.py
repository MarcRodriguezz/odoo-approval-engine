# -*- coding: utf-8 -*-
from odoo import models


class HrExpense(models.Model):
    _name = "hr.expense"
    _inherit = ["hr.expense", "approval.engine.mixin"]

    def action_submit(self):
        if self._approval_is_bypassed():
            return super().action_submit()
        blocked = self._approval_split_blocked("on_submit")
        if not blocked:
            return super().action_submit()
        to_submit = self - blocked
        if to_submit:
            super(HrExpense, to_submit).action_submit()
        return blocked._approval_block_action(done=to_submit)

    def _on_approval_approved(self):
        return self._approval_bypass().action_submit()
