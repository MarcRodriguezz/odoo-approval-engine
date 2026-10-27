# Technical Architecture (Odoo 19)

Engineering reference for the Approval & Rules Engine. End-user docs live in the
[README](../README.md); install and test commands in [INSTALL.md](INSTALL.md).

---

## 1. Overview

`odoo_approval_engine` is a **model-agnostic** core. It holds a business action (confirm a sale,
post an invoice, …) until a configurable, multi-stage approval completes, with a full chatter
trail. Integration modules wire it into concrete documents:

```
┌───────────────────────────────┐  inherits   ┌──────────────────────────────┐
│ odoo_approval_sale / purchase │ ──────────▶ │ approval.engine.mixin        │
│ / account / expense           │             │  _approval_split_blocked()   │
│  (gated business method)      │             │  _on_approval_approved()     │
└───────────────────────────────┘             └──────────────┬───────────────┘
                                                             │ evaluates / creates
                              ┌──────────────────────────────▼───────────────────────────┐
                              │ approval.engine.request (mail.thread) — state machine     │
                              │   └─ approval.engine.request.line — one line per stage    │
                              └──────────────────────────────┬───────────────────────────┘
                                                             │ configured by
                              ┌──────────────────────────────▼───────────────────────────┐
                              │ approval.engine.rule ─< approval.engine.rule.level        │
                              │   └─ approval.engine.trigger (the gated action)           │
                              └──────────────────────────────────────────────────────────┘
```

On top of that, a global hook on `base` makes **on create / on modification** rules work on *any*
model with no per-model code (§4.2).

Dependencies: `base`, `mail` (core); `sale`, `purchase`, `account`, `hr_expense` (integrations
only). Community-only, no external Python packages.

---

## 2. Data model

### `approval.engine.rule`
| Field | Notes |
|---|---|
| `name`, `active`, `sequence` | rules are evaluated by `sequence, id`; the first match wins |
| `model_id` / `model_name` | target model (selector limited to integrated models) |
| `trigger_id` / `trigger_event` | user-facing action selector / technical matching key (kept in sync) |
| `condition_domain` | optional domain, validated on save against the target model |
| `condition_python` | optional `safe_eval` boolean expression — **administrators only** (§5) |
| `level_ids` | ≥ 1 level, unique sequences |
| `company_id` | empty = applies to every company; otherwise only to documents of that company |

### `approval.engine.rule.level`
| Field | Notes |
|---|---|
| `sequence`, `name` | stage order and label (e.g. "Manager", "Finance") |
| `approver_type` | `group` (live group membership) or `expression` |
| `approver_group_id` | required for `group` |
| `approver_expression` | `safe_eval` returning `res.users` — **administrators only** (§5) |
| `min_approvals` | distinct approvals needed to clear the stage (≥ 1) |

### `approval.engine.request` (`mail.thread`, `mail.activity.mixin`)
`name` (sequence), `rule_id`, `res_model` / `res_id` (+ computed `resource_ref`), `state`
(`draft → pending → approved / rejected / cancelled`), `requested_by`, `request_date`,
`current_level`, `line_ids`, `company_id` (the **document's** company), and analytics fields
`closed_date` / `approval_duration` (stored, averaged in the dashboard).

### `approval.engine.request.line` — one line per stage
`level`, `min_approvals`, `approver_group_id` (matched live, incl. implied membership) or
`candidate_user_ids` (expression approvers), `approved_by_ids`, `approver_id` (who closed the
stage), `decision`, `decision_date`, `comment`.

### `approval.engine.trigger`
An approvable action: `code` + optional `model_id`. Universal triggers (`on_create`, `on_write`)
have no model; integrations ship model-specific ones (`on_confirm`, `on_post`, `on_submit`).

---

## 3. Lifecycle

```
gated action ─▶ _evaluate_rules_for(record, event)
                  rules = active rules for model + event (+ company filter)
                  first rule whose conditions match:
                     open request exists? ─▶ hold
                     else _create_request_for() ─▶ pending, stage 1 line, notify ─▶ hold
                  no match ─▶ action runs normally

decision (inbox / wizard) ─▶ line._check_can_decide()   (candidate approver or manager)
                         ─▶ request.sudo()._register_decision(line, decision, actor)
                               line must be pending and at current_level
                               reject  ─▶ rejected, notify requester, _on_approval_rejected()
                               approve ─▶ add actor; when min_approvals reached:
                                          next stage ─▶ _advance_level() + notify
                                          last stage ─▶ approved, _on_approval_approved()
```

- **Batch actions.** `_approval_split_blocked(event)` returns only the records that need
  approval; integrations run the real action on the others and show a notification listing the
  held documents.
- **Held action.** `_on_approval_approved()` re-runs the gated method in the engine's bypass
  context (`_approval_bypass()`), under `sudo()` — the approval itself is the authorization.
- **Stages are idempotent.** `_generate_lines_for_level()` resets and reuses the stage line, so
  step-back / re-approve cycles never duplicate lines.
- **Step back** (managers): from `pending` go back one stage; from `rejected` / `cancelled`
  reopen the last stage. **Approved requests cannot be reopened or cancelled** — their action
  already ran.
- **Cancel**: managers, or the requester for their own open (`draft` / `pending`) request.

---

## 4. Integration points

### 4.1 Gating a business action (mixin)

```python
class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "approval.engine.mixin"]

    def action_confirm(self):
        if self._approval_is_bypassed():
            return super().action_confirm()
        blocked = self._approval_split_blocked("on_confirm")
        if not blocked:
            return super().action_confirm()
        to_confirm = self - blocked
        if to_confirm:
            super(SaleOrder, to_confirm).action_confirm()
        return blocked._approval_block_action(done=to_confirm)

    def _on_approval_approved(self):
        return self._approval_bypass().action_confirm()
```

| Module | Model | Gated method | Trigger |
|---|---|---|---|
| `odoo_approval_sale` | `sale.order` | `action_confirm` | `on_confirm` |
| `odoo_approval_purchase` | `purchase.order` | `button_confirm` | `on_confirm` |
| `odoo_approval_account` | `account.move` | `action_post`, plus the auto-post cron and the *Post entries* list action | `on_post` |
| `odoo_approval_expense` | `hr.expense` | `action_submit` | `on_submit` |

The mixin also exposes `approval_engine_state` / `approval_engine_request_ids` for list and form
badges, computed with **one query per recordset**.

### 4.2 Any model: create / write hook (`models/base_approval.py`)

`base.create()` / `base.write()` call `_approval_engine_trigger(event)`, which returns immediately
unless the registry is ready, the model is not one of the engine's own, the engine is not itself
running an approved action, and the model has at least one active rule for the event. That last check uses an
`ormcache` that is cleared whenever a rule changes, so the hook costs almost nothing on models
without rules.

---

## 5. Security

| Who | Can |
|---|---|
| Internal user | read rules; read requests they made or can approve; comment in their chatter; cancel their own open requests |
| Approver (candidate of the current stage) | approve / reject that stage from the inbox or the wizard |
| Approvals Manager | full CRUD on rules (except Python code) and requests; decide any stage; step back; cancel |
| Administrator (`base.group_system`) | additionally author `condition_python` / `approver_expression` |

- **Requests and stage lines are read-only for regular users** (ACL + record rules). Every write
  goes through engine methods that check permissions first and then use `sudo()`, so nobody can
  edit their own request (e.g. add themselves as an approver or change its state).
- **`_register_decision` only accepts the current, still-pending stage**, so a stale inbox or
  wizard cannot re-decide a closed stage and skip the next approvers.
- **Python code is admin-only.** Expressions are evaluated with superuser rights, so — like
  server actions — they are restricted to `base.group_system` via field `groups`.
- **The bypass flag cannot be forged.** The engine runs an approved action with
  `approval_bypass` set to a per-process random token, not `True`: a client can send any JSON in
  the context of an RPC call, but cannot produce that value.
- **Every posting path is gated for invoices**: the *Post* button, the *Post entries* list action
  and the auto-post cron. Entries held from the cron leave the auto-post queue and are posted by
  the engine once approved.
- **Rules fail closed.** Domains and Python are validated when a rule is saved. If a condition
  still fails at runtime (e.g. a field was removed later), the error is logged and the document
  is **held for approval** rather than silently let through.
- **Multi-company.** Rules only apply to documents of their company (or every company when
  empty); requests belong to the document's company; managers see requests of their allowed
  companies.

---

## 6. UI

- **My Approvals** — kanban inbox of stages the user can decide (one-click approve; reject asks
  for a reason).
- **All Requests** — list / form with status bar, stages, chatter and a smart button to the
  source document.
- **Reporting ▸ Analysis** — graph / pivot dashboard (volume, outcome, average approval time) —
  managers.
- **Configuration ▸ Rules** — managers.

---

## 7. Tests

91 `TransactionCase` tests tagged `approval` (engine 76, sale 7, purchase 2, invoicing 4,
expenses 2), run in CI on Odoo 19 + PostgreSQL 16:

| Area | Covered |
|---|---|
| Rules | domain / Python matching, validation on save, fail-closed evaluation, approver resolution |
| Lifecycle | submit, single / multi-stage approve, reject, `min_approvals`, live group membership, step back, cancel, idempotent stages, stale-stage protection |
| Security | record visibility, read-only requests and lines, no self-approval, admin-only Python, unforgeable bypass flag, who may step back / cancel, multi-company rules |
| Integrations | each gated action is held and then executed on approval; batch actions hold only what needs approval; invoices cannot skip approval through auto-post or *Post entries* |
