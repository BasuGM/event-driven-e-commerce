# Analytics

`/staff/analytics` is a staff-only dashboard. It shows:
- orders, revenue (GMV), average order value and the cancellation rate;
- revenue over time, by category and by state;
- weekly delivery performance, grouped by **purchase** week.

Every figure is reported **per source**:
- `olist`: the imported history;
- `app`: orders placed in this app;
- `replay`: replayed copies.

The dashboard never aggregates orders at request time. It reads small **projection tables**,
which an event consumer keeps current.

## Projections

These are in [backend/apps/analytics/models.py](../../backend/apps/analytics/models.py). Each
table has one row per key, and a unique constraint on that key:

| Table | Key | Columns |
|---|---|---|
| `DailySales` | (day, source) | `orders`, `canceled_orders`, `paid_orders`, `gmv`, `items` |
| `CategorySales` | (day, source, category) (`NULLS NOT DISTINCT`, so "no category" is one row) | `revenue`, `units` |
| `StateSales` | (day, source, state) | `orders`, `gmv` |
| `DeliveryStats` | (day, source) | `delivered`, `delivery_seconds_total`, `late` |

**"Day" is the purchase date in São Paulo time** (`ANALYTICS_TIMEZONE = America/Sao_Paulo`), for
every table, delivery stats included. Olist's timestamps are Brazilian local time, so a
São Paulo day matches what the business would call "orders on the 24th". An order at 23:30 in
São Paulo (02:30 UTC the next day) counts on the São Paulo day
(`test_days_are_sao_paulo_purchase_days`).

### Definitions

Recorded in [projections.py](../../backend/apps/analytics/projections.py):

- **`orders`** counts every placed order. **`canceled_orders`** counts the canceled and
  unavailable ones. The cancellation rate is canceled / orders.
- **Revenue counts only orders that reached approved or later:** approved, invoiced,
  processing, shipped and delivered. A `created` (unpaid) or canceled order adds to `orders`, but
  not to revenue (`test_created_and_canceled_orders_count_as_orders_but_not_revenue`).
  - **GMV** is items + freight of those paid orders.
  - **AOV** is GMV / paid orders, as an exact `Decimal` rounded half-up to the cent.
- **Category revenue** is item prices only, because freight isn't per category.
- **State** is the shipping state if set, else the customer's state (Olist orders have no
  shipping address).
- **Delivery:**
  - delivery time is purchase → delivered, in seconds;
  - **late** means delivered (local date) after the estimated delivery date;
  - the average delivery days and the late share are computed when the dashboard is read.
  - **Delivery stats are keyed by purchase day**, like every projection. So the weekly delivery
    chart groups orders by the week they were **bought**, not the week they were delivered. An
    order bought on 28 Nov and delivered on 15 Dec counts in the week of 28 Nov.

## Keeping them current

### State-based recompute

`recompute_days(days, source)` rebuilds the rows for a set of (day, source) pairs **in one
transaction**:

1. **Take a lock per day.** It takes `pg_advisory_xact_lock(hashtext('analytics:<source>:<day>'))`
   for each day, **in ascending day order**.
2. **`DELETE`** the four tables' rows for those days and that source.
3. **`INSERT … SELECT`** them again from the orders: set-based SQL with no Python loops.

**It never applies increments.** It recomputes from the orders, like every consumer in the
pipeline ([event-pipeline.md](event-pipeline.md#no-ordering-guarantee-handlers-are-state-based)).
A duplicate or out-of-order event therefore produces the same rows.

**Why the advisory lock.** Two recomputes of the same day can run at once: the consumer, the
backfill, or two consumer instances. Without the lock, both would `DELETE` (nothing to delete
yet), and both would `INSERT`:
- the unique constraints would reject the second insert;
- without the constraints, the day would be double-counted.

With the lock, the second recompute waits until the first commits, then rebuilds the same rows.
Taking the locks in ascending day order means two multi-day recomputes can't deadlock
(`test_concurrent_recomputes_of_the_same_day_queue_instead_of_double_inserting`).

### Who triggers it

- **The `analytics` consumer**
  ([consumers/analytics.py](../../backend/apps/events/consumers/analytics.py)) handles every
  order event. It looks up the order's source and purchase time, and recomputes that one
  (day, source). If the order no longer exists, for example after a replay reset that already
  rebuilt its days, it does nothing.
- **`backfill_analytics`** (`make analytics-backfill`, also run by `make seed`) rebuilds every day
  that has orders or stale rows, per source, in chunks of 31 days per transaction. The importer
  emits no events, so this is how imported orders reach the projections
  (`test_backfill_matches_a_direct_computation`).

## API and dashboard

`GET /api/staff/analytics/?source=&date_from=&date_to=` is staff-only (404 otherwise), in
[queries.py](../../backend/apps/analytics/queries.py).

- **`source`** is `all`, `olist`, `app` or `replay`; the API's default is `all`. With no dates
  given, it covers all data for that source.
- **The response** contains:
  - the KPIs;
  - the daily series;
  - categories: the top 10, plus "Other (n categories)" for the rest;
  - states;
  - delivery by week. Weeks group delivery stats by **purchase** week (`TruncWeek` on the purchase
    day), not by the week the order was delivered;
  - the data's first and last day, which date presets are relative to.

The page is `/staff/analytics`, with components in
[components/analytics/](../../frontend/src/components/analytics/). Its URL is its state
([lib/analytics-params.ts](../../frontend/src/lib/analytics-params.ts)).

| Choice | Why |
|---|---|
| Default source `olist` (`DEFAULT_SOURCE`, left out of the URL; "All" is `?source=all`) | A day of app test orders would otherwise flatten the first view of two years of history |
| Date presets relative to the **newest data** ("Last 30/90 days of data") | Olist data ends in 2018; "last 30 days" relative to today would be empty |
| Revenue over time on a time-scaled numeric axis, with the line broken after gaps of more than 31 days (`GAP_DAYS`) | 2018 → 2026 shows as a gap instead of a misleading straight line |
| Category: top 10 bars + a note for the rest; State: top 10 horizontal bars + "Other (n)", every bar labelled | Readable at a glance, with nothing hidden |
| Series colours from `--chart-1..5`, no animation | Real colours in both themes, ≥ 3:1 against the background |

**Staff only.** GMV, cancellations and lateness are business data, not storefront content.

**Live, with a gentle poll.** The page calls `router.refresh()` every 10 s while the tab is
visible (`AutoRefresh`). It doesn't use SSE. Projections change in bursts (hundreds of times a
second during a replay), so a stream would need server-side coalescing, and a dashboard isn't
latency-critical.

## Performance

The consumer recomputes a whole purchase day **for every event**. That's simple and always
correct, but it's the slowest consumer in the pipeline.

**Measured 2026-11-09** during a `--speed 0` replay of 2,000 orders (9,896 events):
- **Throughput:** the analytics consumer processed about 64 events/s, while the replay wrote
  about 90.
- **Backlog:** it peaked at 3,979 entries (sampled every 2 s).
- **Latency:** from an event's outbox write to the analytics commit, p50 was 31.65 s, p95 74.67 s
  and max 76.1 s.
- **Drain:** the backlog was empty about 45–50 s after the replay finished.

The other consumers kept p95 under 1.1 s. Details and definitions are in
[replay.md](replay.md#throughput).

The planned fix, when needed: recompute each distinct (day, source) **once per read batch**,
coalescing the batch's events, instead of once per event. Until then, replays run at `--speed`
≥ 1 (the default is 10), which spreads the events out enough. This is recorded in CLAUDE.md's
known issues; it hasn't been measured separately.

## Sources

- [backend/apps/analytics/](../../backend/apps/analytics/) (models, projections, queries, serializers, views, management/commands/backfill_analytics.py)
- [backend/apps/events/consumers/analytics.py](../../backend/apps/events/consumers/analytics.py)
- [frontend/src/app/staff/analytics/](../../frontend/src/app/staff/analytics/), [frontend/src/components/analytics/](../../frontend/src/components/analytics/), [frontend/src/lib/analytics-params.ts](../../frontend/src/lib/analytics-params.ts)
- Tests: [test_analytics.py](../../backend/tests/test_analytics.py), [charts.test.ts](../../frontend/src/components/analytics/charts.test.ts), [auto-refresh.test.tsx](../../frontend/src/components/analytics/auto-refresh.test.tsx), [analytics-params.test.ts](../../frontend/src/lib/analytics-params.test.ts)
