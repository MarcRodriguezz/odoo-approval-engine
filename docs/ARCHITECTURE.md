# Phase 1 — Technical Architecture (Odoo 19)

This document is the detailed engineering design of the module.

---

## 1. System Context

`odoo_approval_engine` is a **model-agnostic** core that any Odoo model can opt into by inheriting
the `approval.engine.mixin`. Integration modules (starting with `odoo_approval_sale`) wire the
core into concrete business flows. The engine intercepts a business action (e.g. *Confirm Sale
Order*), checks configured rules, and — if a rule matches — holds the action until a sequential,
multi-level approval is completed, with full chatter/email traceability.

```
┌──────────────────────────┐     inherits      ┌───────────────────────────┐
│ odoo_approval_sale        │ ───────────────▶ │ approval.engine.mixin      │
│  sale.order.action_confirm│                   │  _evaluate_approval_rules()│
└──────────────────────────┘                   └────────────┬──────────────┘
                                                             │ creates
                                       ┌─────────────────────▼─────────────────────┐
                                       │ approval.request (mail.thread) state machine│
                                       │   └─ approval.request.line (per approver)   │
                                       └─────────────────────┬─────────────────────┘
                                                             │ evaluated against
                                       ┌─────────────────────▼─────────────────────┐
                                       │ approval.rule ─< approval.rule.level         │
                                       └─────────────────────────────────────────────┘
```

---

## 2. Dependencies (Odoo 19)

| Module | Why |
|---|---|
| `base` | ir.model, res.users, res.groups, ir.sequence |
| `mail` | `mail.thread`, `mail.activity.mixin`, email + chatter notifications |
| `sale` | (integration module only) `sale.order` |

No external Python packages beyond the Odoo 19 baseline (`python-dateutil` ships with Odoo).

---

## 3. Data Models (field-level spec)

### 3.1 `approval.rule`
| Field | Type | Notes |
|---|---|---|
| `name` | Char, required | |
| `active` | Boolean, default True | archivable |
| `sequence` | Integer | evaluation order |
| `model_id` | Many2one `ir.model`, required | target model |
| `model_name` | Char, related `model_id.model`, stored | fast lookup in engine |
| `trigger_event` | Selection `on_create/on_write/on_confirm`, required | |
| `condition_domain` | Char (domain widget) | applied via `search` on the record id |
| `condition_python` | Text | optional `safe_eval` boolean expr |
| `level_ids` | One2many `approval.rule.level` | required ≥1 |
| `company_id` | Many2one `res.company` | default current |

Constraint: at least one level; level sequences unique within a rule.

### 3.2 `approval.rule.level`
| Field | Type | Notes |
|---|---|---|
| `rule_id` | Many2one `approval.rule`, ondelete cascade | |
| `sequence` | Integer, required | level order 1..N |
| `name` | Char | e.g. "Manager", "Finance" |
| `approver_type` | Selection `group/expression`, required | |
| `approver_group_id` | Many2one `res.groups` | required if type=group |
| `approver_expression` | Text | safe_eval → `res.users` recordset; required if type=expression |
| `min_approvals` | Integer, default 1 | approvals needed to clear level |

### 3.3 `approval.request`  (inherits `mail.thread`, `mail.activity.mixin`)
| Field | Type | Notes |
|---|---|---|
| `name` | Char, default `/` | filled from `ir.sequence` |
| `rule_id` | Many2one `approval.rule`, required | |
| `res_model` | Char, required, index | source model |
| `res_id` | Integer, required, index | source record id |
| `resource_ref` | Reference (selection from ir.model) | computed clickable link |
| `state` | Selection `draft/pending/approved/rejected/cancelled`, tracking=True | |
| `requested_by` | Many2one `res.users`, default current | |
| `request_date` | Datetime, default now | |
| `current_level` | Integer, default 1 | |
| `line_ids` | One2many `approval.request.line` | |
| `company_id` | Many2one `res.company` | |

### 3.4 `approval.request.line`
| Field | Type | Notes |
|---|---|---|
| `request_id` | Many2one `approval.request`, ondelete cascade | |
| `level` | Integer | which level this line belongs to |
| `approver_id` | Many2one `res.users`, required | |
| `decision` | Selection `pending/approved/rejected`, default pending | |
| `decision_date` | Datetime | set on decision |
| `comment` | Text | from wizard |

---

## 4. Business Logic

### 4.1 Engine evaluation (`approval.engine.mixin`)
```
_evaluate_approval_rules(trigger_event) -> bool (True = blocked)
  rules = approval.rule.search([model_name=self._name, trigger_event=event, active])
        sorted by sequence
  for rule in rules:
      if not self._approval_match_domain(rule): continue
      if rule.condition_python and not safe_eval_bool(rule.condition_python, ctx): continue
      if existing open request for (self, rule): return True
      _approval_create_request(rule); return True
  return False
```
`ctx = {'record': self, 'user': self.env.user, 'datetime': datetime, 'relativedelta': relativedelta}`

### 4.2 Request creation
- Create `approval.request` (state `pending`, current_level=1).
- Generate lines for level 1 via `_approval_resolve_approvers(level)`:
  - `group` → all users in group.
  - `expression` → `safe_eval` returning `res.users`.
- Post chatter message + `mail.activity` / email to approvers of level 1.

### 4.3 Decision flow (wizard `approval.decision.wizard`)
- Approver approves/rejects with optional comment → updates their line.
- **Reject** (any line, current level) → request `rejected`, notify requester, call
  `record._on_approval_rejected()`.
- **Approve**: if `approved lines at current_level >= level.min_approvals`:
  - if more levels → `current_level += 1`, generate next level lines, notify them.
  - else → state `approved`, call `record._on_approval_approved()` (executes the held action).

### 4.4 Source-record hooks (default no-op in mixin, overridden by integrations)
- `_on_approval_approved()` — perform the originally blocked action.
- `_on_approval_rejected()` — optional rollback/notification.
- `_approval_block_action()` — return an action/notification telling the user it's pending.

---

## 5. Security

### 5.1 Groups (`security/approval_security.xml`)
| Group | Rights |
|---|---|
| `group_approval_user` | create/read own requests; read rules |
| `group_approval_approver` | act on lines assigned to them |
| `group_approval_manager` | full CRUD on rules & requests (implies approver) |

### 5.2 Record rules
- Users see requests where they are `requested_by` OR an `approver_id` on a line.
- Managers see all (company-scoped via `company_id`).

### 5.3 `ir.model.access.csv`
Matrix for the 4 models × 3 groups. Rules are read-only for non-managers.

---

## 6. UI (OWL / XML views)

- **Rules**: list + form (with levels one2many, domain widget, code editor for expressions).
- **Requests**: list (state-colored), form (statusbar, chatter, lines, smart button to source).
- **Inbox**: filtered action "My Pending Approvals" = lines where `approver_id == uid` and
  `decision == pending`; buttons open the decision wizard.
- **Menus**: root *Approvals* → *My Inbox*, *Requests*, *Configuration > Rules*.

---

## 7. Testing Strategy

| Layer | Tests |
|---|---|
| Engine | rule matching by domain + python; no-match path; duplicate-request guard |
| Lifecycle | submit→pending; single & multi-level approve→approved; reject→rejected; min_approvals |
| Security | approver cannot see foreign requests; non-manager cannot edit rules |
| Integration | sale.order confirm blocked until approved; approval triggers real confirm |

All tests use `TransactionCase`, tagged `@tagged("approval")`, runnable with Odoo's `--test-tags approval` option.

---

# Phase 2 additions (v19.0.2.0.0)

## A. Approvable Actions (`approval.engine.trigger`)

A rule now states *which action* it gates, per document.

- `approval.engine.trigger`: `name`, `code`, `model_id` (empty = universal), `active`.
- Universal triggers shipped by the core: **On creation** (`on_create`), **On modification**
  (`on_write`). Integrations ship model-specific ones (e.g. *Sale Order: Confirmation* →
  `on_confirm` / `sale.order`).
- `approval.engine.rule.trigger_id` is the user-facing selector, filtered in the form to
  `['|', ('model_id','=',False), ('model_id','=',model_id)]`. It syncs the technical matching key
  `trigger_event` (Char) on create/write. The engine still matches on `trigger_event`.
- The rule's **Document** selector is limited to integrated models via the computed
  `allowed_model_ids` (= models that have a model-specific trigger).

## B. Generic engine on any model (`models/base_approval.py`)

`base` is extended with `create` / `write` overrides that route records through the engine when a
matching `on_create` / `on_write` rule exists:

```
base.create()/write()  ->  _approval_engine_trigger(event)
  skip if: not registry.ready, engine's own models, approval_bypass ctx
  skip O(1) if model not in approval.engine.rule._models_with_rules(event)  # ormcache
  else: approval.engine.request._evaluate_rules_for(record, event)
```

The ormcache is cleared on any rule create/write/unlink. Matching always re-queries real rules, so
a stale cache only ever causes a redundant lookup — never a wrong request. This makes
`on_create` / `on_write` rules work on **any** model with no per-model code.

Matching + request creation live on `approval.engine.request` (`_evaluate_rules_for`,
`_create_request_for`); `approval.engine.mixin` delegates to them. Domain matching is
`approval.engine.rule._match_record`.

## C. Action-blocking integrations

To hold a *specific* business action (which differs per model), a model inherits the mixin and
overrides that method with the bypass-flag pattern:

| Module | Model | Gated method | Trigger code |
|--------|-------|--------------|--------------|
| `odoo_approval_sale` | `sale.order` | `action_confirm` | `on_confirm` |
| `odoo_approval_purchase` | `purchase.order` | `button_confirm` | `on_confirm` |
| `odoo_approval_account` | `account.move` | `action_post` | `on_post` |
| `odoo_approval_expense` | `hr.expense` | `action_submit` | `on_submit` |

```python
def action_confirm(self):
    if self.env.context.get("approval_bypass"):
        return super().action_confirm()
    if any(o._evaluate_approval_rules("on_confirm") for o in self):
        return self._approval_block_action()
    return super().action_confirm()

def _on_approval_approved(self):
    return self.with_context(approval_bypass=True).action_confirm()
```

## D. Security model (any internal user can approve)

- ACL: `base.group_user` gets read on rule/trigger/request/line (+ wizard RWC); managers full.
- Record rules (on `base.group_user`) scope rows to requester-or-approver; managers see all.
- Decisions (`action_quick_approve`, wizard) verify `env.user == line.approver_id` (or manager),
  then run `request.sudo()._register_decision(...)` — so advancing the workflow (which creates the
  next stage's lines) doesn't require the approver to own the engine's models.
- The source action runs via `record.sudo()._on_approval_approved()` (the approval is the
  authorization).

## E. UX & naming

- Mixin fields are namespaced: `approval_engine_state`, `approval_engine_request_ids`.
- Users see **stages** (the `approval.engine.request.line.stage_label` = the stage's name,
  else "Approval N") rather than raw "levels/steps".
- "My Approvals" is a kanban board (one-click approve; reject requires a reason). Requests can be
  reopened from any final state.
