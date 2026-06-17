# -*- coding: utf-8 -*-
{
    "name": "Approval & Rules Engine",
    "version": "19.0.2.0.0",
    "summary": "Centralized, model-agnostic approval rules engine for Odoo",
    "description": """
Centralized Approval & Rules Engine
===================================
Define configurable approval rules for any Odoo model and run sequential,
multi-level approval workflows with full chatter/email traceability.
""",
    "author": "Marc Rodriguez",
    "website": "https://github.com/MarcRodriguezz/odoo-approval-engine",
    "license": "LGPL-3",
    "category": "Tools",
    "depends": ["base", "mail"],
    "data": [
        # Security
        "security/approval_security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/ir_sequence_data.xml",
        "data/approval_trigger_data.xml",
        # Views
        "views/approval_rule_views.xml",
        "views/approval_request_views.xml",
        "views/approval_inbox_views.xml",
        "wizards/approval_decision_wizard_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
}
