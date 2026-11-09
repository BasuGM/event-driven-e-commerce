# Event-driven e-commerce

A learning/portfolio e-commerce platform built around events: Django + DRF backend, Next.js
frontend, PostgreSQL and Redis, all run with Docker Compose. It is seeded with the real
[Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
so there is realistic data from day one.

## Prerequisites

- Docker with Docker Compose v2
- Node.js 22+ (only needed to run frontend tooling outside the containers)
- `make`

## Olist data

Download "Brazilian E-Commerce Public Dataset by Olist" from Kaggle (link above), unzip it and
put the CSVs **directly** in `data/olist/` (e.g. `data/olist/olist_orders_dataset.csv`). The
folder is gitignored. The geolocation CSV is not used yet.

## Setup

```sh
cp .env.example .env   # adjust host ports here if 5432/6379/8000/3000 are taken
make up                # build and start db, redis, backend, Celery worker + beat, event relay +
                       # consumers, the SSE stream service, Mailpit, frontend
make reset             # create the schema, import ~2,000 orders, create dev users
```

`make seed-large` imports the full dataset (~1 minute). `make test` runs the backend and
frontend tests plus a typecheck; `make e2e` runs the Playwright smoke test against the running
stack. See `CLAUDE.md` for the full command list and project conventions.

Olist has no product names, prices or stock, so the import generates them deterministically
(see "Data rules" in `CLAUDE.md`).

## URLs (default ports)

| What              | URL                              |
|-------------------|----------------------------------|
| Dashboard         | http://localhost:3000            |
| Shop              | http://localhost:3000/shop       |
| API docs (Swagger)| http://localhost:8000/api/docs/  |
| Django admin      | http://localhost:8000/admin/     |

## Dev login

`make reset` / `make seed` create three dev-only accounts — `admin@example.com` (superuser),
`staff@example.com` and `customer@example.com` — all with the password `DEV_USER_PASSWORD` from
`.env` (default `devpass123`). Log in on the site with the email; the Django admin accepts the
username (`admin`).

## Buying something (dev)

Log in as `customer@example.com`, open a product, **Add to cart** on an offer, then **Cart →
Checkout**. Placing the order holds the stock for 15 minutes (`RESERVATION_TTL_MINUTES`). On the
order page click **Pay**: you land on **FakePay**, a dev-only payment page that behaves like
Stripe Checkout (`ALLOW_FAKE_PAYMENTS`). Choose succeed, fail or "succeed after a delay", and
optionally have each webhook delivered twice or out of order. You're sent back to the order,
which shows "Payment in progress" and updates live (Server-Sent Events) when the signed webhook
arrives via the Celery `worker`, without polling or reloading. If you don't pay, the
`beat` + `worker` services cancel the order and return the stock within a minute of expiry.

Staff tools: log in as `staff@example.com` and use the **Staff** link: the event log (every
domain event, filterable), per-order event timelines with consumer status, and event health
(consumer lag, outbox backlog, dead letters with a Retry button). The **Analytics** tab is a staff dashboard
(orders, GMV, cancellations, delivery performance) per source: imported Olist history vs orders
placed in the app.

Order emails (received, paid, failed, canceled, expired, refund due) are caught by Mailpit:
open the URL from `make mail` (default http://localhost:8025).

## Events (dev)

Every order change (placed, paid, payment failed, canceled, expired) writes an event to the
outbox in the same transaction; the `relay` service publishes it to Redis Streams and the
`consumers` service reacts: it updates the product's sales count and tells Next.js to refresh
the cached product page. Watch it with `make events-logs`; the dashboard's health badges show
the outbox backlog.

Upgrading an existing checkout: add the `# --- Events ---`, `# --- Payments ---` and
`# --- Email ---` blocks from `.env.example` to your `.env` (set `FRONTEND_PUBLIC_URL` to your
frontend port), run `make up && make migrate`, then `make backfill-sales` once (older data counted
canceled orders as sales).
