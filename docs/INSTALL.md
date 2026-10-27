# Installation & Testing (Odoo 19)

Technical install/run guide. End-user docs: [README](../README.md). Architecture:
[ARCHITECTURE.md](ARCHITECTURE.md).

## Run it standalone (no existing Odoo)

A ready-to-run Docker stack lives in [`deploy/`](../deploy/) (Postgres + Odoo 19,
Community-only, this repo mounted as the addons path):

```bash
cd deploy && cp .env.example .env && docker compose up -d
# http://localhost:8069 -> create a DB -> install the modules
```

See [`deploy/README.md`](../deploy/README.md) for details.

## Modules

| Module | Depends on | Purpose |
|--------|-----------|---------|
| `odoo_approval_engine` | `base`, `mail` | Model-agnostic core: rules, approvable actions (triggers), the generic create/write hook, requests, inbox UI, security. |
| `odoo_approval_sale` | engine, `sale` | Gate `sale.order` confirmation. |
| `odoo_approval_purchase` | engine, `purchase` | Gate `purchase.order` confirmation (2-step demo rule). |
| `odoo_approval_account` | engine, `account` | Gate `account.move` posting (invoices). |
| `odoo_approval_expense` | engine, `hr_expense` | Gate `hr.expense` submission. |

All live under the Docker instance's `addons/extra/` (mapped to `/mnt/extra-addons`).

## Install

Install only what you need; each integration pulls the core automatically:

```bash
docker exec odoo19-app odoo -d <db> \
  -i odoo_approval_sale,odoo_approval_purchase,odoo_approval_account,odoo_approval_expense \
  --db_host=db --db_user=odoo --db_password=odoo --stop-after-init \
  --http-port=8999 --gevent-port=8998 --max-cron-threads=0
docker restart odoo19-app   # reload the web server
```

Install only the generic core with `-i odoo_approval_engine` (on_create/on_write rules on any
model still work; document-action gating needs an integration module).

> The running server holds ports 8069/8072, so one-off CLI runs must pass alternate
> `--http-port` / `--gevent-port`.

## Run the test suite

```bash
docker exec odoo19-app odoo -d approval_test \
  -i odoo_approval_sale,odoo_approval_purchase,odoo_approval_account,odoo_approval_expense \
  --db_host=db --db_user=odoo --db_password=odoo --test-enable \
  --test-tags=/odoo_approval_engine,/odoo_approval_sale,/odoo_approval_purchase,/odoo_approval_account,/odoo_approval_expense \
  --stop-after-init --http-port=8999 --gevent-port=8998 --max-cron-threads=0
```

Expected: **0 failed, 0 error(s) of 91 tests** (engine 76, sale 7, purchase 2, account 4,
expense 2). The same suite runs in GitHub Actions on every push
([`.github/workflows/tests.yml`](../.github/workflows/tests.yml)).

## Translations (i18n)

Templates and Spanish translations live in each module's `i18n/`. Re-export the `.pot` after
changing user-facing strings:

```bash
docker exec -e PGHOST=db -e PGUSER=odoo -e PGPASSWORD=odoo odoo19-app \
  odoo i18n export -d approval_test odoo_approval_engine odoo_approval_sale \
  odoo_approval_purchase odoo_approval_account odoo_approval_expense
```

Load translations into a DB with `-u <module> --i18n-overwrite`.

## Local Docker stack

- `odoo19-app` — Odoo 19 server (web 8069, websocket 8072).
- `odoo19-db` — PostgreSQL 16 (user/password `odoo`/`odoo`).
- Databases: `odoo` (usable instance) and `approval_test` (CI/test DB).
