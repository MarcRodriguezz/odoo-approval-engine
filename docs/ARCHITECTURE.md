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
