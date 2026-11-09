# Runbook

How to run, check and fix the local stack. Every `make` target is listed in CLAUDE.md's commands
table. This page is task-oriented: what to run, what to look at, and what is safe.

## First run

1. **Prerequisites:** Docker with Compose v2 (the e2e stack uses `!reset` overrides, which need a
   recent Compose; tested with v5.5.1), `make`, and `python3` for `make docs-check`.
2. **Data:** download the "Brazilian E-Commerce Public Dataset by Olist" from
   [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Unzip it, and put the
   CSVs **directly** in `data/olist/` (the folder is gitignored). The importer fails with a list
   of the missing files if they're not there.
3. **Config:** `cp .env.example .env`. Every `make` target refuses to run without `.env`.
   - Change host ports there if they clash: `DB_HOST_PORT`, `REDIS_HOST_PORT`,
     `BACKEND_HOST_PORT`, `FRONTEND_HOST_PORT`, `MAILPIT_HOST_PORT`.
   - If you change the frontend port, also update `CSRF_TRUSTED_ORIGINS` and
     `FRONTEND_PUBLIC_URL` to match.
4. **Start:** `make up` builds and starts every service, and waits until they're running.
5. **Create the schema and data:** `make migrate`, then `make seed`.
   - `make seed` imports the small Olist subset, creates the dev users, and builds the analytics
     projections.
   - On an empty database this is all you need.
   - `make reset` does the same, but **drops the database first** (see below).

Then open the site at `http://localhost:<FRONTEND_HOST_PORT>`, the API docs at
`http://localhost:<BACKEND_HOST_PORT>/api/docs/`, and Mailpit via `make mail`.

**Dev accounts** (password `DEV_USER_PASSWORD` from `.env`, default `devpass123`):
- `admin@example.com` (superuser);
- `staff@example.com` (staff tools);
- `customer@example.com`;
- `replay@example.com` (owns replayed orders).

## Daily use

| Task | Command |
|---|---|
| Start / stop | `make up` / `make down` (data volumes are kept) |
| Follow the event pipeline | `make events-logs` (relay, consumers, stream) |
| Follow Celery | `docker compose logs -f worker beat` |
| Find the emails | `make mail` prints the Mailpit URL |
| Regenerate API types after a serializer change | `make types` |
| Run the tests | `make test` (backend + frontend + typecheck), `make e2e` (isolated stack, see [testing.md](../testing.md)) |
| Check the docs | `make docs-check` |

## Data safety

Some targets **destroy or replace** data in the dev database, and others only add to it. Before
running a destructive one on a database whose contents matter, take a snapshot.

| Target | Effect on the dev database |
|---|---|
| `make reset` | **Destructive.** `DROP SCHEMA public CASCADE`, deletes the `events:*` streams, then migrate + seed |
| `make restore` | **Destructive.** `pg_restore --clean` of the newest dump in `data/snapshots/`. The current data is replaced. Redis streams aren't in the dump |
| `make replay-reset` | **Destructive** for replay data only: deletes replay copies and everything they produced |
| `make seed`, `make seed-large` | Additive and idempotent: upserts on Olist natural keys, never overwrites live stock |
| `make replay` | Additive: creates replay copies (`source='replay'`). The shop's figures ignore them |
| `make analytics-backfill`, `make backfill-sales` | Recompute derived data from the orders. Safe to re-run |
| `make snapshot` | Read-only: `pg_dump` into `data/snapshots/` |
| `make e2e` | **Doesn't touch the dev database.** It runs a separate compose project with its own database |

**Restoring a snapshot.** `make restore` restores the database, not Redis. Afterwards:
- events that were still in the outbox are published again by the relay;
- stream entries from after the snapshot remain in Redis. They describe data the database no
  longer has.

So a full clean slate is `make reset`. To get back to a snapshot's data, use `make restore`, and
expect the event log and stream contents to differ from the database's history.

## Symptoms and fixes

| Symptom | Check | Fix |
|---|---|---|
| The relay and consumers log "waiting for the events tables" | Have migrations run? | `make migrate`. They wait instead of failing, and start by themselves once the tables exist |
| A product page shows stale stock or price | `/staff/health`: `cache_invalidation` pending or lag, dead letters | Start the consumers and frontend if they're down. Retry a dead letter from `/staff/health`. The page also refreshes itself within 5 min (`revalidate: 300`) |
| `sales_count` or "Most popular" lags | `/staff/health`: `product_stats` lag | Usually seconds. During a `--speed 0` replay, wait for the backlog to drain. Replay events don't change sales counts anyway |
| The analytics dashboard lags during a replay | `/staff/health`: `analytics` lag | Expected at `--speed 0` (the measured peak was ~4,000 entries). Use `--speed` ≥ 1, or wait ([flows/analytics.md](../flows/analytics.md#performance)) |
| `/api/health` shows an outbox backlog | Is the `relay` service running? Its log shows the Redis errors | `docker compose up -d relay`. It resumes from the oldest unpublished row; nothing is lost |
| Events in the dead-letter list | `/staff/health`: the consumer, error and delivery count | Fix the cause (for example, a frontend that was down), then **Retry**. Only the failed consumer applies it again ([flows/staff-tools.md](../flows/staff-tools.md#dead-letter-retry)) |
| An email didn't arrive | Mailpit (`make mail`); `Notification` rows in the admin (`status`, `attempts`, `last_error`) | Pending rows retry with backoff, and beat sends due ones every 30 s. A `failed` row has used all 8 attempts. Check the SMTP settings |
| The order page doesn't update live | The browser network tab: `/api/orders/<id>/stream/`; `docker compose logs stream` | Make sure the `stream` service is running and `STREAM_URL` is set. The page falls back to a 15 s refresh by itself |
| An unpaid order isn't cancelled after 15 min | `docker compose logs worker beat` | Both `beat` and `worker` must run. The sweeper runs every 60 s |
| "Replay #N is running" when starting a replay | Is another replay process running? | Stop it (Ctrl-C). A dead run (no heartbeat for 5 min) is taken over automatically. `make replay-reset ARGS=--force` is the last resort |
| `replay_reset` refuses: unprocessed order events | `/staff/health`: order-stream lag | Wait until the consumers have caught up |
| The first visit to a page takes a minute | It's the Next dev server compiling the route | Expected on the first request after a start. Later requests are fast |
| Behaviour doesn't match the code after a pull or a branch switch | Which services reload code by themselves: `backend` (runserver), `stream` (uvicorn `--reload`) and `frontend` (Next dev) do; **`consumers`, `relay`, `worker` and `beat` don't**, they keep running the code they started with | `docker compose restart consumers relay worker beat stream`. During Step 7c, a stale `consumers` process sent emails for replayed orders, which the new code skips |
| A port is already in use at `make up` | Another local service is using it | Change the `*_HOST_PORT` in `.env` (and the frontend origins, see First run) |
| A new npm dependency is missing in the container | `frontend/dev.sh` reinstalls when `package-lock.json` changes | `make up` (it rebuilds and restarts the frontend) |
| `npm audit` reports `shadcn`-related findings | Known: they're in the CLI tooling, not shipped code | **Never** `npm audit fix --force`: it downgrades shadcn to 1.x |

## Upgrading an older checkout

New settings have arrived in `.env.example` over time: events, payments, email, the stream
service. After pulling:
1. Compare your `.env` with `.env.example`, and add the missing blocks.
2. `make up && make migrate`.
3. Restart the long-running processes, which don't reload code on their own:
   `docker compose restart consumers relay worker beat stream`.
4. For data from before the order flow counted cancellations correctly, run `make backfill-sales`
   once.

## Production

This stack is for local development. CLAUDE.md's "Before deploying" section is the checklist for
any other environment. Its main items:
- a production WSGI server instead of `runserver`;
- secure cookies and HTTPS;
- real secrets;
- the fake payment provider off;
- rate limiting on login;
- proxy settings for the SSE stream.

See [limitations-and-roadmap.md](../limitations-and-roadmap.md).

## Sources

- [Makefile](../../Makefile), [docker-compose.yml](../../docker-compose.yml), [.env.example](../../.env.example), [scripts/e2e.sh](../../scripts/e2e.sh)
- [backend/apps/core/health.py](../../backend/apps/core/health.py), [backend/apps/staff/services.py](../../backend/apps/staff/services.py), [backend/apps/events/readiness.py](../../backend/apps/events/readiness.py)
