# The lab: where the exercises run

Every exercise in `docs/concepts/` says where it runs: **A**, **B** or **C**. The one rule
behind all three: **nothing ever writes to, or locks rows in, the dev database.** The dev
database holds data you've built up (seeded orders, replays, app orders), and a held lock there
would stall the running stack (the sweeper, the consumers, checkout).

| Venue | What it is | Allowed |
|---|---|---|
| **A. The lab stack** | The isolated e2e compose project (`ecommerce-e2e`), seeded fresh, left running | Everything: writes, locks, two concurrent sessions, Redis commands, checkout and payment in a browser |
| **B. The dev database, read-only** | Your dev stack's Postgres | `SELECT` and `EXPLAIN` only. No `FOR UPDATE`, no `INSERT`/`UPDATE`/`DELETE`, no constraint-violation demos |
| **C. The test suite** | pytest in the dev `backend` container: its own test database and Redis DB 15 | Mutation exercises: change a guard in the code, watch the named test fail, restore the file |

## A. The lab stack

### Start and stop

```sh
make lab-up      # start + seed the isolated stack, leave it running (a few minutes)
make lab-down    # remove it: containers and network; the database (tmpfs) and Redis go with them
```

`make lab-up` runs [scripts/e2e.sh](../../scripts/e2e.sh) in lab mode. It's the same script
`make e2e` uses, with the same safety checks, stopping just before Playwright
([testing.md](../testing.md#the-isolated-e2e-stack)):
- **Project name.** It refuses any compose project other than `ecommerce-e2e`.
- **Static check.** Before anything starts, every Django service's configuration must point at
  the database `ecommerce_e2e` on the e2e `db` container.
- **Live check.** On each running Django service, it compares the configured database, the
  connected database and the server's IP with the e2e database container's.
- **One at a time.** The run lock is held, and a stack that's already running is refused.
- **Fresh data.** It migrates and seeds the small Olist subset, the dev users and the analytics,
  then warms the routes.

If any step fails, the stack is torn down. A started lab stack also blocks `make e2e` (and a
second `make lab-up`) until `make lab-down`. `make lab-down` leaves only the frontend's dependency
caches (the `ecommerce-e2e_*node_modules` and `ecommerce-e2e_frontend_next` volumes), kept on
purpose so the next start is fast; no data survives.

Measured on 2026-11-12: `make lab-up` took 65 s (warm caches), every static and live check
passed, and only ports 3101 and 8125 were published.

What you get:

| | Where |
|---|---|
| The site | http://localhost:3101, with the dev accounts (`customer@example.com`, `staff@example.com`, password `DEV_USER_PASSWORD` from `.env`) |
| Mailpit (every email the lab sends) | http://localhost:8125 |
| Postgres, Redis, Django shell | Not published on the host: use the `lab` alias below |

### The `lab` alias

Run these from the repo root (the `-f` paths are relative), in an interactive shell (a script
doesn't expand aliases; spell the command out there):

```sh
alias lab='docker compose -p ecommerce-e2e -f docker-compose.yml -f docker-compose.e2e.yml -f docker-compose.e2e-keep.yml'

lab exec db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'   # psql on ecommerce_e2e
lab exec redis redis-cli                                      # Redis (no persistence)
lab exec backend python manage.py shell                       # Django shell, lab settings
lab logs -f consumers relay                                   # follow the event pipeline
```

`$POSTGRES_DB` is expanded **inside** the lab's `db` container, where it is `ecommerce_e2e`.

**Check where you are** before anything that writes:

```sql
SELECT current_database();   -- must be ecommerce_e2e
```

### Two sessions

Concurrency exercises need two `psql` sessions at once: open two terminals and run the `psql`
line in each. Label them, so the steps "in S1" and "in S2" are easy to follow:

```sql
\set PROMPT1 'S1 %/%R%# '    -- in the first terminal
\set PROMPT1 'S2 %/%R%# '    -- in the second
```

Some exercises create a scratch table (named `lab_…`). It lives only in the lab database, and
`make lab-down` throws it away with everything else.

## B. The dev database, read-only

```sh
docker compose exec -e PGOPTIONS='-c default_transaction_read_only=on' db \
  sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

- **The `PGOPTIONS` setting makes every transaction in that session read-only by default.** An
  accidental `UPDATE` is then rejected, instead of changing your data
  ([default_transaction_read_only](https://www.postgresql.org/docs/17/runtime-config-client.html#GUC-DEFAULT-TRANSACTION-READ-ONLY),
  [setting parameters via `PGOPTIONS`](https://www.postgresql.org/docs/17/config-setting.html#CONFIG-SETTING-SHELL)).
- **Checked on 2026-11-12:** in such a session, an `UPDATE` fails with "cannot execute UPDATE in a
  read-only transaction".
- **It's a guard against accidents, not a security boundary.** The session itself could turn it
  off. Venue B exercises use only `SELECT` and `EXPLAIN` anyway.
- **Why not `FOR UPDATE` here, even inside `BEGIN … ROLLBACK`?** A row lock on the dev database
  blocks the live stack while you hold it. And a rollback isn't free: sequence values taken by an
  `INSERT` are never given back
  ([sequence functions](https://www.postgresql.org/docs/17/functions-sequence.html)).

## C. The test suite (mutation exercises)

Mutation exercises are the project's review rule turned into practice
([testing.md](../testing.md#techniques-worth-knowing)): remove a guard, and the test that
protects it must turn red.

Each one follows the same protocol. `FILE` is the one file the exercise tells you to change:

```sh
FILE=backend/apps/orders/services.py      # the exercise names it

# 1. Refuse if the file already has uncommitted changes: step 4 would throw them away
git diff --quiet -- "$FILE" && git diff --cached --quiet -- "$FILE" \
  || { echo "REFUSE: $FILE has uncommitted changes. Commit or stash them first."; }
git status --short                        # note the starting state

# 2. Make the one change the exercise describes, in $FILE only
# 3. Run the named test
docker compose exec backend pytest tests/test_concurrency.py -k two_buyers

# 4. Restore the file (this discards every uncommitted change in it, hence step 1)
git checkout -- "$FILE"

# 5. Prove it: no diff in the file, and the same `git status` as in step 1
git diff --quiet -- "$FILE" && echo "restored" ; git status --short
```

**If step 1 prints REFUSE, stop.** `git checkout -- <file>` can't tell your mutation from earlier
work in the same file. Commit or `git stash` that work first, then start again.

- **Where tests run.** They use the dev stack's `backend` container, but pytest always uses
  `config.settings.test`. That means its own test database (created and dropped by pytest), Redis
  DB 15 with the `test-events` prefix, and an in-memory Celery broker. **The dev database isn't
  touched** ([testing.md](../testing.md#backend-pytest)).
- **Keep the mutation short.** Every backend container bind-mounts `./backend`, the lab stack's
  included. `backend` (runserver) reloads code on save, so the dev API, and the lab's if it's up,
  run the mutated code while it's in place. Don't run a mutation while `make lab-up` is still
  setting up. Restore it right after the test run. The `consumers`, `relay`,
  `worker` and `beat` processes don't reload on save, so they keep running the committed code,
  unless one restarts while the mutation is in place
  ([runbook](../operations/runbook.md#symptoms-and-fixes)).

> **Never commit a mutated file.** Step 5 is there to prove the tree is back to where it was. If
> it doesn't print "restored", or `git status` differs from step 1, run step 4 again before doing
> anything else.

## Checking that the dev database is untouched

Before and after a session of exercises, take the same snapshot of the dev database's counts
(venue B, read-only). The two results must be identical:

```sql
SELECT (SELECT count(*) FROM orders_order)              AS orders,
       (SELECT sum(stock) FROM catalog_offer)           AS stock,
       (SELECT count(*) FROM events_outboxevent)        AS outbox,
       (SELECT count(*) FROM events_eventlog)           AS event_log,
       (SELECT count(*) FROM notifications_notification) AS notifications;
```

They may differ only if you used the dev site yourself in between. **Never run** `make reset`,
`make restore`, `make replay` or `make replay-reset` for an exercise: everything an exercise
needs is on the lab stack.

## Sources

- [scripts/e2e.sh](../../scripts/e2e.sh), [docker-compose.e2e.yml](../../docker-compose.e2e.yml), [docker-compose.e2e-keep.yml](../../docker-compose.e2e-keep.yml), [Makefile](../../Makefile) (`lab-up`, `lab-down`)
- [backend/pytest.ini](../../backend/pytest.ini), [backend/config/settings/test.py](../../backend/config/settings/test.py)
