# Testing

There are four kinds of check, each run by its own `make` target:

| Layer | Tool | Runs | Target |
|---|---|---|---|
| Backend | pytest + pytest-django | In the dev `backend` container, against a separate test database and a separate Redis DB | `make test-backend` |
| Frontend unit and component | Vitest + Testing Library (jsdom) | In the dev `frontend` container | `make test-frontend` |
| Types | `tsc --noEmit` | In the dev `frontend` container | `make typecheck` |
| End-to-end smoke | Playwright (Chromium) | On an **isolated** compose project, seeded fresh | `make e2e` |

`make test` runs the first three. There's no CI workflow yet, so a failing test fails only the
local run ([limitations-and-roadmap.md](limitations-and-roadmap.md)).

## Latest run (2026-11-09)

| Suite | Result |
|---|---|
| Backend | **354 passed** (28 test files), 23.2 s |
| Frontend | **91 passed** (25 test files) |
| Typecheck | clean |
| e2e | **5 of 5 full runs passed** (25/25 tests, no retries), after the navigation fix: 3 min 45 s to 6 min 18 s per run |

## Backend (pytest)

[backend/pytest.ini](../backend/pytest.ini) always passes `--ds=config.settings.test`. That
command-line flag overrides `DJANGO_SETTINGS_MODULE` from `.env`, and `test_settings.py` asserts
it. The test settings ([config/settings/test.py](../backend/config/settings/test.py)) isolate
every external system:

| System | In tests |
|---|---|
| Postgres | pytest-django's own test database (created and destroyed by pytest), not the dev database. The tests use real Postgres, because the code relies on `SELECT … FOR UPDATE`, `SKIP LOCKED`, partial indexes, advisory locks and full-text search |
| Redis Streams | The real compose Redis, but **DB 15** and the stream prefix `test-events`. The `events_redis` fixture deletes every `test-events:*` key before and after each test |
| Redis Pub/Sub (live updates) | Channel prefix `test-live`, because Pub/Sub ignores the DB number |
| Celery | `CELERY_BROKER_URL = "memory://"`, so the dev worker never picks up a test task |
| Email | Django's in-memory backend (`mail.outbox`) |
| Payments | The fake provider, with `PAYMENT_WEBHOOK_SECRET = "whsec_test"`. Webhooks are delivered synchronously through the real view by the `run_deliveries` fixture |
| Timings | Short ones: an SSE heartbeat of 0.2 s, streams that close after 3 s, immediate reclaim of pending entries, dead-lettering after 3 deliveries |

### Techniques worth knowing

- **Real concurrency, not mocks.**
  - `run_concurrently()` in [test_concurrency.py](../backend/tests/test_concurrency.py) starts
    functions in separate threads, each with its own database connection, released together by a
    `threading.Barrier`.
  - Tests that use it are marked `django_db(transaction=True)`, so commits are real and visible
    across connections.
  - It covers the last unit of stock, opposite lock orders, duplicate idempotency keys,
    concurrent sweepers, concurrent stats refreshes, the sweeper racing a webhook, analytics
    recomputes of the same day, and two replay runners.
- **Query-count pins.** `django_assert_num_queries` (exact) and `django_assert_max_num_queries`
  (an upper bound) pin the catalog, cart and order endpoints, so an N+1 query fails a test.
- **Messy fixture data.** [tests/fixtures/olist/](../backend/tests/fixtures/olist/) holds tiny
  CSVs with deliberate problems: unknown references, bad amounts, out-of-range scores, duplicates,
  a missing translation, and a review shared by two orders. The importer's skip and note counts
  are asserted.
- **Failure injection.** For example, a webhook that crashes *after* `pay()` has applied
  everything (`test_a_webhook_that_fails_partway_rolls_back_and_applies_once_on_retry`), and a
  consumer that "crashes" between commit and ack.
- **Migration SQL tested inside a transaction.** Postgres DDL is transactional. So
  `test_history_backfill_recovers_replay_times_from_the_event_log`:
  1. drops the `NOT NULL` inside the test's transaction;
  2. nulls the column, and runs the migration's real backfill function;
  3. checks the result.

  The rollback restores everything.
- **Mutation checks: the project's review rule.** A fix is accepted only after its new test has
  been shown to fail without it: the guard is temporarily removed, the test must turn red, then
  the guard is restored. Examples:
  - without the webhook's `transaction.atomic()`,
    `test_a_webhook_that_fails_partway_rolls_back_and_applies_once_on_retry` fails (the order is
    left approved after the crash);
  - without `status='running'` in the replay runner's conditional UPDATE,
    `test_a_taken_over_run_stops_without_writing_further_steps` fails (the taken-over run keeps
    writing);
  - with the stream reading its snapshot before subscribing,
    `test_a_change_committed_while_subscribing_is_not_missed` times out.
- **`django_capture_on_commit_callbacks`** proves that side effects which must wait for a commit
  really do (emails, and the stats refresh).

## Frontend (Vitest)

[frontend/vitest.config.mts](../frontend/vitest.config.mts) runs `src/**/*.test.{ts,tsx}` in jsdom.
The tests cover:
- the URL ⇄ state translation layers: `shop-params`, `staff-params`, `analytics-params`;
- checkout idempotency attempts, the logged-out cart intent, and the API client's timeout
  handling;
- the revalidate route (secret, tag validation);
- the live-order hook (version comparison, fallback polling);
- components with behaviour: order actions, payment confirmation, the order timeline (including
  replay dates), the staff title observer, dead-letter retry, chart gap handling, the auto-refresh,
  filters and the login form.

## End-to-end (Playwright)

Five smoke specs in [frontend/e2e/](../frontend/e2e/):

| Spec | Covers |
|---|---|
| `checkout.spec.ts` | Log in → add to cart → checkout → pay on the fake provider's page → approved, and the confirmation email arrives in Mailpit |
| `order-live.spec.ts` | A 30 s delayed webhook: "Payment in progress" survives a reload, then "Approved" arrives over SSE with exactly one refresh |
| `shop.spec.ts` | Category filter → search → product page → offers |
| `staff-title.spec.ts` (×2) | The staff title holds through a real 10 s dashboard refresh and client navigation; a non-staff visitor only ever gets the neutral title |

### The isolated e2e stack

The checkout and live-order specs place and **pay** real orders. A paid app order can't be
cancelled, so running e2e against the dev stack used to leave two paid orders, lower stock,
emails and events behind on every run. So `make e2e` runs
[scripts/e2e.sh](../scripts/e2e.sh), which uses a **separate compose project**:

```
docker compose -p ecommerce-e2e -f docker-compose.yml -f docker-compose.e2e.yml …
```

[docker-compose.e2e.yml](../docker-compose.e2e.yml) gives the e2e project:
- the database `ecommerce_e2e`, **on tmpfs** (no named volume);
- Redis without persistence, and its own Mailpit;
- **no host ports**.

Each run:

1. **Guard: the project name.** It refuses anything but `ecommerce-e2e`, before any docker call.
2. **Guard: static.** From the merged compose config, every Django service (backend, worker, beat,
   relay, consumers, stream) must have `POSTGRES_DB=ecommerce_e2e` and `POSTGRES_HOST=db`. This
   runs before any container starts.
3. **Start only db, redis, mailpit and backend.** Then the **live guard** on backend:
   - the configured `NAME` and `HOST`;
   - `current_database()`;
   - `inet_server_addr()`, which must equal the e2e db container's IP.
4. **Start worker, beat, relay, consumers, stream and frontend,** and run the live guard on each.
   Any mismatch tears the stack down and exits 3, before anything is written.
5. **Migrate and seed fresh:** the small Olist import, the dev users, the analytics backfill.
6. **Warm** every route the specs enter, then run Playwright.
7. **Tear down** (the tmpfs database and Redis disappear), and exit with Playwright's exit code.
   - `KEEP_E2E=1` keeps the stack, with its frontend on http://localhost:3101.
   - `make e2e-down` removes a kept stack.
   - `ARGS="e2e/shop.spec.ts"` runs one spec. Playwright arguments pass through, for example
     `ARGS="--repeat-each 3"`.

**One run at a time.** Before anything else, the script takes a lock: an atomic `mkdir` of
`e2e-results/.e2e-lock` holding its PID. It refuses (exit 4) while a live process holds the lock,
or while `ecommerce-e2e` containers are already running (a kept stack). Without this, a second
run's first step, `down`, would tear down the first run's stack. A lock left by a dead process is
taken over.

**Evidence survives the run.** The results go to the gitignored `e2e-results/` folder on the host:
- traces and videos of failed tests, and the HTML report (`e2e-results/test-results/`,
  `e2e-results/report/`);
- after a failed run, the frontend, backend and stream container logs, saved before teardown
  (`e2e-results/logs-<UTC time>/`).

**Verified on 2026-11-09:**
- the dev database counts and dev Mailpit were identical before and after six e2e runs;
- no e2e Postgres or Redis volume remained;
- a deliberately failing spec made `make e2e` exit non-zero.

**A fixed flake.** Before the fix, 3 of 6 full-suite runs on 2026-11-09 failed: a form's navigation
never completed (the URL stayed on `/login` or `/checkout`). The kept trace showed the cause:
`router.refresh()` called right after `router.push/replace()` stalled the navigation. The fix
([auth-and-sessions.md](flows/auth-and-sessions.md#after-an-auth-change-a-full-page-load)) has
two parts:
- full page loads after auth changes and checkout;
- JS-driven controls disabled until hydrated.

Then 5 of 5 full runs passed. The helpers wait for a control to be enabled before typing or
clicking, and the login helper submits exactly once.

**Run times:** 3 min 45 s to 8 min 42 s per run. The first run is the slowest, because of
`npm ci` and route compiles. The isolated stack runs the Next **dev** server next to the dev
stack. A production build would be faster, but changes behaviour
([limitations-and-roadmap.md](limitations-and-roadmap.md)).

## Known gaps

- **The payment-after-expiry path is never made to fail partway.** Rollback-on-failure inside the
  webhook's transaction is tested only for the success path
  (`test_a_webhook_that_fails_partway_rolls_back_and_applies_once_on_retry`). For an expired hold,
  `test_success_paid_after_expiry_cancels_and_needs_a_refund` shows the cancel and the refund flag
  landing together, but no test crashes that path and checks that both roll back.
- **The staff endpoints have no query-count tests.** The catalog, cart and order endpoints do.
- **No CI.** The suites run only locally.
- **Pages are covered only by e2e smoke.** Many presentational shop, layout and dashboard
  components have no unit tests, and there are no visual or accessibility tests for either theme.
- **One email gap can't be closed by a test.** A crash after SMTP accepted a message, but before
  its row is marked sent, resends that email once ([flows/notifications.md](flows/notifications.md)).
- **No automated performance tests.** The throughput figures in [flows/replay.md](flows/replay.md#throughput)
  come from one measured run, not a regression test.
- **The importer's `large` mode** is tested only on the tiny fixtures, never on the full dataset
  in the test suite.

## Sources

- [backend/pytest.ini](../backend/pytest.ini), [backend/config/settings/test.py](../backend/config/settings/test.py), [backend/tests/conftest.py](../backend/tests/conftest.py), [backend/tests/](../backend/tests/)
- [frontend/vitest.config.mts](../frontend/vitest.config.mts), [frontend/playwright.config.ts](../frontend/playwright.config.ts), [frontend/e2e/](../frontend/e2e/)
- [scripts/e2e.sh](../scripts/e2e.sh), [docker-compose.e2e.yml](../docker-compose.e2e.yml), [docker-compose.e2e-keep.yml](../docker-compose.e2e-keep.yml), [Makefile](../Makefile)
