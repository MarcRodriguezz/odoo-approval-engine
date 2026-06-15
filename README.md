# Odoo Approval & Rules Engine

A centralized, configurable approval and rules engine module for Odoo that automates approval workflows across any ERP process.

## Problem

Most companies handle approvals via email, WhatsApp, or manual meetings — scattered across every Odoo module. This leads to:

- Lack of control and visibility
- Human errors
- Slow processes
- Poor traceability

## Solution

This module introduces a **centralized rules engine** that evaluates every operation in Odoo and triggers structured approval workflows automatically.

## Key Features

### 1. Configurable Approval Rules
Define rules like:
- `amount > X` → approval required
- New customer → mandatory review
- High discount → manager approval

### 2. Rules Engine
Automatically evaluates operations across any Odoo model:
- Sales orders
- Purchase orders
- Invoices
- Expenses
- Any custom model

### 3. Approval Workflow
Standard state machine:
```
Draft → Pending Approval → Approved / Rejected
```

### 4. Approval Inbox
Dedicated UI where approvers can:
- View pending requests
- Approve or reject
- Add comments

### 5. Full Traceability
Complete audit log:
- Who approved / rejected
- When
- Under which rule

## Tech Stack

- **Platform**: Odoo (target version TBD)
- **Language**: Python + XML (Odoo standard)
- **Module type**: Odoo addon

## Project Structure

```
odoo_approval_engine/
├── models/          # Core data models
├── views/           # UI definitions (XML)
├── wizards/         # Action wizards
├── security/        # Access control lists
├── data/            # Default data / demo data
└── tests/           # Unit and integration tests
```

## Status

**MVP complete (v0.1.0-mvp)** — validated on Odoo 19. Two modules:

- `odoo_approval_engine` — model-agnostic core (rules, engine, requests, inbox UI, security).
- `odoo_approval_sale` — `sale.order` integration (high-value orders require approval).

**48 automated tests green** (core + sale integration incl. a multi-level e2e scenario).

See [docs/](docs/) for the architecture and design notes.

### Quick start (local Docker Odoo 19)

```bash
docker exec odoo19-app odoo -d <db> -i odoo_approval_sale \
  --db_host=db --db_user=odoo --db_password=odoo --stop-after-init
```

Then open the *Approvals* menu → *Configuration > Rules* to define rules, and *My Inbox* to approve.
