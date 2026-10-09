# Project: Event-driven e-commerce (Django + Next.js)

A learning/portfolio project: an e-commerce platform built around events, seeded with the
real Olist Brazilian E-Commerce dataset so there is realistic data from day one.

## Stack

- **Backend:** Django (latest stable) + Django REST Framework, drf-spectacular for OpenAPI
- **Database:** PostgreSQL
- **Queue / events:** Redis (Celery broker now; Redis Streams for events in a later step)
- **Frontend:** Next.js (latest stable, App Router) + TypeScript + Tailwind + shadcn/ui (lucide-react
  icons, next-themes for dark mode, TanStack Table for data tables, Recharts via shadcn's chart
  component for charts)
- **Types across the boundary:** OpenAPI schema → `openapi-typescript` generated client
- **Tests:** pytest + pytest-django (backend), Vitest (frontend unit), Playwright (later)
- **Local dev:** Docker Compose; everything starts with one command

## Repo layout

```
backend/
  config/settings/  base.py, dev.py, test.py (DJANGO_SETTINGS_MODULE picks one)
  apps/accounts/    custom User model (AUTH_USER_MODEL = accounts.User)
  apps/core/        health + stats endpoints, Olist importer, management commands
  apps/catalog/     Category, Product, Seller
  apps/customers/   Customer
  apps/orders/      Order, OrderItem, Payment, Review
  tests/            pytest suite; tests/fixtures/olist/ = tiny CSVs incl. messy rows
frontend/src/
  app/              App Router pages (+ loading.tsx / error.tsx per data view)
  components/ui/    shadcn primitives (CLI-managed)
  components/<feature>/  feature components (layout/, dashboard/, ...)
  lib/api/          schema.yml + generated schema.d.ts (make types) and typed client.ts
data/olist/     Raw Olist CSVs, directly in this folder (gitignored, never committed)
data/snapshots/ Postgres dumps of a seeded DB (gitignored)
docker-compose.yml
Makefile
CLAUDE.md
```

Configuration lives in `.env` (copy `.env.example`). Host ports are configurable
(`DB_HOST_PORT`, `REDIS_HOST_PORT`, `BACKEND_HOST_PORT`, `FRONTEND_HOST_PORT`) in case they clash
with other local services; containers always talk to each other on the default ports.

## Commands (keep this list accurate as the project grows)

| Command           | What it does                                              |
|-------------------|-----------------------------------------------------------|
| `make up`         | Start all services                                        |
| `make down`       | Stop all services                                         |
| `make reset`      | Drop DB, migrate, seed (small) — clean slate in one step  |
| `make seed`       | Seed small dataset (fast, for dev and tests)              |
| `make seed-large` | Import the full Olist dataset                             |
| `make snapshot`   | Dump the current DB to `data/snapshots/`                  |
| `make restore`    | Restore the latest snapshot (skip slow CSV parsing)       |
| `make test`       | Run backend and frontend tests                            |
| `make types`      | Regenerate OpenAPI schema and the TS client               |
| `make migrate`    | Apply migrations                                          |

Under the hood: `python manage.py import_olist --size small|large [--data-dir DIR]` and
`python manage.py seed_dev_users` (refuses to run unless settings set `ALLOW_DEV_SEED`).

## Data rules (important)

- Every feature must ship with seed data. When you add or change a model, extend the seed
  command for it in the same change.
- Seeding is **idempotent**: running it twice must not duplicate rows (use natural keys from
  Olist IDs, `update_or_create` or bulk upserts).
- `--size small` = a consistent subset (~2,000 orders plus every related customer, seller,
  product, item, payment and review). `--size large` = everything.
- Seed known dev accounts (admin, staff, customer) from a dev-only fixture. Never in
  production settings.
- Raw CSVs live in `data/olist/` and are gitignored. If they are missing, the import command
  must fail with a clear message telling me where to download them. The importer reads
  `OLIST_DATA_DIR` (default `/data/olist`, i.e. `data/olist/` mounted read-only in the container).
- Bad rows are logged and skipped, never fatal; the import summary reports skipped counts by
  reason. Rows kept with a caveat (no category, untranslated category) are reported as notes.

## Domain rules

- Money: `DecimalField(max_digits=12, decimal_places=2)` — never floats.
- Time: store everything in UTC (`USE_TZ = True`); Olist timestamps are Brazil local time,
  convert on import (America/Sao_Paulo).
- Olist IDs are 32-char hex strings: keep them as the external ID; use our own primary keys.
- `Customer.external_id` is Olist's `customer_unique_id` (the real person); the per-order
  `customer_id` lives on `Order.olist_customer_id`.
- One Olist review can cover several orders: `Review` is unique on `(external_id, order)`.
- Order statuses follow Olist: created, approved, invoiced, processing, shipped, delivered,
  canceled, unavailable.

## UI rules

- Build UI from shadcn/ui components (added with the shadcn CLI into `components/ui/`). Don't
  hand-roll a button, dialog, table or form control that shadcn already provides; compose them
  into feature components in `components/<feature>/`.
- Theme through shadcn's CSS variables in `globals.css` only — no hard-coded colours in
  components. Light and dark mode must both look right.
- One consistent app shell: header with nav and a theme toggle, max-width content area,
  consistent page headings and spacing.
- Every data view has a loading state (Skeleton), an empty state and an error state.
- Forms: shadcn Form + react-hook-form + zod, with schemas mirroring the API types.
- Prices formatted with `Intl.NumberFormat` (BRL for Olist data), dates with `Intl.DateTimeFormat`.
- Responsive from 375px wide upwards; accessible (labels, focus states, keyboard navigation).
- Aim for a clean, modern storefront/admin look — restrained colour, generous whitespace, clear
  typography. No placeholder lorem ipsum: use real seeded data.

## How to work

- **Plan before coding.** For each task, propose a short plan (files, models, endpoints) and
  wait for my approval before writing code.
- **Vertical slices.** One feature end to end per task: model → migration → API → schema →
  TS client → UI → tests → seed.
- **Tests with every change.** No feature is done without tests for its core behaviour.
- **Migrations:** never edit a migration that has been applied; create a new one. Summarise
  every migration in your final message so I can review it.
- **Explain non-obvious choices** in a sentence or two in your final summary — I'm using this
  project to learn the backend side deeply.
- Keep dependencies minimal; ask before adding a new major library.
- Update this file when commands, layout or conventions change.

## Out of scope (for now)

- Kafka (Redis Streams covers the concepts), Kubernetes, microservices split, real payments
  (Stripe test mode only, in a later step).
