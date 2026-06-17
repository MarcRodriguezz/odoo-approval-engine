# -*- coding: utf-8 -*-
{
    "name": "Approval Engine — Invoicing Integration",
    "version": "19.0.2.0.0",
    "license": "LGPL-3",
    "category": "Accounting/Accounting",
    "summary": "Wire account.move (invoices/bills) into the approval engine",
    "description": """
Integrates account.move with the odoo_approval_engine core: posting a
rule-matched journal entry / invoice is held pending approval; fully approved
requests automatically post the document.
""",
    "author": "Custom",
    "depends": ["odoo_approval_engine", "account"],
    "data": [
        "data/approval_trigger_account.xml",
        "views/account_move_views.xml",
        "data/approval_demo_rule_account.xml",
    ],
    "installable": True,
    "auto_install": False,
}
