# Approval & Rules Engine for Odoo

[![Tests](https://github.com/MarcRodriguezz/odoo-approval-engine/actions/workflows/tests.yml/badge.svg)](https://github.com/MarcRodriguezz/odoo-approval-engine/actions/workflows/tests.yml)
[![License: LGPL-3](https://img.shields.io/badge/license-LGPL--3-blue.svg)](LICENSE)
![Odoo 19](https://img.shields.io/badge/Odoo-19.0-714B67.svg)

Stop chasing approvals over email and WhatsApp. Define **approval rules** once, and Odoo
automatically holds the right actions until the right people say "yes" — with a full history of
who approved what, when, and why.

> 💡 **Example:** "Any sales order above €10,000 must be confirmed by a Sales Manager first."
> You set that rule once; from then on every big order is held and routed automatically.

---

## Table of contents

1. [The idea in 30 seconds](#the-idea-in-30-seconds)
2. [Key concepts](#key-concepts)
3. [Which documents are supported](#which-documents-are-supported)
4. [Tutorial: your first approval rule](#tutorial-your-first-approval-rule)
5. [Approving and rejecting (My Approvals)](#approving-and-rejecting-my-approvals)
6. [Following the history](#following-the-history)
7. [Multi-stage approvals](#multi-stage-approvals)
8. [Tips & FAQ](#tips--faq)
9. [For developers](#for-developers)

---

## The idea in 30 seconds

- You write **rules** like *"if the amount is over X, ask for approval"*.
- You pick the **document** (sales order, invoice, …) and the exact **action** that needs
  approval (confirm, post, …).
- When someone triggers that action, the engine checks the rules. If one matches, the action is
  **paused** and an **approval request** is created.
- The chosen approvers get it in **My Approvals**, where they approve or reject with a comment.
- Once every stage approves, the action runs automatically. Everything is logged.

## Screenshots

| My Approvals (one-click) | Stage-by-stage trace | Reporting dashboard |
|---|---|---|
| ![My Approvals](docs/img/inbox.png) | ![Request](docs/img/request.png) | ![Dashboard](docs/img/dashboard.png) |

> Drop your captures into `docs/img/` as `inbox.png`, `request.png`, `dashboard.png`
> (and an optional `flow.gif`). A ready-to-run stack is in [`deploy/`](deploy/), and a
> 5-minute walkthrough to record from is in [`docs/DEMO.md`](docs/DEMO.md).

---

## Key concepts

| Term | What it means |
|------|---------------|
| **Approval Rule** | The "if this, then ask for approval" definition. |
| **Approvable Action** | *What* on the document needs approval — e.g. *Sale Order: Confirmation*, *Invoice: Posting*. The rule shows only the actions valid for the chosen document. |
| **Approval Stage** | One step of the rule — *who* approves (a group or a dynamic expression) and *how many* approvals are needed. Stages run in order. |
| **Approval Request** | Created automatically when a rule fires. It moves through *Draft → Pending → Approved / Rejected*. |
| **My Approvals** | Your personal board of requests waiting for **your** decision. |

---

## Which documents are supported

Out of the box, these documents can be gated (the rule's *Document* selector only shows
integrated documents):

| Document | Action that can require approval |
|----------|----------------------------------|
| **Sales Order** | Confirmation |
| **Purchase Order** | Confirmation |
| **Invoice / Journal Entry** | Posting |
| **Expense** | Submission |
| **Any model** | *On creation* / *On modification* (generic, no integration needed) |

Adding another document (e.g. a delivery) is a ~30-line integration — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Tutorial: your first approval rule

We'll recreate the classic case: **big sales orders need a manager's confirmation.**

### 1 — Open the app

A top menu **Approval Engine** appears after install. Go to
**Approval Engine ▸ Configuration ▸ Rules** (needs the *Approvals / Manager* right).

### 2 — Describe when it applies

Click **New** and fill in *When does it apply?*:

| Field | Value |
|-------|-------|
| **Name** | `High-value sales orders` |
| **Document** | `Sales Order` (only integrated documents are listed) |
| **Approvable Action** | `Sale Order: Confirmation` |

Then, in the **Conditions** tab, set when it should fire — a point-and-click **Domain** or (for
administrators) a one-line **Python** expression such as `record.amount_total > 10000`. Leave both
empty to match every record. Conditions are checked when you save the rule.

### 3 — Say who must approve

In **Who must approve**, add one stage:

| Field | Value |
|-------|-------|
| **Stage** | `Sales Manager` |
| **Approved by** | `User Group` → `Sales / Manager` |
| **Required approvals** | `1` |

Save — the rule is live.

### 4 — See it in action

Create a sales order over €10,000 and press **Confirm**. Instead of confirming, Odoo shows
*"This operation requires approval and is now pending."* The order stays a quotation and a request
goes to the Sales Managers. An **Approval** badge also appears in the order form and list.

---

## Approving and rejecting (My Approvals)

Approvers open **Approval Engine ▸ My Approvals** — a board with one card per pending decision,
showing the document, the rule, who requested it and the stage. On each card:

- **Approve** ✅ — one click.
- **Reject** ❌ — opens a short dialog where a reason is required.

When the last stage approves, the original action runs automatically. A single rejection stops the
request and notifies the requester.

---

## Following the history

Open any request under **Approval Engine ▸ All Requests**:

- The **status bar** (Draft → Pending → Approved/Rejected) — change it only through the buttons.
  An **Approvals Manager** can **Step back** a request to a previous stage, or reopen a rejected /
  cancelled one. The requester can **Cancel** their own open request. Approved requests are final:
  their action has already run.
- One line per approver with their decision, date and comment.
- The **chatter** + email notifications — a permanent, auditable trail.
- A smart button jumps back to the source document.

---

## Multi-stage approvals

Add several **stages** to a rule; they run **in order**:

```
Stage 1: Sales Manager   →   Stage 2: Finance
```

The request advances to stage 2 only after stage 1 is satisfied, and is fully approved (letting the
action run) only once **all** stages approve. Set **Required approvals** above 1 to need several
people at the same stage.

---

## Tips & FAQ

- **Why can't I pick any model in a rule?** The *Document* selector lists only integrated documents
  (those with an approvable action). For *on creation / on modification* rules the engine is
  generic and works on any model.
- **Who can configure rules?** Only *Approvals / Manager*. Any internal user can still act as an
  approver on requests assigned to them — no special group needed.
- **What if no approver is found?** No request is created and the action proceeds — make sure the
  chosen group has members.
- **Can I disable a rule?** Untick **Active** (archive) instead of deleting it.

---

## For developers

Technical docs live in [`docs/`](docs/):

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data model, engine, generic base hook, the
  integration contract, security, testing.
- [`docs/INSTALL.md`](docs/INSTALL.md) — install + run the test suite on Odoo 19.
- [`docs/DEMO.md`](docs/DEMO.md) — a 5-minute walkthrough.

Modules: `odoo_approval_engine` (model-agnostic core) + integrations `odoo_approval_sale`,
`odoo_approval_purchase`, `odoo_approval_account`, `odoo_approval_expense`. Multilingual
(English + Spanish). **87 automated tests green on Odoo 19.**

**Security in short:** requests are read-only for regular users and every decision is checked
server-side, so nobody can approve their own request; Python conditions are restricted to
administrators; a rule that cannot be evaluated holds the document instead of letting it through;
rules respect companies. Details in [`docs/ARCHITECTURE.md` § Security](docs/ARCHITECTURE.md#5-security).

## License

All modules are licensed under the **GNU Lesser General Public License v3.0 (LGPL-3)** — see
[`LICENSE`](LICENSE).
