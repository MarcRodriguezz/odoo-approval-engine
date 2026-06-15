# -*- coding: utf-8 -*-
from odoo import models, fields


class ApprovalRequestLine(models.Model):
    _name = "approval.request.line"
    _description = "Approval Request Line"
    _order = "level, id"

    request_id = fields.Many2one(
        "approval.request", required=True, ondelete="cascade"
    )
    level = fields.Integer(required=True, default=1)
    approver_id = fields.Many2one("res.users", required=True)
    decision = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="pending",
        required=True,
    )
    decision_date = fields.Datetime()
    comment = fields.Text()
