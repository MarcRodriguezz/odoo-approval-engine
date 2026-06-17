# -*- coding: utf-8 -*-
from odoo import models


class HrExpense(models.Model):
    _name = "hr.expense"
    _inherit = ["hr.expense", "approval.engine.mixin"]

    def action_submit(self):
        if self.env.context.get("approval_bypass"):
            return super().action_submit()
        blocked = False
        for expense in self:
            if expense._evaluate_approval_rules("on_submit"):
                blocked = True
        if blocked:
            return self._approval_block_action()
        return super().action_submit()

    def _on_approval_approved(self):
        return self.with_context(approval_bypass=True).action_submit()
