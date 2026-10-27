# -*- coding: utf-8 -*-
from odoo import models


class ValidateAccountMove(models.TransientModel):
    _inherit = "validate.account.move"

    def validate_move(self):
        # The "Post entries" list action posts through _post(): gate it.
        return super(
            ValidateAccountMove, self.with_context(approval_gate_post=True)
        ).validate_move()
