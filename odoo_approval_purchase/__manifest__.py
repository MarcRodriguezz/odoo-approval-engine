# -*- coding: utf-8 -*-
{
    "name": "Approval Engine — Purchase Order Integration",
    "version": "19.0.3.1.0",
    "license": "LGPL-3",
    "category": "Inventory/Purchase",
    "summary": "Wire purchase.order into the centralized approval engine",
    "description": """
Integrates purchase.order with the odoo_approval_engine core.
Confirmation of rule-matched purchase orders is held pending approval;
fully approved requests automatically trigger the real confirmation.
This module demonstrates how any model is wired into the engine.
""",
    "author": "Marc Rodriguez",
    "website": "https://github.com/MarcRodriguezz/odoo-approval-engine",
    "support": "https://github.com/MarcRodriguezz/odoo-approval-engine/issues",
    "depends": ["odoo_approval_engine", "purchase"],
    "data": [
        "data/approval_trigger_purchase.xml",
        "views/purchase_order_views.xml",
        "data/approval_demo_rule_purchase.xml",
    ],
    "installable": True,
    "auto_install": False,
}
