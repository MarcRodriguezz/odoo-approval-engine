# Run it with Docker (Odoo 19)

A self-contained stack — Postgres + Odoo 19 with these modules already on the
addons path. No Enterprise required (Sales/Purchase/Invoicing/Expenses are
Community modules).

## Quick start

```bash
cd deploy
cp .env.example .env          # optional: change the DB password
docker compose up -d
```

Open <http://localhost:8069>, create a database, then install **Approval & Rules
Engine** plus whichever integrations you need (Sales, Purchase, Invoicing,
Expenses).

Install everything from the CLI instead:

```bash
docker compose exec odoo odoo -d <db> \
  -i odoo_approval_sale,odoo_approval_purchase,odoo_approval_account,odoo_approval_expense \
  --stop-after-init
docker compose restart odoo
```

## Run the tests

```bash
docker compose exec odoo odoo -d test_db \
  -i odoo_approval_sale,odoo_approval_purchase,odoo_approval_account,odoo_approval_expense \
  --test-enable \
  --test-tags=/odoo_approval_engine,/odoo_approval_sale,/odoo_approval_purchase,/odoo_approval_account,/odoo_approval_expense \
  --stop-after-init
```

## Notes

- The repository root is mounted at `/mnt/extra-addons`; non-module folders
  (`docs/`, `deploy/`, `.git/`) are ignored by Odoo.
- Ports `8069` (web) and `8072` (websocket) are bound to `localhost` only.
- Before exposing the instance: change `admin_passwd`, set `list_db = False` in
  `odoo.conf`, set a strong `POSTGRES_PASSWORD` in `.env`, and serve it behind
  an HTTPS reverse proxy.
