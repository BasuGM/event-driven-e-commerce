# 0011. Analytics projections: DELETE + INSERT under advisory locks

- **Status:** Accepted
- **Date:** 2026-11-09 (commit `4c3cd2f`, Step 7b)

## Context

The staff dashboard reports per-day sales, categories, states and delivery performance, for
each order source. Aggregating orders at request time would get slower as history grows. The
projections must stay current as order events arrive, under the pipeline's rules:
- delivery is at least once;
- there's no ordering guarantee;
- handlers must be state-based ([0003](0003-state-based-idempotent-consumers.md)).

## Options considered

1. **Aggregate on request.** Simple and always current, but the cost grows with history, on
   every dashboard view.
2. **Incremental counters** (`+1` per event). Deltas, which break with duplicates and reordering.
3. **Materialized views, refreshed periodically.** Stale between refreshes, and a full refresh
   recomputes everything.
4. **Upsert rows per (day, key) from a recompute.** A category or state that disappears from a
   day would leave a stale row behind.
5. **DELETE + INSERT the affected (day, source) rows from the orders, in one transaction.**

## Decision

Option 5, `recompute_days(days, source)`:
- **Locks.** It takes `pg_advisory_xact_lock(hashtext('analytics:<source>:<day>'))` for each day,
  **in ascending day order**.
- **Rebuild.** It deletes those days' rows in all four tables, then re-inserts them with
  set-based `INSERT … SELECT`.
- **Unique keys.** Each projection has a unique key, with `NULLS NOT DISTINCT` for "no category".
- **Who calls it.** The `analytics` consumer recomputes the order's purchase day on every order
  event. `backfill_analytics` rebuilds everything, in chunks of 31 days.

Why the advisory lock: two recomputes of the same day (the consumer, the backfill, two consumer
instances) would otherwise both delete nothing and both insert. The unique keys turn that into a
loud error instead of double counting. The lock makes them queue instead, and the ascending
order prevents deadlocks between multi-day recomputes.

## Consequences

- **Correct under duplicates, reordering and concurrency**
  (`test_concurrent_recomputes_of_the_same_day_queue_instead_of_double_inserting`), and the
  backfill equals a direct computation.
- **Cheap reads:** the dashboard sums small tables.
- **Recomputing a whole day per event is the pipeline's bottleneck.** Measured on 2026-11-09:
  ~64 events/s, p95 latency 74.67 s during a `--speed 0` replay. The planned fix is to coalesce
  each read batch to its distinct (day, source) pairs.
- **Days are São Paulo purchase days.** So "late deliveries" are attributed to the purchase
  week, not the delivery week.

## Links

- [docs/flows/analytics.md](../flows/analytics.md)
- [backend/apps/analytics/projections.py](../../backend/apps/analytics/projections.py), [backend/apps/events/consumers/analytics.py](../../backend/apps/events/consumers/analytics.py)
