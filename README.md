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
                       # consumers, frontend
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
order page use **Simulate payment success / failure** (dev only, `ALLOW_FAKE_PAYMENTS`). If you
don't pay, the Celery `beat` + `worker` services cancel the order and return the stock within a
minute of expiry (`docker compose logs -f worker`).

## Events (dev)

Every order change (placed, paid, payment failed, canceled, expired) writes an event to the
outbox in the same transaction; the `relay` service publishes it to Redis Streams and the
`consumers` service reacts: it updates the product's sales count and tells Next.js to refresh
the cached product page. Watch it with `make events-logs`; the dashboard's health badges show
the outbox backlog.

Upgrading an existing checkout: add the `# --- Events ---` block from `.env.example` to your
`.env` (`REVALIDATE_SECRET`, `FRONTEND_INTERNAL_URL`), run `make up && make migrate`, then
`make backfill-sales` once (older data counted canceled orders as sales).
