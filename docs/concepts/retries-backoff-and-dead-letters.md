# Retries, backoff and dead letters

## What it is

Things fail **transiently** (a dependency restarting, a timeout, a lock conflict) or
**permanently** (a malformed message, a bug, a missing record). A retry policy decides what to do
about a failure without knowing which kind it is:

- **Retry** at all, and how many times. Retrying a permanent failure only wastes work; never
  retrying turns every blip into an error.
- **Backoff:** wait longer between attempts, usually exponentially (0.5 s, 1 s, 2 s, … up to a
  cap), so a struggling dependency gets room to recover.
- **Jitter:** randomise the waits, so many clients that failed together don't retry together. Marc
  Brooker's analysis for AWS concludes that jittered backoff is worth its small complexity and
  should be standard for remote clients
  ([Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/), 2015).
- **Give up:** after N attempts, stop retrying and put the item somewhere visible. For messages
  that's a **dead-letter queue** (DLQ): the message that keeps failing (a **poison message**) is
  moved aside, so it stops blocking or burning the work behind it, and a person can inspect it,
  fix the cause, and retry.

Two properties make retries safe:
- **The operation is idempotent,** because a retry may repeat work that half-succeeded
  ([idempotency.md](idempotency.md)).
- **The retry state is durable** where it matters. A retry schedule kept in memory dies with the
  process; one kept in a database row or a broker's pending list survives.

## The problem it solves

```text
Without backoff:   fail, retry, fail, retry, …  hundreds of attempts per second against a
                   dependency that is already down; the logs drown, the dependency can't recover.
Without a cap:     one poison message is retried forever; with ordered processing it blocks
                   everything behind it.
Without jitter:    1,000 clients fail at 12:00:00, all retry at 12:00:01, 12:00:03, 12:00:07…
                   in lockstep, a synchronized storm at each step.
```

```mermaid
sequenceDiagram
    participant C as Consumer
    participant S as Stream (pending list)
    participant D as Dead-letter stream
    participant O as Staff
    C->>S: delivery 1: handler fails, rollback, no ack
    Note over S: stays pending; reclaimed once idle ≥ 60 s
    C->>S: deliveries 2–5: fail again
    C->>D: delivery 6 > max (5): copy to events:dlq with the error · ack the original
    O->>D: fix the cause, click Retry
    D->>S: same fields (same event id) re-added once
    C->>S: applied; groups that already had it just ack
```

## In this project

Every retry loop, side by side:

| Where | Retries | Backoff | Gives up | Retry state lives in |
|---|---|---|---|---|
| Relay, Redis errors ([relay.py](../../backend/apps/events/relay.py)) | Forever | 0.5 s doubling, capped at 30 s, ×0.8–1.2 jitter | Never (the outbox holds the events) | Process memory; each failed row records `attempts` and `last_error` |
| Consumer loop, Redis errors ([consumer.py](../../backend/apps/events/consumer.py)) | Forever | 0.5 s doubling, capped at 30 s, no jitter | Never | Process memory |
| Event handler failures (any consumer) | Up to `EVENTS_MAX_DELIVERIES` (5) deliveries | Natural: an entry is reclaimed once idle for `EVENTS_CLAIM_IDLE_MS` (60 s), with a claim sweep every 30 s | Copied to `events:dlq` with the consumer, delivery count and last error, then acked | Redis: the pending list and its delivery counts |
| Dead letters (`/staff/health`) | Once per DLQ entry, by a person | — | — | `DeadLetterRetry` (unique per DLQ entry) |
| Email sending ([sender.py](../../backend/apps/notifications/sender.py)) | Up to `NOTIFICATION_MAX_ATTEMPTS` (8) | 30 s doubling, capped at 1 h | Row marked `failed`, error logged | The `Notification` row (`attempts`, `next_attempt_at`); beat sends due rows every 30 s |
| Fake provider webhook delivery ([fake_provider/tasks.py](../../backend/apps/fake_provider/tasks.py)) | Up to 6 retries | 5 s doubling, capped at 5 min | Celery stops retrying | Celery (`self.retry`) |
| Stats refresh on deadlock ([stats.py](../../backend/apps/catalog/stats.py)) | Up to 3 attempts, only for SQLSTATE `40P01` or `40001` | 50 ms × attempt | Raises (logged; it runs `robust` after commit) | Process memory |
| Checkout in the browser ([checkout-attempt.ts](../../frontend/src/lib/checkout-attempt.ts)) | When the person clicks "Retry placing order" after a network error or 5xx | — | — | The same idempotency key, in `sessionStorage` |
| Live order page | EventSource reconnects on its own | `retry: 3000` ms from the server; a 15 s fallback refresh if EventSource gives up | — | The browser |

Notes:
- **Handler retries need no timer.** A failed handler rolls back and doesn't ack, so the entry
  just stays pending. Reclaiming it after 60 s idle *is* the backoff, and the delivery count kept
  by Redis is the attempt counter ([redis-streams-and-pubsub.md](redis-streams-and-pubsub.md)).
- **The dead letter keeps the event retryable.** The DLQ entry copies the original fields (same
  event id) plus `dlq_consumer`, `dlq_stream`, `dlq_entry_id`, `dlq_deliveries` and `dlq_error`.
  Retrying re-adds the original fields to the stream once. Every group sees the new entry; groups
  that had already applied it find their `ProcessedEvent` row and ack; only the consumer that
  dead-lettered it applies it ([staff-tools.md](../flows/staff-tools.md#dead-letter-retry),
  `test_retry_redelivers_a_dead_letter_once_and_only_the_failed_consumer_applies_it`).
- **Jitter is used where several instances could retry in step** (relays). The single consumer
  process and Celery's webhook retries don't add it; that's fine at one instance each, and the
  first thing to change if they were scaled out.
- **What's retried is idempotent:** handlers dedupe through `ProcessedEvent`, webhooks through
  `ProviderEvent`, emails through the row's status, checkout through its key.

## Pitfalls

- **Retrying non-idempotent work.** A retry after a timeout may be the second execution.
- **Retrying permanent errors.** Classify where you can: the stats refresh retries only deadlocks
  and serialization failures, never other errors.
- **Retry state in memory for work that must survive a restart.** Keep it in a row or in the
  broker's pending list.
- **No cap, or a DLQ nobody looks at.** A dead-letter queue is only useful if it's visible (here on
  `/staff/health`) and retryable.
- **Retrying a dead letter without fixing the cause.** It will dead-letter again; keep the error
  with the entry so the cause is visible.
- **Retries multiplying across layers.** A client retrying 3 times, through a server that retries
  3 times, makes 9 calls to the database. Retry at one layer.

## Interview follow-ups

- **Why exponential backoff, and why jitter?** Backoff gives a failing dependency time to recover
  and limits load; jitter spreads out clients that failed at the same moment, so their retries
  don't arrive in synchronized waves.
- **What's a poison message, and what do you do with it?** A message that fails every time. After N
  attempts, move it to a dead-letter queue with its error, ack the original so the rest flows, and
  let a person fix the cause and replay it.
- **How do you replay a dead letter safely?** Re-deliver the original message (same id), and rely on
  consumer-side dedupe, so consumers that already applied it skip it.
- **Where should retry state live?** Wherever it must survive: a database row for scheduled retries,
  the broker's pending list for message redelivery; in memory only for in-process loops.
- **When shouldn't you retry?** On permanent errors (validation, not found, a bug), and on
  non-idempotent operations without a key.

Project-specific questions: [interview-guide.md](../interview-guide.md#event-pipeline).

## Exercises

### 1. Dead-letter an event, then retry it

**Runs on: A** (lab stack; about 8 minutes, mostly waiting).

1. Stop the lab's frontend, so the `cache_invalidation` consumer's call to it fails:
   `lab stop frontend`
2. In the Django shell, record a `ProductsChanged` event for a real product, as `product_stats`
   would:
   ```python
   from django.db import transaction
   from apps.catalog.models import Product
   from apps.events.outbox import record_event
   p = Product.objects.order_by("id").first()
   with transaction.atomic():
       e = record_event("ProductsChanged", "product", str(p.id), {"product_ids": [p.id], "slugs": [p.slug]})
   print(e.id)
   ```
3. Watch it fail and come back: `lab logs -f consumers | grep cache_invalidation`, and in
   `lab exec redis redis-cli`: `XPENDING events:product cache_invalidation - + 10` (the delivery
   count rises about once a minute).
4. After the sixth delivery, look at the dead-letter stream: `XRANGE events:dlq - +`
5. `lab start frontend`. Log in as `staff@example.com` with the
   [curl helper](lab.md#calling-the-lab-api-with-curl), then retry the entry:
   `api POST /api/staff/dead-letters/<dlq entry id>/retry/ '' -i`. Send it a second time.
6. In `psql`:
   `SELECT consumer FROM events_processedevent WHERE event_id = '<event id>' ORDER BY 1;`

**Expected:**
- **Steps 3–4:** the delivery count rises from 1 to 5, about once a minute. At the sixth delivery
  (about 5.5 minutes in, on 2026-11-12) the entry leaves the pending list, and `events:dlq` holds a
  copy with `dlq_consumer` `cache_invalidation`, `dlq_deliveries` `6` and the error in `dlq_error`
  (with the frontend container stopped its hostname no longer resolves:
  `RevalidateError: revalidate failed: <urlopen error [Errno -2] Name or service not known>`).
- **Step 5:** both retries answer `200` with the same retry record: `"created": true` the first
  time, `"created": false` the second.
- **Step 6:** `cache_invalidation` and `event_log` each appear once.

<details><summary>Solution</summary>

Each failed attempt rolled back, so `cache_invalidation` never wrote a `ProcessedEvent` row, and
the entry stayed pending. The claim sweep took it over every time it had been idle for 60 s, each
time counting a delivery. Above `EVENTS_MAX_DELIVERIES` the next delivery moved it to the DLQ
instead of running it, and acked it, so the group's pending list was clean again. `event_log` had
logged the event on the first try; it's unaffected. The retry re-added the same event id:
`event_log` found its row and just acked, and `cache_invalidation`, with the frontend back, applied
it. The second click found the `DeadLetterRetry` row and did nothing.
</details>

### 2. Remove the delivery cap

**Runs on: C** ([mutation protocol](lab.md#c-the-test-suite-mutation-exercises)).

0. Check the file is unmodified, or stop and commit or stash first:
   `git diff --quiet -- backend/apps/events/consumer.py && git diff --cached --quiet -- backend/apps/events/consumer.py && echo clean`
1. In [backend/apps/events/consumer.py](../../backend/apps/events/consumer.py), in `_process()`,
   delete the two lines `if deliveries > settings.EVENTS_MAX_DELIVERIES:` and the
   `self._dead_letter(...)` / `return` under them.
2. `docker compose exec backend pytest tests/test_events_consumer.py -k poison_event`
3. Restore and prove it: `git checkout -- backend/apps/events/consumer.py`, then
   `git diff --quiet -- backend/apps/events/consumer.py && echo restored` and `git status --short`.
   Never commit the mutated file.

**Expected:** the test fails: after the fourth delivery the event is still pending (attempted again)
and the dead-letter stream is empty.

<details><summary>Solution</summary>

Without the cap, a poison event is retried forever: every claim sweep runs it again, it fails
again, and it never leaves the pending list. Nothing alerts anyone; the logs just repeat. The cap
plus the DLQ turn "fails forever, silently" into "fails five times, then waits visibly for a
person".
</details>

### 3. Retry state in the dev database

**Runs on: B** (dev database, read-only).

```sql
SELECT status, count(*), max(attempts) AS max_attempts, max(last_error) <> '' AS any_error
FROM notifications_notification GROUP BY 1;
SELECT count(*) FILTER (WHERE attempts > 0) AS rows_that_ever_failed FROM events_outboxevent;
```

**Expected:** with a healthy Mailpit, every notification is `sent` with 1 attempt, and no outbox row
has failed. Anything else is a story: which email, which error, how many attempts.

<details><summary>Solution</summary>

Both tables keep their retry state on the row: `attempts`, `last_error` and, for emails,
`next_attempt_at`. That's what lets a retry survive a restart of the sender or the relay, and what
lets you answer "did this ever fail?" afterwards. In-memory retry loops (the consumer's Redis
backoff) leave no such trace; only the logs.
</details>

**Run status:** all three run on 2026-11-12. Venue A on the lab stack (`make lab-up`), driven by a
script that ran the listed commands and polled `XPENDING` every 20 s; venue B read-only; venue C with
the [mutation protocol](lab.md#c-the-test-suite-mutation-exercises). **One correction:** I had
predicted `201` for the first retry; the endpoint answers `200` both times and says which one created
the retry in `"created"`. Everything else matched: the dev database had 79 notifications, all sent
at the first attempt, and no outbox row had ever failed.

## Further reading

- Marc Brooker, [Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/) (AWS Architecture Blog, 2015)
- Redis: [XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/) (the delivery counter), [XPENDING](https://redis.io/docs/latest/commands/xpending/)
- Celery 5.6: [task_acks_late](https://docs.celeryq.dev/en/v5.6.0/userguide/configuration.html#std-setting-task_acks_late) and the FAQ it links on `acks_late` vs retry
- Project: [event-pipeline.md: recovery and dead letters](../flows/event-pipeline.md#recovery-and-dead-letters), [staff-tools.md: dead-letter retry](../flows/staff-tools.md#dead-letter-retry), [notifications.md](../flows/notifications.md)

**Verified** 2026-11-12 against the article and documentation pages linked above.
