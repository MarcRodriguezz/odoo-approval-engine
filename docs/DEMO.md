# 5-minute demo script

A tight walkthrough for showing the Approval & Rules Engine to a prospect. Reset
to a clean DB with the modules installed and the demo rules active.

## Cast (create once)

Two fake users make the multi-stage flow obvious:

- **Ana** — a *Buyer* (`Purchase / User`).
- **Beto** — a *Purchase Manager* (`Purchase / Manager`).

> CLI shortcut to create them (password `demo1234`):
> ```python
> for name, login, grp in [("Ana", "ana@demo.com", "purchase.group_purchase_user"),
>                          ("Beto", "beto@demo.com", "purchase.group_purchase_manager")]:
>     u = env["res.users"].create({"name": name, "login": login,
>                                  "group_ids": [(4, env.ref(grp).id)]})
>     u.password = "demo1234"
> ```

## The pitch (15 seconds)

> "Today approvals live in emails, WhatsApp and meetings — no control, no trace.
> This turns any Odoo document into a controlled approval flow you configure in
> one screen. Let me show you."

## 1 — A rule, in plain language (60s)

**Approval Engine ▸ Configuration ▸ Rules ▸ New**

- *Document*: **Purchase Order** — point out the selector only lists integrated
  documents.
- *Approvable Action*: **Purchase Order: Confirmation**.
- *Conditions* tab → `record.amount_total > 1000`.
- *Who must approve*: two stages — **Buyer** (group *Purchase / User*) then
  **Purchase Manager** (group *Purchase / Manager*).

> "Read it out loud: a purchase over 1.000 € must be approved by a buyer, then a
> manager, before it can be confirmed."

## 2 — It blocks the action (45s)

Create a purchase order over 1.000 € → **Confirm**. It does **not** confirm; a
toast says *approval required* and an **Approval: Pending** badge appears in the
header and the list.

> "The confirmation is held. Nobody can sneak it through."

## 3 — Approve, stage by stage (90s)

- Log in as **Ana** → **Approval Engine ▸ My Approvals**. One card: the document,
  the rule, who asked. Click **Approve**.
- Note it moved to stage 2 — Ana is done, it's now waiting on a manager.
- Log in as **Beto** → **My Approvals** → **Approve** (or **Reject** with a
  reason). The purchase order **confirms itself**.

> "One member of each group is enough. The moment the last stage approves, Odoo
> runs the original action automatically."

## 4 — Full trace (30s)

Open the request (**All Requests**): the status bar, every stage with *who
approved* and when, the chatter history, and a button back to the document.
**Step back** sends it to a previous stage if something changed.

> "Every euro held, every decision, fully auditable."

## 5 — The dashboard (45s)

**Approval Engine ▸ Reporting ▸ Analysis** — graph + pivot. Group by *Document
Type*, *Rule* or *Month*; the **average approval time** is right there.

> "Management sees where things get stuck and how fast the team approves."

## 6 — It's generic (15s)

> "Same engine already covers Sales, Purchase, Invoicing and Expenses — and adding
> another document is about thirty lines of code."

## Reset between demos

```bash
docker compose exec db psql -U odoo -d postgres -c "DROP DATABASE <db>;"
# recreate + reinstall, or keep a template DB and copy it.
```
