# -*- coding: utf-8 -*-
{
    "name": "Approval & Rules Engine",
    "version": "19.0.3.0.0",
    "summary": "Turn any Odoo action into a configurable, multi-stage approval flow — "
    "no code. Sales, Purchase, Invoicing & Expenses included.",
    "description": """
Approval & Rules Engine
=======================
Define centralized approval rules for any Odoo document and hold the right
business action (confirm a sale, post an invoice, submit an expense...) until the
right people approve — with multi-stage flows, a live inbox, full traceability
and a reporting dashboard.

This purchase includes the engine **and** the ready-made integrations for Sales,
Purchase, Invoicing and Expenses (install only the ones you need).
""",
    "author": "Marc Rodriguez",
    "website": "https://github.com/MarcRodriguezz/odoo-approval-engine",
    "support": "https://github.com/MarcRodriguezz/odoo-approval-engine/issues",
    "license": "OPL-1",
    "category": "Productivity/Approvals",
    "price": 149.00,
    "currency": "EUR",
    "depends": ["base", "mail"],
    "data": [
        "security/approval_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/approval_trigger_data.xml",
        "views/approval_rule_views.xml",
        "views/approval_request_views.xml",
        "views/approval_inbox_views.xml",
        "wizards/approval_decision_wizard_views.xml",
        "views/menus.xml",
        "views/approval_analysis_views.xml",
    ],
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": True,
}
