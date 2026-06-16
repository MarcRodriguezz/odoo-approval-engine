# -*- coding: utf-8 -*-
from odoo import api, models


class Base(models.AbstractModel):
    """Global hook so that on_create / on_write approval rules work on ANY
    model — no per-model integration code needed.

    (Blocking a specific business action such as *confirm* still requires the
    lightweight approval.engine.mixin adapter, because "confirm" is a different
    method on every model. on_create / on_write, by contrast, are universal.)
    """

    _inherit = "base"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._approval_engine_trigger("on_create")
        return records

    def write(self, vals):
        res = super().write(vals)
        self._approval_engine_trigger("on_write")
        return res

    def _approval_engine_trigger(self, trigger_event):
        # Don't run during install/upgrade, on the engine's own models, or when
        # explicitly bypassed.
        if not self or not self.env.registry.ready:
            return
        if self._name.startswith("approval.engine") \
                or self._name == "approval.decision.wizard":
            return
        if self.env.context.get("approval_bypass"):
            return
        Rule = self.env["approval.engine.rule"].sudo()
        # Cheap O(1) skip for the vast majority of models (no rules).
        if self._name not in Rule._models_with_rules(trigger_event):
            return
        Request = self.env["approval.engine.request"].sudo()
        for record in self:
            Request._evaluate_rules_for(record, trigger_event)
