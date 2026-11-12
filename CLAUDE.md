# Project: Event-driven e-commerce (Django + Next.js)

A learning/portfolio project: an e-commerce platform built around events, seeded with the
real Olist Brazilian E-Commerce dataset so there is realistic data from day one.

## Stack

- **Backend:** Django (latest stable) + Django REST Framework, drf-spectacular for OpenAPI
- **Database:** PostgreSQL
- **Queue / events:** Redis — Celery broker (`worker` + `beat` services: reservation expiry,
  key/event cleanup) and Redis Streams for domain events (`relay` + `consumers` services; see
  "Events")
- **Frontend:** Next.js (latest stable, App Router) + TypeScript + Tailwind + shadcn/ui (lucide-react
  icons, next-themes for dark mode), forms with shadcn `Field` + react-hook-form + zod. TanStack
  Table (data tables) and Recharts via shadcn's chart component (charts) are added with the first
  feature that uses them
- **Payments:** a fake Stripe-like provider (`apps/fake_provider`, dev/test only) behind a
  `PaymentGateway` interface; signed webhooks delivered by Celery
- **Live updates:** Server-Sent Events from a separate ASGI `stream` service (uvicorn, same
  Django code), signalled through Redis Pub/Sub; the rest of the API stays on WSGI
- **Email:** Mailpit in dev (SMTP + web UI, `make mail`), Django `MAILERS`
- **Types across the boundary:** OpenAPI schema → `openapi-typescript` generated client
- **Tests:** pytest + pytest-django (backend), Vitest (frontend unit), Playwright (e2e smoke, in
  its own Docker image via `make e2e`, against a separate compose project seeded fresh each run:
  `scripts/e2e.sh` + `docker-compose.e2e.yml`; it checks, statically and then live on every
  Django service, that the database in use is `ecommerce_e2e` before anything writes; one run at
  a time; Playwright output and failure logs kept on the host in `e2e-results/`)
- **Local dev:** Docker Compose; everything starts with one command

## Repo layout

```
backend/
  config/settings/  base.py, dev.py, test.py (DJANGO_SETTINGS_MODULE picks one)
  config/asgi.py    ASGI app for the `stream` service (SSE only)
  apps/accounts/    custom User model (AUTH_USER_MODEL = accounts.User), session auth API
  apps/core/        health + stats endpoints, Olist importer, management commands,
                    IdempotencyKey + idempotency.py, domain errors (errors.py)
  apps/cart/        Cart, CartItem, cart API (never reserves stock)
  apps/catalog/     Category, Product, Seller, Offer; catalog API; enrichment.py (generated
                    names/slugs/descriptions), stats.py (set-based SQL for offers + product stats)
  apps/customers/   Customer
  apps/orders/      Order, OrderItem, Payment, Review, Reservation, OrderStatusHistory;
                    state.py (state machine), services.py (checkout/pay/cancel/expiry — the
                    only code that changes stock), events.py (order event names + payloads),
                    live.py (snapshot, version, Pub/Sub signal), stream.py (SSE view),
                    selectors.py, tasks.py (Celery)
  apps/events/      OutboxEvent, ProcessedEvent, EventLog, DeadLetterRetry; outbox.py
                    (record_event), relay.py, consumer.py (framework), consumers/
                    (product_stats, cache_invalidation, notifications, order_live, event_log,
                    analytics),
                    revalidate.py (calls Next), run_relay / run_consumers commands
  apps/payments/    PaymentIntent, ProviderEvent; gateway.py (interface), signature.py (HMAC),
                    services.py (start_payment, handle_webhook), webhook view
  apps/fake_provider/  FakeIntent, FakeEvent, FakeGateway, hosted page, Celery delivery
                    (dev/test only; URLs mounted only with ALLOW_FAKE_PAYMENTS)
  apps/notifications/  Notification; rendering.py + templates, sender.py, tasks.py
  apps/staff/       staff-only API: event log, order timelines, consumer health, DLQ retry
  apps/analytics/   projection tables, projections.py (set-based recompute), queries.py
                    (dashboard), backfill_analytics command
  apps/replay/      ReplayRun; services.py (plan, copies, Runner, reset); replay_orders and
                    replay_reset commands (dev/test only)
  tests/            pytest suite; tests/fixtures/olist/ = tiny CSVs incl. messy rows
frontend/src/
  app/              App Router pages (+ loading.tsx / error.tsx per data view);
                    app/internal/revalidate/route.ts = cache invalidation for the consumers
  components/ui/    shadcn primitives (CLI-managed)
  components/<feature>/  feature components (layout/, dashboard/, shop/, ...)
  lib/api/          schema.yml + generated schema.d.ts (make types), typed client.ts,
                    catalog.ts (catalog fetchers incl. the cached getProduct),
                    server.ts (as-the-visitor fetchers, forwards cookies), browser.ts (same-origin
                    client for Client Components, sends X-CSRFToken)
  lib/cache-tags.ts  cache tag names (productTag, ALL_PRODUCTS), shared with the backend
  lib/use-order-live.ts  EventSource hook for the order page (SSE; slow-poll fallback)
  lib/staff-params.ts  staff event filters <-> URL search params
  app/staff/        staff pages (events, health, orders/[id], analytics); components/staff/,
                    components/analytics/ (charts, filters); lib/analytics-params.ts
  lib/checkout-attempt.ts  idempotency keys for checkout (reuse on retry)
  lib/use-hydrated.ts  false until hydrated: JS-driven controls stay disabled until then
  lib/shop-params.ts  URL search params <-> shop filters (the only translation layer)
frontend/e2e/       Playwright smoke tests (run.sh is the e2e container entry point)
frontend/screenshots/  README screenshot generator (own Playwright config; `make e2e` never runs it)
docs/           Human docs: architecture, data model, API, flows/, adr/, concepts/, stack/, operations/
                (README.md links to every one; docs/images/ = README screenshots from `make screenshots`)
scripts/        docs_check.py (make docs-check)
data/olist/     Raw Olist CSVs, directly in this folder (gitignored, never committed)
data/snapshots/ Postgres dumps of a seeded DB (gitignored)
docker-compose.yml
Makefile
CLAUDE.md
README.md       Landing page: pitch, screenshot gallery, highlights, architecture, quick start, docs map
                (the long how-to is docs/operations/runbook.md)
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
| `make reset`      | Drop DB, delete the `events:*` streams, migrate, seed (small) — clean slate in one step |
| `make seed`       | Seed small dataset (fast, for dev and tests)              |
| `make seed-large` | Import the full Olist dataset                             |
| `make snapshot`   | Dump the current DB to `data/snapshots/`                  |
| `make restore`    | Restore the latest snapshot (skip slow CSV parsing)       |
| `make test`       | Backend tests, frontend tests and the frontend typecheck  |
| `make test-backend`  | Run only the backend tests (pytest)                    |
| `make test-frontend` | Run only the frontend tests (Vitest)                   |
| `make typecheck`  | `tsc --noEmit` inside the frontend container              |
| `make e2e`        | Playwright smoke tests on an **isolated** stack (compose project `ecommerce-e2e`, own DB `ecommerce_e2e` on tmpfs, Redis, Mailpit; seeded fresh, torn down after). Never touches the dev DB. One run at a time (lock `e2e-results/.e2e-lock`; refuses while another run or a kept stack is up). Traces/videos/HTML report and, on failure, frontend/backend/stream logs land in `e2e-results/` (gitignored). `ARGS="e2e/shop.spec.ts"` (Playwright args pass through, e.g. `--repeat-each 3`); `KEEP_E2E=1` leaves it up on http://localhost:3101, only if setup and every guard passed (a guard or setup failure always tears down) |
| `make e2e-down`   | Remove a kept e2e stack (`KEEP_E2E=1`)                    |
| `make lab-up` / `make lab-down` | The isolated e2e stack for the `docs/concepts/` exercises: same guards and run lock as `make e2e`, seeded fresh, no Playwright, left up (site http://localhost:3101, Mailpit http://localhost:8125; db/Redis via `docker compose exec`, alias in `docs/concepts/lab.md`). A failed start tears down. `lab-down` = `e2e-down` |
| `make types`      | Regenerate OpenAPI schema and the TS client               |
| `make migrate`    | Apply migrations                                          |
| `make backfill-sales` | Recount `sales_count` without canceled/unavailable orders (one-off, re-runnable) |
| `make events-logs` | Follow the relay, consumers and stream (SSE) logs        |
| `make mail`       | Print the Mailpit URL (every email the app sends lands there) |
| `make analytics-backfill` | Rebuild the analytics projections from orders (also run by `make seed`) |
| `make replay`     | Replay imported orders as live events (default Black Friday week 2017, `--speed 10`; `ARGS="--from … --to … --speed … --limit … --dry-run"`) |
| `make replay-reset` | Delete replayed orders and everything they produced (`ARGS="--run N"`) |
| `make screenshots` | Regenerate `docs/images/*.png` (README gallery): Playwright in the Playwright image against the **lab stack only** — refuses unless `make lab-up` is up and every Django service is on `ecommerce_e2e`; places orders, pays on the fake provider (30 s delayed webhook), runs a short replay there (never the dev stack), then optimises the PNGs with pngquant in a throwaway container. ~5 min. Raw shots + failure output in `e2e-results/` |
| `make docs-check` | Check README.md + docs/: links, anchors, images and code references resolve (pending docs listed in `scripts/docs_pending.txt`; in `docs/concepts/` only, external names such as Postgres settings may be backticked if listed in `scripts/docs_external_names.txt`) |

`make up` also starts the Celery `worker` and `beat` services (see their logs with
`docker compose logs -f worker beat`), the event `relay` and `consumers` services and the
`stream` service (uvicorn on 8001, SSE; Next rewrites `/api/orders/<id>/stream/` to it). Until
`make migrate` has created the events tables they log one "waiting for the events tables" line
and wait (also after `make reset` drops the schema); consumers never read a stream before that.

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
- Seed known dev accounts (admin, staff, customer, replay) from a dev-only fixture. Never in
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
- `Order.source`: `olist` (the importer), `app` (`checkout()`) or `replay` (copies made by
  `apps/replay`), required (no default, so a new creation path can't forget it). Analytics
  reports every metric per source. **Replay copies never count for the shop:** `OFFERS_SQL`
  (prices) and `SALES_SQL` (`sales_count`) exclude `source='replay'`, as does the public orders
  count; the `product_stats` and `notifications` consumers skip replay events.
- `sales_count` / `first_sold_at` only count units on orders that aren't `canceled` or
  `unavailable` (unpaid orders count until they're canceled or expire). After an import the SQL
  applies it directly; in the order flow the `product_stats` consumer keeps it current.
- The importer emits no events (it isn't the order flow); a bulk change to imported data needs
  `make backfill-sales` or a full stats refresh, not events.
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
  revalidate 5 min, tags `productTag(slug)` = `product:<slug>` and `ALL_PRODUCTS` = `products`
  from `lib/cache-tags.ts`). The `cache_invalidation` consumer revalidates `product:<slug>`
  through `POST /internal/revalidate` (`revalidateTag(tag, { expire: 0 })`, shared secret
  `REVALIDATE_SECRET`). Listings stay dynamic (no tags). Anything reading `searchParams`/`usePathname()` must
  sit under a `<Suspense>` boundary (or a `loading.tsx`).
- On a streamed route, `notFound()` renders the not-found UI with `noindex` but the HTTP status
  is already 200 (documented Next behaviour); the API returns real 404s.
- The shop's URL search params are the single source of truth for filters/search/sort/page;
  convert only via `lib/shop-params.ts`.
- Only our own `TimeoutError` becomes `BackendTimeoutError`; an `AbortError` (e.g. Next aborting a
  prerender pass) propagates unchanged.
- After an auth change (login, register, logout) and after checkout, navigate with a **full page
  load** (`window.location.assign`), never `router.push/replace` + `router.refresh()`: the header
  (user menu, cart badge) is a Server Component in the root layout, which a soft navigation
  reuses, and a refresh right after the navigation raced it (trace 2026-11-09: refresh pending
  > 20 s, URL never changed).
- Controls that act through JavaScript render **disabled until hydrated** (`useHydrated()` in
  `lib/use-hydrated.ts`), and forms use `method="post"`: before hydration a click is lost, and a
  method-less form falls back to a native GET that put credentials or the address in the URL.
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
  `/api/checkout/`, `/api/orders/[{id}/[payment/[return/]|cancel/|stream/]]`, `/api/payments/webhook/` (no session:
  HMAC-signed), `/api/fake-provider/pay/<pi_id>/` (dev). Order URLs use the 32-hex external ID.

## Orders, stock and locking (important)

- **All stock changes after the import go through `apps/orders/services.py`.** Stock is
  decremented at checkout (a `Reservation` holds it for `RESERVATION_TTL_MINUTES`), returned on
  release, kept on payment. `stock` has `CHECK (stock >= 0)` as a backstop. The importer only
  sets stock when it *creates* an offer.
- **Lock order: Cart (owner) → Order → PaymentIntent → Offers by ascending id → (after commit, own
  tx) Products by ascending id.** Always `select_for_update()` with `order_by("id")`; never lock in another order.
- Reservations are committed/released with a conditional `UPDATE … WHERE status='active'`, so each
  happens at most once even under races.
- Order status changes only through `apps/orders/state.transition()` (explicit table, writes
  `OrderStatusHistory`, requires the locked order). Illegal moves → `InvalidTransition` → 409.
  Table: created → approved | canceled; approved → invoiced | canceled | unavailable;
  invoiced → shipped; shipped → delivered (`processing` is historical only). Fulfilment
  services `invoice` / `ship` / `deliver` / `mark_unavailable` / `cancel_paid` lock the order
  and check + transition in one transaction (no stock moves: it stayed sold at payment). Only
  the replay calls them so far; **`cancel_paid` and `mark_unavailable` refuse non-replay
  orders** (`InvalidTransition`): a real paid cancellation needs a refund + restock design.
- Domain errors (`apps/core/errors.py`) are plain exceptions mapped to `{code, detail, …}` by the
  DRF exception handler: `out_of_stock` (with `lines`), `reservation_expired`,
  `invalid_transition`, `idempotency_conflict`, `replay_read_only` (409) and `empty_cart` (400).
- Only `POST /api/checkout/` takes an `Idempotency-Key` header (required; `run_idempotent`): keys
  are per user, stored with a request hash and the successful response in the same transaction,
  expire after 24 h. Same key → replay; same key + different body → 409; failures aren't stored.
  Payment start needs no key: the partial unique index `uniq_open_intent_per_order` allows one
  open `PaymentIntent` per order, so a repeated click reuses it.
- Celery: `release_expired_reservations` every minute (each order in its own transaction,
  `SKIP LOCKED`, idempotent) and a daily idempotency-key purge. Daily tasks are crontabs at a
  fixed UTC time (never 24 h intervals, which restart with beat); beat's state lives on the
  `beatstate` volume (`-s /var/lib/celerybeat/schedule`).
- `ALLOW_FAKE_PAYMENTS` (dev/test only) enables the fake payment provider (hosted page, webhook
  delivery). Payment state changes only arrive through the webhook (see "Payments").
- Order items are stored one row per unit (like Olist); APIs group them into lines.
- After any stock change, `refresh_product_stats_on_commit(product_ids)` refreshes `min_price`
  and ratings synchronously (per-product SQL, products locked in id order, retried on deadlock,
  `robust=True` so it can't fail a committed request), so the listing's price and in-stock
  filter are right at once. `sales_count` is **eventually consistent**: the `product_stats`
  consumer owns it (seconds of lag).
- Every order state change records a domain event with `events.record_order_event()` in the
  same transaction (see "Events").

## Payments (fake provider, webhooks)

- **Interface:** `apps/payments/gateway.py` `PaymentGateway` (`create_payment`, `parse_webhook`);
  `get_gateway()` picks `PAYMENT_PROVIDER` (`fake`). A real provider = one more class.
- **Two models, two jobs:** `payments.PaymentIntent` = the provider lifecycle (one open intent
  per order, `needs_refund`); `orders.Payment` = the settled ledger (Olist's shape), written by
  `services.pay()` on success.
- **Flow:** `POST /api/orders/{id}/payment/` creates or reuses the intent → the customer pays on
  the provider's hosted page → the provider redirects to `GET /api/orders/{id}/payment/return/`,
  which marks the intent **`processing`** (+ `returned_at`) and goes to `/orders/<id>` → the
  provider delivers a signed webhook (Celery, with retries) → `handle_webhook` → `services.pay()`.
  `OrderPaid` / `PaymentFailed` / `ReservationExpired` still come from the outbox.
- **`processing` is UI state only** (stored server-side so it survives reloads; the webhook still
  decides). It hides Pay ("Payment in progress") for `PAYMENT_CONFIRMATION_TIMEOUT_SECONDS`
  (180) after `returned_at`; then `confirmation_overdue` and Pay is offered again, reusing the
  same intent (`OPEN_STATUSES` = requires_payment, processing), so it can't double-charge. No
  URL parameter carries payment state.
- **No HTTP inside transactions:** `create_payment` runs before the short transaction that saves
  the intent; its idempotency key (`order:<id>:intent`) dedupes concurrent clicks.
- **Signature:** `Fake-Signature: t=<unix>,v1=<hex>`, `v1 = HMAC-SHA256(PAYMENT_WEBHOOK_SECRET,
  "<t>." + raw body)`, ±`PAYMENT_WEBHOOK_TOLERANCE_SECONDS` (300), `hmac.compare_digest`, several
  `v1` allowed (rotation). Verified over the **raw bytes** (a plain Django view, not DRF), JSON
  parsed only afterwards; failures are a vague 400.
- **Idempotency:** `ProviderEvent` unique on `(provider, provider_event_id)`: duplicates return
  200 and do nothing. Then Order → PaymentIntent are locked.
- **State rules:** expiry is judged by the event's own `created` time (paid in time + stock still
  held = approved, however late the webhook). A decline cancels the order (`PaymentFailed`). A
  decline older than an applied success is `ignored_stale`. A success for an order that's
  canceled/expired (or already paid) never revives it: the intent is flagged `needs_refund` and a
  `PaymentRefundDue` event is recorded in the same transaction (no refund logic yet; admin
  PaymentIntent list filtered by `needs_refund`).
- **Fake provider page** (`/api/fake-provider/pay/<pi_id>/`, served through the Next proxy so one
  relative URL works for every browser): succeed / fail / succeed after a delay, plus "deliver
  each webhook twice" and "declined then succeeded, delivered out of order";
  `FAKE_PROVIDER_DUPLICATE_DELIVERY` makes "twice" the default. It refuses after the hold expires.

## Live order tracking (SSE)

- **Where:** `GET /api/orders/<id>/stream/` is served by the **ASGI `stream` service** (uvicorn,
  `config/asgi.py`, same code and session auth as the API). An open stream is an idle coroutine,
  not a WSGI worker. Under WSGI the view refuses (404): Django would buffer the whole async
  stream. The rest of the API stays on WSGI (on ASGI, sync views would share one thread).
- **Routing:** Next rewrites that path to `STREAM_URL` (before `/api/*`). The response sends
  `Cache-Control: no-cache, no-transform` (Next's rewrite proxy gzips every response otherwise,
  which buffers SSE completely; verified: without it 10 bytes arrived in 35 s) and
  `X-Accel-Buffering: no`. Heartbeats every 15 s keep it under the proxy's 30 s idle timeout.
- **Signal vs state:** the `order_live` consumer publishes `live:order:<id>` (Pub/Sub) for every
  order event and `PaymentRefundDue`; the return view publishes too. The signal carries no
  state: the stream re-reads the **snapshot from the DB** (the order detail serializer's
  status, timeline, payment, can_pay/can_cancel, expiry). A dropped signal is fixed by the next
  one, a reconnect, or the fallback poll.
- **Versions:** `live_version` = hash of the snapshot fields (also on the order detail API).
  Events go out as `id: <version>`; a reconnect's `Last-Event-ID` equal to the current version
  gets no replay, and an unchanged version is never re-sent.
- **Lifecycle:** owner only (404 otherwise, 401 anonymous); subscribe first, then read and send
  the snapshot (so a change committed while connecting isn't missed), again on each
  signal that changes the version; `: heartbeat` every 15 s; wakes at a payment's `overdue_at`
  (no event for that); closes after 300 s (EventSource reconnects) or with `event: end` when
  the order is final (delivered/canceled with no payment pending). `finally` unsubscribes on
  every exit, including a client disconnect.
- **Failure modes:** Redis down → the stream re-reads the DB every 5 s; `stream` restarts →
  EventSource reconnects with Last-Event-ID; consumers down → signals catch up from the durable
  stream; snapshot reads run on the thread pool (`thread_sensitive=False`) and close their DB
  connection each time.
- **Frontend:** `useOrderLive` (EventSource) calls `router.refresh()` when a snapshot's version
  differs from the rendered `live_version` (one render path: the Server Component page); falls
  back to a 15 s refresh only if EventSource gives up (non-200). `OrderLive` shows a badge only
  after 5 s disconnected. No 2-second polling anywhere.
- Not done (follow-up): live status badges on `/orders` (needs a per-user channel).

## Notifications (email)

- The `notifications` consumer writes a pending `Notification` (unique `(event_id, kind)`,
  subject/text/HTML rendered then) in its transaction and enqueues `send_notification` on
  commit. **Email is never sent inside the consumer's transaction.** Kinds: order_placed,
  order_paid, payment_failed, order_canceled, reservation_expired, refund_due.
- Sender (`apps/notifications/sender.py`, Celery): one row per transaction, `SKIP LOCKED`, marked
  sent with the send; failures retry with backoff (30 s doubling, max 1 h) up to
  `NOTIFICATION_MAX_ATTEMPTS` (8), then `failed`. Beat `send_due_notifications` (30 s) covers
  retries and lost enqueues. A replay can't send twice (ProcessedEvent + the unique row).
- Known gap: a crash after SMTP accepted the message but before the commit resends it once
  (deterministic `Message-ID: <notification-<id>@olist-commerce.local>`).
- Templates `notifications/order_email.{txt,html}`; money via `apps.core.formatting.format_brl`
  ("R$ 1.234,50"); links use `FRONTEND_PUBLIC_URL`. Dev mail goes to Mailpit (`make mail`).

## Events (outbox → relay → Redis Streams → consumers)

- **Write:** services call `record_event()` (`apps/events/outbox.py`) inside the transaction
  that makes the change — never in views or signals. Rollback = no event. Order events
  (`ORDER_EVENTS`): `OrderPlaced`, `OrderPaid`, `PaymentFailed`, `OrderCanceled` (customer, or
  after payment), `ReservationExpired` (`source`: `sweeper` or `payment_attempt`),
  `OrderInvoiced`, `OrderShipped`, `OrderDelivered`, `OrderUnavailable`; payload = order id,
  user id, `order_source` (+ `replay_run`), status, reason, lines (offer/product id + slug,
  seller, quantity, unit price/freight), totals. Money as decimal strings. Bump
  `schema_version` for breaking payload changes (additive fields don't).
- **Relay** (`run_relay`, compose `relay`): batches of unpublished rows with
  `FOR UPDATE SKIP LOCKED`, XADD to `events:<aggregate_type>` (entry carries the event id), then
  stamps `published_at`. Stops at the first Redis error (never skips), records
  `attempts`/`last_error`, backs off. Safe to scale. The Redis client has connect/socket
  timeouts so a hung Redis can't hold the row locks.
- **Delivery is at-least-once** (a crash between XADD and the commit re-sends). Consumers make
  it effectively-once: `ProcessedEvent(consumer, event_id)` is inserted in the same transaction
  as the side effects, and XACK only happens after commit. Event types a consumer doesn't
  handle are just acked.
- **No ordering guarantee** across relays: handlers must be **state-based** (recompute from the
  DB), never apply deltas.
- **Recovery:** pending entries idle for `EVENTS_CLAIM_IDLE_MS` are reclaimed (XAUTOCLAIM);
  after `EVENTS_MAX_DELIVERIES` (5) an entry goes to `events:dlq` with the error and is acked.
- **Consumers** (`run_consumers`, compose `consumers`, one thread each, SIGTERM = graceful):
  - `product_stats` (order events): recomputes `sales_count` + `min_price`, then records
    `ProductsChanged` (stream `events:product`) in the same transaction.
  - `cache_invalidation` (`ProductsChanged`): POSTs the products' cache tags to the frontend's
    `/internal/revalidate` (header `x-revalidate-secret`). Chained so revalidation always
    follows the recompute.
  - `notifications` (order events + `PaymentRefundDue`): order emails (see "Notifications").
- `PaymentRefundDue` (stream `events:order`) is recorded by the payment webhook when money
  arrives for an order that can't take it.
- **No inventory consumer (yet), on purpose:** oversell protection stays synchronous in
  `checkout()`; `min_price` stays on-commit (in-stock filter must be right at once); stock-driven
  cache refresh already flows through `product_stats` → `ProductsChanged`. `StockLow`/`OutOfStock`
  events would have no reader. When a feature needs one (back-in-stock alerts, restocking), emit
  `OfferStockChanged` from `services.py` (every stock change is there) and build the consumer
  with it.
- **Dashboard stats stay on-request** (four `COUNT(*)`s): products/sellers come from the
  importer (no events), so event-maintained counters would need a backfill and could drift.
- `event_log` consumer (every stream, `event_types = ALL`) writes each event once to `EventLog`
  (unique `event_id`): the explorer's history. Beat purges published outbox rows after
  `EVENTS_RETENTION_DAYS` (7: a delivery buffer) and `EventLog` + `ProcessedEvent` after
  `EVENT_LOG_RETENTION_DAYS` (90: the explorer shows which consumers processed each event, so
  both are kept as long).
- `make reset` also deletes the event streams (`manage.py clear_event_streams`: only
  `<EVENTS_STREAM_PREFIX>:*` stream keys, with their groups and the DLQ; Celery's keys in the
  same Redis DB are untouched). Otherwise consumers would replay old events against fresh data.
  Dev/test only (`ALLOW_DEV_SEED`).
- `/api/health` reports the outbox backlog (unpublished count, oldest age); informational only.
- Tests use the real compose Redis (DB 15, `test-events:` prefix, keys cleared per test) and
  Celery's in-memory broker (never the dev Redis broker).

## Staff tools (event explorer)

- Staff only: `/api/staff/*` uses `IsStaffOr404` (anonymous and non-staff get **404**, not
  401/403), and each `/staff/*` page renders its staff header only after its data check passed
  (no shared layout that would flash staff chrome). The "Staff" header link shows for
  `is_staff` users.
- The 404 for a staff page is still HTTP 200 (streamed route), so nothing in the page's static
  part may reveal it: `app/staff/layout.tsx` gives every `/staff/*` page the neutral title
  "Olist Commerce" + robots `noindex, nofollow`; the real "<Page> · Staff · …" title is set
  client-side by `DocumentTitle` inside the staff header, i.e. only after the staff check.
  Staff pages export no `metadata` title of their own. Next re-writes the metadata `<title>`
  whenever a metadata tree commits (every `router.refresh()`, and streamed metadata can land
  after mount), so `DocumentTitle` keeps a MutationObserver on `<head>` while mounted (layout
  effect, so it disconnects before the next page's title). e2e: `staff-title.spec.ts`.
- Pages: `/staff/events` (filters: type, aggregate id, date range; URL = state via
  `lib/staff-params.ts`; payload as JSON), `/staff/orders/<id>` (the order's events in order,
  each with the consumers that should process it and when they did, from ProcessedEvent),
  `/staff/health` (per group pending/lag via XINFO GROUPS, active consumers, outbox backlog, last
  100 dead letters). Each page is a static shell with the data (and staff header) under
  `<Suspense>`; blank filter fields redirect to a clean URL.
- Consumer names are `hostname-pid`, so restarts leave dead names in groups: on start a consumer
  removes names with **0 pending** idle > `EVENTS_CONSUMER_PRUNE_IDLE_MS` (10 min; never ones
  with pending entries, which XAUTOCLAIM recovers). Health counts consumers active within
  `EVENTS_CONSUMER_ACTIVE_IDLE_MS` (1 min) and shows the rest as inactive.
- **Dead-letter retry** (`POST /api/staff/dead-letters/<entry_id>/retry/`, CSRF): XADDs the
  entry's original fields (same event id) back onto its stream, once per DLQ entry
  (`DeadLetterRetry` unique, records who). Every group sees the new entry; groups that already
  processed the event find their ProcessedEvent row and just ack; the consumer that
  dead-lettered it has no row (each attempt rolled back), so it applies it now. The DLQ entry
  stays for the record, marked retried.

## Analytics (staff dashboard)

- Projections (`apps/analytics`): `DailySales`, `CategorySales`, `StateSales`, `DeliveryStats`,
  one row per (day, source[, category/state]) with a unique key. **Day = purchase date in
  America/Sao_Paulo** (`ANALYTICS_TIMEZONE`), for every table (delivery stats included).
- Definitions: `orders` and `canceled_orders` (canceled + unavailable) count every placed order;
  **revenue counts only orders that reached approved or later** (approved, invoiced, processing,
  shipped, delivered): GMV = items + freight, AOV = GMV / paid orders (Decimal, half-up),
  category revenue = item prices (freight isn't per category), state = shipping state else the
  customer's. Delivery: purchase → delivered seconds, late = delivered (local date) after the
  estimated date.
- State-based: `recompute_days(days, source)` DELETEs and re-INSERTs those rows from the orders
  in one transaction, after `pg_advisory_xact_lock` per (source, day) taken in ascending day
  order, so concurrent recomputes (consumer, backfill, two consumers) queue instead of
  double-inserting or deadlocking. The `analytics` consumer recomputes the order's purchase day
  on every order event; `backfill_analytics` / `make analytics-backfill` rebuilds everything (the
  importer emits no events) and runs as part of `make seed`.
- `GET /api/staff/analytics/?source=&date_from=&date_to=` (staff only, 404 otherwise; no dates =
  all data for that source). `/staff/analytics`: KPI cards, revenue over time, by category, by
  state, weekly delivery performance (shadcn chart/Recharts, no animation), source filter and a
  Calendar range picker with presets relative to the newest data; URL = state via
  `lib/analytics-params.ts`. **Staff only**: GMV, cancellations and lateness are business data.
- Dashboard choices: the default source is `olist` (`DEFAULT_SOURCE`, omitted from the URL; All is
  `?source=all`) so a day of app test orders doesn't flatten the first view. Revenue over time
  uses a time-scaled numeric x axis and breaks the line after gaps > 31 days (2018 → 2026 shows
  as a gap). Category: top 10 bars, the rest as a note ("+N categories, R$ X"). State: top 10
  horizontal bars + "Other (n)", every bar labelled. Series use `--chart-1..5` (real colours in
  both themes, ≥ 3:1 on the background); delivery = line `chart-1` + translucent bars `chart-4`.
- Updates while open with a gentle poll (`router.refresh()` every 10 s while the tab is visible),
  not SSE: projections change in bursts (hundreds per second during a replay), so a stream would
  need coalescing, and a dashboard isn't latency-critical.

## Replay (historical orders as live events)

- `replay_orders --from --to [--limit] [--speed S] [--dry-run]` (`make replay`; dev/test only,
  `ALLOW_DEV_SEED`): selects imported orders by Sao Paulo purchase day and re-enacts each as a
  **copy** (`source='replay'`, `replay_of` = original, `replay_run` = the `ReplayRun`, owned by
  `replay@example.com`, the buyer's city/state/zip, items and estimated date copied).
- Steps per order: place (purchased) → approve (`approved_at`, through the real `pay()`: ledger
  row + `OrderPaid`) → invoice → ship (carrier date) → deliver, or → unavailable / cancel.
  Olist has no invoiced/canceled/unavailable times: synthesized (approved + 1 h; invoice before
  pickup); out-of-order Olist dates are clamped so time never goes back. Olist `processing`
  stays approved; the one order canceled after shipping is canceled right after approval
  (shipped → canceled is illegal), reported by the command.
- All orders' steps are merged by time and applied on a simulated clock: sleep
  `gap × speed / 86400` s, at most 2 s per gap (`--speed` = real seconds per simulated day,
  0 = no waits). Every step is a real service call (transition + history + outbox event), so
  relay, consumers, SSE, explorer and dashboard see a real flow. Historical times go into the
  order columns, the payload's `occurred_at` and `OrderStatusHistory.occurred_at` (the same
  `now`; `created_at` stays the recording time); outbox/EventLog times stay real. The order
  page's History shows `occurred_at` with the year for replay copies, `created_at` otherwise.
- **Idempotent, resumable:** a step applies only while the copy is in that step's from-status;
  `uniq_replay_copy` (unique `replay_of`) allows one copy per original. SIGINT/SIGTERM sets a
  stop flag: the current step finishes, the run is saved `interrupted`; re-running the range
  resumes without duplicates. Each step's service locks the copy (`select_for_update`) and
  re-checks its status in the transaction that transitions, so even two runners over the same
  orders apply every step once (one Payment, one OrderPaid per copy; tested concurrently).
- **One running replay at a time:** `start_run()` relies on the partial unique index
  `one_running_replay` (status='running'), not a read-then-insert, so two processes starting at
  once can't both win. A run saves `heartbeat_at` at least every 30 s; a `running` run silent
  for 5 min (`STALE_AFTER`: its process died) is marked `failed` and taken over by the next
  `replay_orders` or `replay_reset`. A live run is refused (stop it with Ctrl-C). Every
  runner write (heartbeat, progress, final status) is `UPDATE … WHERE id=? AND
  status='running'`; 0 rows = taken over, so a frozen-then-resumed runner stops before its next
  step (the heartbeat check runs at the top of the loop) and never overwrites `failed`.
  `replay_reset --force` skips the running and backlog checks (last resort).
- **Bypassed, on purpose:** cart/checkout and reservations (would drain real stock; history was
  fulfilled long ago), the payment provider/webhooks/PaymentIntent, emails. Stock never moves.
- **Only the replay moves a replay order:** the sweeper excludes `source='replay'` (copies have
  no reservations anyway); `can_pay`/`can_cancel` are false and cancel/payment/return answer
  409 `replay_read_only`. The order page shows a "Replayed historical order" note.
- `replay_reset [--run N] [--force]` (`make replay-reset`): deletes copies (cascade: items,
  ledger, history) and their outbox / EventLog / ProcessedEvent / Notification rows and runs,
  rebuilds the affected `(day, 'replay')` projections, refreshes product stats. Refuses while a
  live run is `running` or the order stream has unprocessed entries (in-flight events would be
  logged again after their orders are gone). Stream entries stay (acked; trimmed eventually).
  The staff explorer reads only EventLog/ProcessedEvent, so a reset order's timeline is just
  empty, and an event logged after its order was deleted (forced reset) still renders.
- `Order.replay_of` is PROTECT, so deleting an imported order that has a copy fails loudly.
  Nothing deletes orders today: the importer only upserts (verified with copies present:
  0 new rows, offers/stats unchanged), and `make reset` drops the whole schema.
- Throughput (dev laptop, 2,000 orders / 9,896 events at `--speed 0`): the replay writes ~90
  events/s (one transaction per step); relay, event_log, order_live and product_stats keep up
  (p95 < 1.1 s). **`analytics` is the bottleneck** at ~64 events/s (each event re-aggregates
  its whole purchase day): lag peaked ~4,000 entries, p95 75 s, drained ~45 s after the replay
  ended. Fine at `--speed` ≥ 1 (see Known issues). Replay analytics totals equal the imported
  ones (orders, paid, GMV).

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

- Replace `manage.py runserver` (the `backend` service's dev server) with a production WSGI
  server (gunicorn or similar), and serve static files properly.
- Rate-limit `POST /api/auth/login/` and `/register/` (e.g. per IP + per email).
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, HTTPS only (HSTS).
- `CSRF_TRUSTED_ORIGINS` = the real `https://` origin(s) only; `ALLOWED_HOSTS` likewise.
- `ALLOW_FAKE_PAYMENTS` off (it is off in `base.py`; only `dev.py`/`test.py` enable it).
- `DEBUG = False`, a real `DJANGO_SECRET_KEY`, no dev users (`seed_dev_users` refuses without
  `ALLOW_DEV_SEED`).
- A real `REVALIDATE_SECRET`; keep `/internal/revalidate` off the public edge (it's for the
  backend containers only).
- A real `PAYMENT_WEBHOOK_SECRET`, a real `PAYMENT_PROVIDER`, `ALLOW_FAKE_PAYMENTS` off (no fake
  provider URLs), a real SMTP `MAILERS["default"]` and `FRONTEND_PUBLIC_URL`.
- The webhook's HMAC is over the **raw body**. If production routes it through the Next `/api`
  rewrite, verify the bytes arrive unchanged (no re-encoding/decompression), or point the
  provider directly at Django.
- SSE: route `/api/orders/*/stream/` to the ASGI `stream` service (uvicorn behind the proxy,
  `--timeout-graceful-shutdown`). Any proxy in front (nginx etc.): `proxy_buffering off` (or
  honour `X-Accel-Buffering: no`), `proxy_read_timeout` above the 15 s heartbeat, HTTP/1.1 to
  the upstream, no gzip for `text/event-stream`. If it goes through the Next rewrite, keep
  `Cache-Control: no-transform` and the heartbeat under Next's 30 s `proxyTimeout`.
  `DJANGO_ALLOWED_HOSTS` must include the stream service's host.

## Known issues

- Live updates use Redis Pub/Sub, which is fire-and-forget (a subscriber that's briefly away
  misses messages); covered by state-based snapshots, reconnects and the fallback poll.
- One Redis Pub/Sub connection per open stream. Fine for dev and small scale; at scale, use one
  shared subscriber per `stream` process (pattern-subscribe `live:order:*`) fanning out to
  per-connection `asyncio.Queue`s.

- Redis persists streams with AOF `appendfsync everysec`: a hard crash can lose up to ~1 s of
  events the outbox already marked published. Streams are trimmed (`MAXLEN ~ 100000`); a
  consumer group lagging further than that would miss events.

- The `analytics` consumer recomputes an order's whole purchase day per event (~64 events/s),
  so it lags during a `--speed 0` replay. Fix when needed: recompute each distinct (day, source)
  once per read batch (coalesce the batch's events) instead of once per event.

- Replay timestamps for invoiced/canceled/unavailable are synthesized (Olist has none), and one
  Olist order canceled after shipping is replayed as canceled after approval.

- `make e2e` takes ~5–9 min on the isolated stack (measured 2026-11-09: 4:37–8:42 per run): it
  runs a second full stack next to the dev one, and its Next dev server compiles routes under
  memory pressure (cold on the first run: `npm ci` + compiles). `scripts/e2e.sh` warms every route
  the specs enter before Playwright starts. Possible follow-up: run e2e against a production build
  (`next build && next start`) — faster, but it changes behaviour (no dev compiles, prerendering).
- `redis` (redis-py) is pinned to 6.4.0: `kombu[redis]` (Celery's transport) requires `<6.5`.
  It was 8.1.0 in Steps 1–2, used only for the health check.

- next-themes 0.4.6 logs "Encountered a script tag while rendering React component" in the
  browser console under React 19. Harmless (the theme script runs during SSR); no newer
  release yet.
- First visit to a route on the dev server compiles it (can take a minute on macOS bind
  mounts); later requests are fast. `node_modules` and `.next` live in named volumes
  (`frontend_node_modules`, `frontend_next`); `frontend/dev.sh` runs `npm ci` into the volume only
  when `package-lock.json` changes, so new npm dependencies reach the container. Don't use
  anonymous volumes or `--renew-anon-volumes` here: each `make up` orphaned ~1 GB of volumes.

- `npm audit` reports high-severity findings via the `shadcn` package (`braces` / `fast-glob`
  glob handling). `shadcn` is a runtime dependency only so `globals.css` can import
  `shadcn/tailwind.css`; the vulnerable code is CLI dev tooling and is not shipped to the browser.
  **Never run `npm audit fix --force`** — it "fixes" this by downgrading shadcn to 1.x.

## Out of scope (for now)

- Kafka (Redis Streams covers the concepts), Kubernetes, microservices split, real payments
  (Stripe test mode only, in a later step), websockets, push notifications, an event replay
  command (later step), multi-tenant analytics.
