# Approval & Rules Engine for Odoo

Stop chasing approvals over email and WhatsApp. This module lets you define **approval rules**
once, and Odoo automatically stops the right operations until the right people say "yes" — with a
full history of who approved what, when, and why.

> 💡 **Example:** "Any sales order above €10,000 must be approved by a Sales Manager before it
> can be confirmed." You set that rule once. From then on, every big order is held and routed
> automatically.

---

## Table of contents

1. [The idea in 30 seconds](#the-idea-in-30-seconds)
2. [Key concepts](#key-concepts)
3. [Tutorial: your first approval rule](#tutorial-your-first-approval-rule)
4. [Approving and rejecting (the Inbox)](#approving-and-rejecting-the-inbox)
5. [Following the history](#following-the-history)
6. [Multi-level approvals](#multi-level-approvals)
7. [Tips & FAQ](#tips--faq)
8. [For developers](#for-developers)

---

## The idea in 30 seconds

- You write **rules** like *"if the amount is over X, ask for approval"*.
- When someone tries to confirm a sales order (or any record), the engine checks the rules.
- If a rule matches, the operation is **paused** and an **approval request** is created.
- The chosen approvers get it in their **Inbox**, where they approve or reject with a comment.
- Once approved, the operation continues automatically. Everything is logged.

---

## Key concepts

| Term | What it means |
|------|---------------|
| **Approval Rule** | The "if this, then ask for approval" condition you configure. |
| **Approval Level** | A step in the rule. A rule can have several levels (e.g. Manager → Finance). Each level says *who* approves and *how many* approvals are needed. |
| **Approval Request** | Created automatically when a rule fires on a record. It moves through *Draft → Pending → Approved / Rejected*. |
| **Inbox** | Your personal list of requests waiting for **your** decision. |

---

## Tutorial: your first approval rule

We'll recreate the classic case: **big sales orders need a manager's approval.**

### Step 1 — Open the Approvals app

After installing, a new top menu **Approvals** appears. Go to:

```
Approvals ▸ Configuration ▸ Rules
```

(You need the *Approvals / Manager* access right to see Configuration.)

### Step 2 — Create the rule

Click **New** and fill in:

| Field | Value | Why |
|-------|-------|-----|
| **Name** | `High-value sales orders` | Just a label. |
| **Model** | `Sales Order` | Which document this watches. |
| **Trigger** | `On Confirm` | Check the rule when the order is confirmed. |

Then open the **Conditions** tab and set when the rule should fire. You can use either:

- **Condition (Domain)** — a point-and-click filter, *or*
- **Condition (Python)** — a one-line expression, e.g.:

  ```python
  record.amount_total > 10000
  ```

> Leave both empty and the rule matches **every** record of that model.

### Step 3 — Decide who approves (Levels)

In the **Approval Levels** tab, add one line:

| Field | Value |
|-------|-------|
| **Level** | `1` |
| **Approver** | `User Group` |
| **Group** | `Sales / Manager` |
| **Min. Approvals** | `1` |

Save. That's it — the rule is live.

### Step 4 — See it in action

Create a sales order over €10,000 and press **Confirm**. Instead of confirming, Odoo shows a
notification: *"This operation requires approval and is now pending."* The order stays unconfirmed
and a request is sent to the Sales Managers.

---

## Approving and rejecting (the Inbox)

Approvers go to:

```
Approvals ▸ My Inbox
```

This lists every request line waiting for **them**. Click **Decide** on a row to open a small
dialog where you can:

- **Approve** ✅ — with an optional comment.
- **Reject** ❌ — with a comment explaining why.

- When the last required approval is given, the original action runs automatically
  (the sales order confirms itself).
- A single rejection stops the request immediately and notifies the requester.

---

## Following the history

Open any request under **Approvals ▸ Requests**. You get:

- The **status bar** (Draft → Pending → Approved/Rejected).
- A line per approver showing their decision, the date, and their comment.
- The **chatter** (message history) at the bottom, plus email notifications to approvers and the
  requester — so there's a permanent, auditable trail of *who approved what, when, and under
  which rule*.

A smart button on the request takes you straight back to the source document (e.g. the sales order).

---

## Multi-level approvals

Need more than one step? Add several **Levels** to the same rule. They run **in order**:

```
Level 1: Sales Manager   →   Level 2: Finance
```

The request only advances to Level 2 after Level 1 is satisfied, and is only fully approved
(letting the action run) once **all** levels approve. Set **Min. Approvals** above 1 on a level
to require several people at the same step.

---

## Tips & FAQ

- **Can I watch other documents, not just sales?** Yes — the engine is generic. The *Model* field
  accepts any Odoo model (purchases, invoices, expenses…). The included sales integration is just
  the first ready-made one.
- **Who can configure rules?** Only users in the *Approvals / Manager* group. Regular users only
  see their own requests and their inbox.
- **What if no approver is found?** No request is created and the action proceeds — so always
  make sure the chosen group has members.
- **Can I temporarily disable a rule?** Yes, untick **Active** (archive it) instead of deleting it.

---

## For developers

The technical documentation lives in [`docs/`](docs/):

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data model, the rules engine, the mixin
  integration contract, security design, and the testing strategy.
- [`docs/INSTALL.md`](docs/INSTALL.md) — installation and how to run the test suite on Odoo 19.

This project ships two modules: `odoo_approval_engine` (the model-agnostic core) and
`odoo_approval_sale` (the `sale.order` integration). Current status: **MVP `v0.1.0-mvp`,
49 automated tests green on Odoo 19.**
