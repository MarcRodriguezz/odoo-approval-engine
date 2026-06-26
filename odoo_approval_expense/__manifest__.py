# -*- coding: utf-8 -*-
{
    "name": "Approval Engine — Expense Integration",
    "version": "19.0.3.0.0",
    "license": "LGPL-3",
    "category": "Human Resources/Expenses",
    "summary": "Wire hr.expense into the centralized approval engine",
    "description": """
Integrates hr.expense with the odoo_approval_engine core: submitting a
rule-matched expense is held pending approval; fully approved requests
automatically submit it.
""",
    "author": "Marc Rodriguez",
    "website": "https://github.com/MarcRodriguezz/odoo-approval-engine",
    "support": "https://github.com/MarcRodriguezz/odoo-approval-engine/issues",
    "depends": ["odoo_approval_engine", "hr_expense"],
    "data": [
        "data/approval_trigger_expense.xml",
        "views/hr_expense_views.xml",
        "data/approval_demo_rule_expense.xml",
    ],
    "installable": True,
    "auto_install": False,
}
