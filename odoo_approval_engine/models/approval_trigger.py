# -*- coding: utf-8 -*-
from odoo import models, fields


class ApprovalEngineTrigger(models.Model):
    """An "approvable action": the concrete moment a rule is checked.

    - Universal triggers (no model): "On Creation" (on_create) and
      "On Modification" (on_write) — work on ANY model out of the box.
    - Model-specific triggers (with a model): a business action provided by an
      integration, e.g. "Sale Order: Confirmation" (on_confirm, sale.order),
      "Journal Entry: Posting" (on_post, account.move).

    In a rule, the action selector is filtered to the chosen model's triggers
    plus the universal ones, so users always see *what* they are gating.
    """

    _name = "approval.engine.trigger"
    _description = "Approval Trigger (Approvable Action)"
    _order = "model_id, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help="Technical event key the engine matches (e.g. on_create, "
        "on_write, on_confirm, on_post).",
    )
    model_id = fields.Many2one(
        "ir.model", string="Model", ondelete="cascade",
        help="Leave empty for a universal trigger (any model).",
    )
    model_name = fields.Char(related="model_id.model", store=True, index=True)
    active = fields.Boolean(default=True)
