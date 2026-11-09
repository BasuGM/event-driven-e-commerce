# 0003. State-based, idempotent consumers

- **Status:** Accepted
- **Date:** 2026-10-23 (commit `b633ef4`, Step 4)

## Context

The pipeline delivers **at least once** ([0002](0002-transactional-outbox-and-relay.md)). It also
doesn't guarantee **order**:
- entries are reclaimed after a failure and processed after newer ones;
- several relays interleave their batches.

So a consumer can see the same event twice, or events in the wrong order. A consumer that adds
"+3 sold" per `OrderPlaced` would double-count on a redelivery, and go wrong when a cancel
arrives before its placement.

## Options considered

1. **Deltas, with exactly-once delivery attempted in the transport.** Not available with Redis
   Streams, and fragile even where it exists.
2. **Deltas plus a dedupe table.** This fixes duplicates but not ordering. A delta applied out of
   order can still produce a wrong intermediate state, or a wrong final one when a delta depends
   on the current value.
3. **Dedupe table plus state-based handlers.** Record `(consumer, event_id)` in the same
   transaction as the handler's side effects. The handler **recomputes** the affected state from
   the database instead of applying a change.

## Decision

Option 3:
- Each consumer inserts `ProcessedEvent(consumer, event_id) … ON CONFLICT DO NOTHING` in the
  transaction that runs its handler. A conflict means "already applied", and the handler is
  skipped.
- `XACK` happens only after the commit.
- Handlers recompute:
  - `product_stats` re-runs the sales and `min_price` SQL for the order's products;
  - `analytics` rebuilds the order's purchase day;
  - `order_live` only signals, and the stream re-reads the database.

## Consequences

- **Effectively-once side effects in the database.** A crash after commit but before `XACK`
  redelivers, and the dedupe row stops the second run.
- **Results don't depend on arrival order.** Replaying the whole stream is safe: a new consumer
  group starts from id 0.
- **Recomputing costs more than an increment.** The analytics consumer re-aggregates a whole day
  per event (~64 events/s measured on 2026-11-09), and is the pipeline's bottleneck. The planned
  fix is coalescing per batch.
- **Side effects outside the database need their own idempotency.**
  - Emails: a unique `(event_id, kind)` row plus a deterministic `Message-ID`, and one remaining
    gap where an email can be sent twice.
  - Cache revalidation: revalidating twice is harmless.
  - DLQ retries: a unique `DeadLetterRetry` row.
- **`ProcessedEvent` grows.** It's kept for 90 days, which is far longer than any redelivery
  window.

## Links

- [docs/flows/event-pipeline.md](../flows/event-pipeline.md), [docs/flows/notifications.md](../flows/notifications.md)
- [backend/apps/events/consumer.py](../../backend/apps/events/consumer.py), [backend/apps/events/consumers/](../../backend/apps/events/consumers/)
- Tests: `test_the_same_event_twice_is_applied_once`, `test_crash_after_commit_before_ack_does_not_apply_twice`, `test_a_poison_event_is_dead_lettered_and_the_group_keeps_moving`
