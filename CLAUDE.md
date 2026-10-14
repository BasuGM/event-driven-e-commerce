# Project: Event-driven e-commerce (Django + Next.js)

A learning/portfolio project: an e-commerce platform built around events, seeded with the
real Olist Brazilian E-Commerce dataset so there is realistic data from day one.

## Stack

- **Backend:** Django (latest stable) + Django REST Framework, drf-spectacular for OpenAPI
- **Database:** PostgreSQL
- **Queue / events:** Redis — Celery broker (`worker` + `beat` services: reservation expiry,
  key cleanup); Redis Streams for events in a later step
- **Frontend:** Next.js (latest stable, App Router) + TypeScript + Tailwind + shadcn/ui (lucide-react
  icons, next-themes for dark mode), forms with shadcn `Field` + react-hook-form + zod. TanStack
  Table (data tables) and Recharts via shadcn's chart component (charts) are added with the first
  feature that uses them
- **Types across the boundary:** OpenAPI schema → `openapi-typescript` generated client
- **Tests:** pytest + pytest-django (backend), Vitest (frontend unit), Playwright (e2e smoke, in
  its own Docker image via `make e2e`)
- **Local dev:** Docker Compose; everything starts with one command

## Repo layout

```
backend/
  config/settings/  base.py, dev.py, test.py (DJANGO_SETTINGS_MODULE picks one)
  apps/accounts/    custom User model (AUTH_USER_MODEL = accounts.User), session auth API
  apps/core/        health + stats endpoints, Olist importer, management commands,
                    IdempotencyKey + idempotency.py, domain errors (errors.py)
  apps/cart/        Cart, CartItem, cart API (never reserves stock)
  apps/catalog/     Category, Product, Seller, Offer; catalog API; enrichment.py (generated
                    names/slugs/descriptions), stats.py (set-based SQL for offers + product stats)
  apps/customers/   Customer
  apps/orders/      Order, OrderItem, Payment, Review, Reservation, OrderStatusHistory;
                    state.py (state machine), services.py (checkout/pay/cancel/expiry — the
                    only code that changes stock), selectors.py, tasks.py (Celery)
  tests/            pytest suite; tests/fixtures/olist/ = tiny CSVs incl. messy rows
frontend/src/
  app/              App Router pages (+ loading.tsx / error.tsx per data view)
  components/ui/    shadcn primitives (CLI-managed)
  components/<feature>/  feature components (layout/, dashboard/, shop/, ...)
  lib/api/          schema.yml + generated schema.d.ts (make types), typed client.ts,
                    catalog.ts (catalog fetchers incl. the cached getProduct),
                    server.ts (as-the-visitor fetchers, forwards cookies), browser.ts (same-origin
                    client for Client Components, sends X-CSRFToken)
  lib/checkout-attempt.ts  idempotency keys for checkout (reuse on retry)
  lib/shop-params.ts  URL search params <-> shop filters (the only translation layer)
frontend/e2e/       Playwright smoke tests (run.sh is the e2e container entry point)
data/olist/     Raw Olist CSVs, directly in this folder (gitignored, never committed)
data/snapshots/ Postgres dumps of a seeded DB (gitignored)
docker-compose.yml
Makefile
CLAUDE.md
README.md       Setup guide for a fresh clone
```

Configuration lives in `.env` (copy `.env.example`; every `make` target refuses to run without it). Host ports are configurable
(`DB_HOST_PORT`, `REDIS_HOST_PORT`, `BACKEND_HOST_PORT`, `FRONTEND_HOST_PORT`) in case they clash
with other local services; containers always talk to each other on the default ports.

## Commands (keep this list accurate as the project grows)

| Command           | What it does                                              |
|-------------------|-----------------------------------------------------------|
| `cp .env.example .env` | First run only: create local config                  |
| `make up`         | Start all services                                        |
| `make down`       | Stop all services                                         |
| `make reset`      | Drop DB, migrate, seed (small) — clean slate in one step  |
| `make seed`       | Seed small dataset (fast, for dev and tests)              |
| `make seed-large` | Import the full Olist dataset                             |
| `make snapshot`   | Dump the current DB to `data/snapshots/`                  |
| `make restore`    | Restore the latest snapshot (skip slow CSV parsing)       |
| `make test`       | Backend tests, frontend tests and the frontend typecheck  |
| `make test-backend`  | Run only the backend tests (pytest)                    |
| `make test-frontend` | Run only the frontend tests (Vitest)                   |
| `make typecheck`  | `tsc --noEmit` inside the frontend container              |
| `make e2e`        | Playwright smoke test against the running, seeded stack   |
| `make types`      | Regenerate OpenAPI schema and the TS client               |
| `make migrate`    | Apply migrations                                          |

`make up` also starts the Celery `worker` and `beat` services (see their logs with
`docker compose logs -f worker beat`).

Under the hood: `python manage.py import_olist --size small|large [--data-dir DIR]` and
`python manage.py seed_dev_users` (refuses to run unless settings set `ALLOW_DEV_SEED`).

## Settings

- `config/settings/base.py` holds shared settings; `dev.py` is used by the running stack
  (`DJANGO_SETTINGS_MODULE` in `.env`).
- Tests always run with `config.settings.test`: `pytest.ini` passes `--ds`, which overrides the
  `.env` value (a test asserts this).

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
- Olist products have no name, description, price or stock. The importer **generates** them:
  `apps/catalog/enrichment.py` derives name/slug/description deterministically from the
  external ID (sha256-seeded, per-category word lists). Tests pin example outputs — changing
  the word lists renames products and changes slugs (= URLs), so treat it like a migration.
- `Offer` = one seller selling one product, derived from order items: price and freight = exact
  median item price / freight_value for the (product, seller) pair; stock is synthetic and
  deterministic (md5 of the IDs, ~10% at 0) and only set when the offer is first created — after
  that it belongs to the order flow, so a re-seed never overwrites it. Product stats (`min_price`, `rating_avg/count`, `sales_count`, `first_sold_at`,
  `search_vector`) are denormalised and recomputed by `apps/catalog/stats.py` at the end of
  every import with set-based SQL. Anything that changes offers, reviews, order items or a
  product's name/category must refresh them.
- Migrations that add required columns to populated tables: add nullable → backfill with a
  frozen `RunPython` (no app imports) → enforce in a follow-up migration.
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

## API conventions

- Catalog endpoints: `GET /api/categories/`, `/api/products/` (filters `category`, `q`,
  `min_price`, `max_price`, `min_rating`, `in_stock`, `ordering`; page size 24, max 100),
  `/api/products/{slug}/`, `/api/products/{slug}/reviews/`.
- Validate query params with a DRF serializer (bad values → 400 with per-field messages; it also
  documents them via `extend_schema(parameters=[...])`). Malformed `page`/`page_size` → 400;
  a valid page past the end → 404 (`StrictPageNumberPagination`).
- Output serializers set `read_only_fields = fields` so the OpenAPI/TS types mark every field
  as always present.
- Every list/detail endpoint has a `django_assert_num_queries` test; use `select_related` /
  `prefetch_related` so counts stay constant.
- Search: Postgres full-text (`Product.search_vector`, GIN index, prefix tsquery). Money is
  serialised as decimal strings ("75.01").

## Frontend data and caching

- Data is fetched in Server Components through the typed client; every call goes through
  `withTimeout()` (5 s, plain `BackendTimeoutError`). Don't add openapi-fetch middleware: it
  calls `Math.random()`, which `cacheComponents` rejects during prerender.
- `cacheComponents` is on. Cache with `"use cache"` + `cacheLife` + `cacheTag` (product detail:
  revalidate 5 min, tags `product:<slug>` and `products` — ready for event-driven
  `revalidateTag`). Listings stay dynamic. Anything reading `searchParams`/`usePathname()` must
  sit under a `<Suspense>` boundary (or a `loading.tsx`).
- On a streamed route, `notFound()` renders the not-found UI with `noindex` but the HTTP status
  is already 200 (documented Next behaviour); the API returns real 404s.
- The shop's URL search params are the single source of truth for filters/search/sort/page;
  convert only via `lib/shop-params.ts`.
- Only our own `TimeoutError` becomes `BackendTimeoutError`; an `AbortError` (e.g. Next aborting a
  prerender pass) propagates unchanged.
- Client components inside cached/prerendered pages must not read the URL (`usePathname`) or
  cookies; pass what they need as props (e.g. `AddToCart` gets `returnTo`). Protected pages turn a
  401 into `redirect("/login?next=…")` via `orLogin()`; `next` is checked by `safeNext()`.
- Browser-generated keys use `crypto.getRandomValues` — `crypto.randomUUID` only exists in secure
  contexts (HTTPS/localhost) and breaks on plain HTTP via other hosts (e2e, LAN).

## Auth, sessions and CSRF

- Session auth only (no JWT). The browser talks to Django **same-origin**: a Next rewrite proxies
  `/api/*` to the backend (`skipTrailingSlashRedirect` keeps Django's trailing slashes), so the
  `sessionid` / `csrftoken` cookies are first-party. Server Components call `API_URL` directly and
  forward the visitor's cookies (`lib/api/server.ts`).
- Unsafe requests send `X-CSRFToken` read from the `csrftoken` cookie on every request (Django
  rotates it at login). `GET /api/auth/csrf/` sets it. Login/register are `csrf_protect`ed.
- Through the proxy Django sees `Host: backend:8000` but the browser's `Origin`, so the browser
  origins are listed in `CSRF_TRUSTED_ORIGINS` (env). We don't trust `X-Forwarded-Host`.
- Unauthenticated → **401** (custom `SessionAuthentication`), CSRF/permission failure → 403.
  Every endpoint requires a session by default; public views opt out.
- Another user's order or cart line is a **404**, never a 403.
- Endpoints: `/api/auth/{csrf,me,login,logout,register}/`, `/api/cart/`, `/api/cart/items/[{id}/]`,
  `/api/checkout/`, `/api/orders/[{id}/[pay/|cancel/]]`. Order URLs use the 32-hex external ID.

## Orders, stock and locking (important)

- **All stock changes after the import go through `apps/orders/services.py`.** Stock is
  decremented at checkout (a `Reservation` holds it for `RESERVATION_TTL_MINUTES`), returned on
  release, kept on payment. `stock` has `CHECK (stock >= 0)` as a backstop. The importer only
  sets stock when it *creates* an offer.
- **Lock order: Cart (owner) → Order → Offers by ascending id → (after commit, own tx) Products by
  ascending id.** Always `select_for_update()` with `order_by("id")`; never lock in another order.
- Reservations are committed/released with a conditional `UPDATE … WHERE status='active'`, so each
  happens at most once even under races.
- Order status changes only through `apps/orders/state.transition()` (explicit table, writes
  `OrderStatusHistory`, requires the locked order). Illegal moves → `InvalidTransition` → 409.
- Domain errors (`apps/core/errors.py`) are plain exceptions mapped to `{code, detail, …}` by the
  DRF exception handler: `out_of_stock` (with `lines`), `reservation_expired`,
  `invalid_transition`, `idempotency_conflict` (409) and `empty_cart` (400).
- Unsafe, non-repeatable endpoints take an `Idempotency-Key` header (`run_idempotent`): keys are
  per user, stored with a request hash and the successful response in the same transaction,
  expire after 24 h. Same key → replay; same key + different body → 409; failures aren't stored.
- Celery: `release_expired_reservations` every minute (each order in its own transaction,
  `SKIP LOCKED`, idempotent) and a daily idempotency-key purge.
- `ALLOW_FAKE_PAYMENTS` (dev/test only) enables `POST /api/orders/{id}/pay/`.
- Order items are stored one row per unit (like Olist); APIs group them into lines.
- After any stock/sales change, `refresh_product_stats_on_commit(product_ids)` refreshes
  `min_price`, sales and ratings (per-product SQL, products locked in id order, retried on
  deadlock, `robust=True` so it can't fail a committed request).

## UI rules

- Build UI from shadcn/ui components (added with the shadcn CLI into `components/ui/`). Don't
  hand-roll a button, dialog, table or form control that shadcn already provides; compose them
  into feature components in `components/<feature>/`.
- Theme through shadcn's CSS variables in `globals.css` only — no hard-coded colours in
  components. Light and dark mode must both look right. Project tokens beyond shadcn's:
  `--success`, `--rating`, and `--category-1..8` (product placeholder tints, picked by a hash
  of the category slug; the icon comes from the category's `group`).
- One consistent app shell: header with nav and a theme toggle, max-width content area,
  consistent page headings and spacing.
- Every data view has a loading state (Skeleton), an empty state and an error state.
- Forms: shadcn `Field` components + react-hook-form `Controller` + zod (shadcn 4's `form` item
  is empty), with schemas mirroring the API request types.
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

## Before deploying (not done yet — required for any non-local environment)

- Rate-limit `POST /api/auth/login/` and `/register/` (e.g. per IP + per email).
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, HTTPS only (HSTS).
- `CSRF_TRUSTED_ORIGINS` = the real `https://` origin(s) only; `ALLOWED_HOSTS` likewise.
- `ALLOW_FAKE_PAYMENTS` off (it is off in `base.py`; only `dev.py`/`test.py` enable it).
- `DEBUG = False`, a real `DJANGO_SECRET_KEY`, no dev users (`seed_dev_users` refuses without
  `ALLOW_DEV_SEED`).

## Known issues

- `redis` (redis-py) is pinned to 6.4.0: `kombu[redis]` (Celery's transport) requires `<6.5`.
  It was 8.1.0 in Steps 1–2, used only for the health check.

- next-themes 0.4.6 logs "Encountered a script tag while rendering React component" in the
  browser console under React 19. Harmless (the theme script runs during SSR); no newer
  release yet.
- First visit to a route on the dev server compiles it (can take a minute on macOS bind
  mounts); later requests are fast. `make up` renews the node_modules volume
  (`--renew-anon-volumes`) so new npm dependencies reach the container.

- `npm audit` reports high-severity findings via the `shadcn` package (`braces` / `fast-glob`
  glob handling). `shadcn` is a runtime dependency only so `globals.css` can import
  `shadcn/tailwind.css`; the vulnerable code is CLI dev tooling and is not shipped to the browser.
  **Never run `npm audit fix --force`** — it "fixes" this by downgrading shadcn to 1.x.

## Out of scope (for now)

- Kafka (Redis Streams covers the concepts), Kubernetes, microservices split, real payments
  (Stripe test mode only, in a later step).
