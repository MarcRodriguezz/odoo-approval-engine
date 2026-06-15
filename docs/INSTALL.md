# Installation & Testing (Odoo 19)

This is the technical install/run guide. For end-user instructions see the
[README](../README.md); for architecture see [ARCHITECTURE.md](ARCHITECTURE.md).

## Modules

| Module | Depends on | Purpose |
|--------|-----------|---------|
| `odoo_approval_engine` | `base`, `mail` | Model-agnostic core: rules, engine, requests, inbox UI, security. |
| `odoo_approval_sale` | `odoo_approval_engine`, `sale` | `sale.order` integration (high-value orders need approval). |

Both must live on the Odoo `addons_path`. In this project they are tracked directly under the
Docker instance's `addons/extra/` (mapped to `/mnt/extra-addons`).

## Install

Install the integration module — it pulls the core and `sale` automatically:

```bash
docker exec odoo19-app odoo -d <db> -i odoo_approval_sale \
  --db_host=db --db_user=odoo --db_password=odoo --stop-after-init \
  --http-port=8999 --gevent-port=8998 --max-cron-threads=0
# then reload the web server so it picks up the new modules
docker restart odoo19-app
```

To install only the generic core (no sales integration), use `-i odoo_approval_engine`.

> The running server occupies ports 8069/8072, so one-off CLI runs must pass alternate
> `--http-port`/`--gevent-port` values.

## Run the test suite

```bash
docker exec odoo19-app odoo -d approval_test -u odoo_approval_engine,odoo_approval_sale \
  --db_host=db --db_user=odoo --db_password=odoo \
  --test-enable --test-tags=/odoo_approval_engine,/odoo_approval_sale \
  --stop-after-init --http-port=8999 --gevent-port=8998 --max-cron-threads=0
```

Expected: `0 failed, 0 error(s)` — 49 tests green (44 core + 5 sale, incl. a multi-level e2e).

Run a single module's tests with `--test-tags=/odoo_approval_engine`, or by tag with
`--test-tags=approval`.

## Local Docker stack

- `odoo19-app` — Odoo 19 server (web on 8069, websocket on 8072).
- `odoo19-db` — PostgreSQL 16 (user/password `odoo`/`odoo`).
- Databases: `odoo` (usable instance, modules installed) and `approval_test` (CI/test DB).
