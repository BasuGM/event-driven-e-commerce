# 0002. Transactional outbox + dedicated relay

- **Status:** Accepted
- **Date:** 2026-10-23 (commit `b633ef4`, Step 4)

## Context

A state change (an order is paid) and its event (`OrderPaid`) must be consistent: an event for a
change that rolled back is a lie, and a change without its event is silently lost downstream.
Postgres and Redis can't share a transaction, so writing to both is a **dual write**.

## Options considered

1. **Publish to Redis inside the service, before commit.** If the transaction then rolls back,
   the event announced a change that never happened.
2. **Publish after commit** (`transaction.on_commit`). If the process dies between the commit and
   the publish, the event is lost, and nothing would ever notice.
3. **Change data capture** (for example Debezium tailing the Postgres WAL). It's correct, but
   adds Kafka Connect-style infrastructure, and turns row changes into events rather than
   business events.
4. **Transactional outbox + relay.** The service inserts an `OutboxEvent` row in the same
   transaction as the change. A separate process copies committed rows to Redis.

## Decision

A transactional outbox:
- `record_event()` refuses to run outside a transaction;
- a dedicated `relay` process claims batches with `FOR UPDATE SKIP LOCKED`;
- it `XADD`s them in order, stops at the first Redis error, and stamps `published_at`.

**Events are recorded only in the service layer, never in views or model signals:**
- **Not views.** A view would miss every caller that isn't an HTTP request: the webhook-driven
  `pay()`, the Celery sweeper, management commands, and the replay.
- **Not model signals.** They fire on row saves rather than business meaning; they don't fire
  for queryset updates (the `F()` stock decrement is one); and they hide side effects inside
  `save()`.
- **The service** holds both the meaning and the transaction. So it's the one place where "the
  event exists if and only if the change does" can be guaranteed.

Why a long-running relay process rather than a Celery beat task polling the outbox:
- **Latency:** publishing is sub-second, instead of waiting for beat's interval.
- **Simplicity:** one simple loop with backoff, instead of task runs that could overlap.
- **Scaling:** it scales by adding relays, which `SKIP LOCKED` already allows.

## Consequences

- **Exactly one outbox row per committed change.** A rollback leaves no row. Delivery from there
  on is still at least once (next point).
- **At-least-once delivery.** A crash between `XADD` and the relay's commit re-sends the batch.
  Consumers must dedupe ([0003](0003-state-based-idempotent-consumers.md)).
- **Latency.** The relay polls every 0.5 s when idle. So an event should reach Redis within
  roughly half a second of its commit, plus the batch time. That figure is derived from the poll
  interval, not measured. The measured end-to-end figures include the relay hop
  ([replay.md](../flows/replay.md#throughput)).
- **The outbox grows.** A partial index on unpublished rows keeps the relay's query fast, and
  beat purges published rows after 7 days.
- **Safe to scale.** Running more relays is safe (`SKIP LOCKED`), at the cost of ordering
  across relays.
- **A hung Redis can't hold locks.** The Redis client has connect and socket timeouts, so a hung
  Redis can't keep the relay's row locks open.

## Links

- [docs/flows/event-pipeline.md](../flows/event-pipeline.md)
- [backend/apps/events/outbox.py](../../backend/apps/events/outbox.py), [backend/apps/events/relay.py](../../backend/apps/events/relay.py), [backend/apps/orders/events.py](../../backend/apps/orders/events.py)
- Tests: `test_rollback_after_the_write_leaves_no_event`, `test_record_event_refuses_to_run_outside_a_transaction`, `test_two_relays_never_publish_the_same_row`, `test_a_hung_redis_times_out_instead_of_holding_the_locks`
