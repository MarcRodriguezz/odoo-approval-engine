# -*- coding: utf-8 -*-
{
    "name": "Approval Engine — Sale Order Integration",
    "version": "19.0.2.0.0",
    "license": "LGPL-3",
    "category": "Sales",
    "summary": "Wire sale.order into the centralized approval engine",
    "description": """
        Integrates sale.order with the odoo_approval_engine core.
        Confirmation of high-value (or rule-matched) orders is held pending
        approval; fully approved requests automatically trigger the real confirm.
    """,
    "author": "Custom",
    "depends": ["odoo_approval_engine", "sale"],
    "data": [
        "data/approval_trigger_sale.xml",
        "views/sale_order_views.xml",
        "data/approval_demo_rule.xml",
    ],
    "installable": True,
    "auto_install": False,
}
