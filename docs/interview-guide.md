# Interview guide

How to talk about this project in an interview: a 60-second pitch, a 5-minute architecture
walkthrough, then one section per area with the decision, its trade-off, what breaks at 100×,
what I'd change, and the questions an interviewer is likely to ask. It ends with the bugs I found
and how.

Every claim here comes from the other docs and the code; follow the links for the detail.
**"At 100×" is reasoned, not measured.** The only measured figures in this project are the
dated ones in [flows/replay.md](flows/replay.md#throughput) and [testing.md](testing.md).

## The 60-second pitch

> It's an event-driven e-commerce platform in Django and Next.js, seeded with the real Olist
> dataset of about 100,000 Brazilian orders.
>
> Checkout reserves stock under row locks taken in a fixed order, so two buyers can't get the last
> unit, and an idempotency key stops a retry from placing two orders. Payments come from a
> Stripe-like fake provider with signed, late, duplicated and out-of-order webhooks. Every state
> change writes an event to a transactional outbox in the same transaction. A relay publishes it
> to Redis Streams, where six idempotent, state-based consumers update stats, invalidate caches,
> send emails, push live updates over Server-Sent Events, log events and maintain analytics.
>
> A replay re-enacts historical orders through the real services; its analytics matched the
> imported totals to the cent. There are over 350 backend tests, including real concurrent
> transactions, and Playwright runs on an isolated, freshly seeded stack.

## The 5-minute architecture walkthrough

A script to talk through with [architecture.md](architecture.md)'s diagrams on screen.

**1. Shape (30 s).** "One Django codebase, run as several processes by Docker Compose: the WSGI
API, an ASGI service that only serves the live order stream, a Celery worker and beat, an event
relay and a consumers process. Postgres is the only system of record. Redis is the Celery broker,
the event transport and the live-update Pub/Sub. Next.js renders the pages and proxies `/api/*`
to Django, so the browser sees one origin."

**2. Data (30 s).** "Olist has no product names, prices or stock, so the importer generates names
deterministically from each product's ID and derives offers, one per seller and product, priced
at the exact median of what that seller actually charged. Imports are idempotent upserts on
Olist's own IDs." ([flows/olist-import.md](flows/olist-import.md))

**3. The write path (60 s).** "Every change goes through a service function with one shape: lock
the rows, check the rule, transition the state, record an event, commit. Checkout locks the cart,
then the offers in ascending id order, checks every line, decrements stock in SQL with a
`CHECK (stock >= 0)` backstop, and creates a reservation that expires in 15 minutes. Status
changes only go through an explicit state machine that writes a history row. Because the event is
just another row in the same transaction, it exists if and only if the change committed."
([flows/cart-checkout-stock.md](flows/cart-checkout-stock.md),
[data-model.md](data-model.md#order-state-machine))

**4. Payments (45 s).** "The customer pays on the provider's hosted page; the result arrives as a
signed webhook. I verify the HMAC over the raw bytes, dedupe on the provider's event id, lock the
order, and decide everything from the event's own timestamp, never its arrival order. A payment
for an order that can't take it never revives the order: it's flagged for refund, and the
customer gets an email." ([flows/payments.md](flows/payments.md))

**5. The event pipeline (60 s).** "A relay claims unpublished outbox rows with
`FOR UPDATE SKIP LOCKED` and adds them to Redis Streams. Delivery is at least once and unordered,
so each consumer records `(consumer, event_id)` in the same transaction as its side effects, acks
only after commit, and recomputes state from the database instead of applying deltas. Failing
entries are retried, then dead-lettered, and staff can retry them from a health page."
([flows/event-pipeline.md](flows/event-pipeline.md))

**6. What reads the events (45 s).** "`product_stats` recomputes sales counts and then records a
`ProductsChanged` event, which `cache_invalidation` turns into a Next.js cache revalidation. So the
cache is dropped only after the new numbers are committed. `notifications` writes an email row
that Celery sends after commit. `order_live` publishes a signal; the SSE stream re-reads the order
from the database and pushes it. `event_log` feeds the staff explorer, and `analytics` rebuilds
per-day projections."

**7. Proving it (30 s).** "A replay re-enacts a date range of history as copies through the real
services. 2,000 orders produced 9,896 events; the analytics for the replay matched the imported
totals exactly, and it showed me the bottleneck: the analytics consumer, at about 64 events/s."
([flows/replay.md](flows/replay.md))

**Close with a limitation (15 s).** "What I'd fix next: coalesce the analytics recompute per batch,
add CI, and build refunds, which today are only flagged."
([limitations-and-roadmap.md](limitations-and-roadmap.md))

## How each section is laid out

- **Key decision:** what I chose.
- **Trade-off:** what it costs.
- **At 100×:** where it would break first under 100× the traffic or data. Reasoned from the code,
  not measured.
- **What I'd do differently:** with hindsight, or at a larger scale.
- **Likely questions,** with short first-person answers.

---

## Data import

Docs: [flows/olist-import.md](flows/olist-import.md).

- **Key decision.** The importer writes every table with `bulk_create(update_conflicts=True)`
  (`INSERT … ON CONFLICT (natural key) DO UPDATE`) on Olist's own IDs, generates product text
  deterministically (sha256-seeded), derives offers and stats with set-based SQL, and emits **no
  events**.
- **Trade-off.** Because the importer bypasses the order flow, everything derived from it must be
  rebuilt in bulk (`make backfill-sales`, `make analytics-backfill`) rather than by consumers.
  Generated names are pinned by tests: changing a word list renames products and changes their
  URLs, so it's treated like a data migration.
- **At 100×.** The full dataset is 99,441 orders; 100× of that is about 10 million. `_read()`
  loads each CSV into a Python list, and the importer builds dictionaries from every external id
  to its primary key, so memory grows linearly with the data. Each table is written in one
  transaction, which becomes a very long transaction. The set-based stats SQL would still be a
  handful of statements, just slower ones.
- **What I'd do differently.** Stream the CSVs with `COPY` into staging tables and resolve the
  foreign keys in SQL, committing per chunk. The upsert keys and the validation rules would stay
  the same.

**Likely questions**

- **How is the import safe to run twice?** "Every table upserts on Olist's natural key, so a
  second run updates rows in place. Postgres refuses an `ON CONFLICT DO UPDATE` that touches the
  same row twice in one statement, so I drop in-file duplicates first and report them as skipped.
  Every stats statement only updates rows whose value changes (`IS DISTINCT FROM`), so a re-run on
  unchanged data writes nothing: `test_reimport_changes_nothing`."
- **Doesn't a re-seed reset stock?** "No. Stock is synthetic and set only when an offer is first
  created; the conflict clause updates price and freight, never stock. After that, stock belongs to
  the order flow (`test_reseed_never_overwrites_live_stock`)."
- **How do you handle bad rows?** "Each row is validated in Python; a bad one is skipped and
  counted by reason, never fatal. Rows kept with a caveat, like an untranslated category, are
  reported as notes. The test fixtures are tiny CSVs with each problem in them, and the counts are
  asserted."
- **Why compute the median yourself instead of `percentile_cont`?** "`percentile_cont` goes
  through `float8`. I compute the median in `numeric` as the mean of the two middle values, so
  prices are exact ([ADR 0010](adr/0010-money-as-decimal-strings.md))."
- **What about time zones?** "Olist timestamps are Brazilian local time without an offset. I parse
  them as America/Sao_Paulo and store UTC. Analytics then groups by São Paulo day, because that's
  what the business would call 'orders on the 24th'."

## Catalog, search and caching

Docs: [flows/catalog-and-search.md](flows/catalog-and-search.md),
[ADR 0008](adr/0008-postgres-full-text-search.md), [ADR 0017](adr/0017-cache-invalidation-by-consumer.md).

- **Key decision.** Listings filter and sort only on denormalised, indexed product columns
  (`min_price`, `rating_avg`, `sales_count`, `search_vector`). Search is Postgres full-text with
  prefix matching. Only the product detail fetch is cached (`"use cache"`, tag `product:<slug>`);
  the `product_stats → ProductsChanged → cache_invalidation` chain revalidates it after commit,
  with `revalidate: 300` as a backstop. Listings are never cached.
- **Trade-off.** Every writer must keep the denormalised columns right: `min_price` is refreshed on
  commit, `sales_count` is eventually consistent (seconds). Search has no typo tolerance. A product
  page can be stale for the seconds the consumer chain takes.
- **At 100×.**
  - **Hot products lose their cache.** `product_stats` records `ProductsChanged` for every
    non-replay order event that has lines, so every placement, payment or cancel of a product
    revalidates its page. At 100× the busiest products, the ones that benefit most from caching,
    would be revalidated almost continuously.
  - **Every listing view is a database query,** because listings are dynamic. Indexed columns keep
    each one cheap, but nothing absorbs a traffic spike.
  - **Search.** 100× the 1,732 products of the small seed is still a modest catalog for a GIN
    index; very short prefixes would match broadly and cost more.
- **What I'd do differently.** Record `ProductsChanged` only when a product's `sales_count` or
  `min_price` actually changed, compared in the recompute's own transaction
  ([roadmap](limitations-and-roadmap.md#roadmap-candidates)). The next step would be to coalesce
  revalidations per product.

**Likely questions**

- **Why Postgres full-text search, not Elasticsearch or Meilisearch?** "The catalog is small, and a
  GIN-indexed `tsvector` handles it. It adds no service and no index to keep in sync, and search
  and filters are one SQL query, so counts and pagination are exact and consistent with prices
  and stock. Meilisearch is the deferred upgrade, for typo tolerance and facets; the API contract
  wouldn't change."
- **How does the in-stock filter work?** "`min_price` is the cheapest offer *with stock*, so it's
  null exactly when nothing is in stock. It's refreshed synchronously right after every order
  commit, so the filter is correct on the next request. That's why there's no inventory consumer
  ([ADR 0009](adr/0009-no-inventory-consumer.md))."
- **Why invalidate through a consumer, and not right after the order commits?** "`sales_count` is
  updated asynchronously by a consumer, so revalidating from the request could run before the new
  value exists, and it would put HTTP to the frontend inside the order flow. Recording
  `ProductsChanged` in the same transaction as the recompute guarantees revalidation follows the
  new values."
- **What if the frontend is down?** "The consumer's call fails, its transaction rolls back and the
  entry stays pending. It's retried, dead-lettered after 5 attempts and retryable by staff. Until
  then the 5-minute `revalidate` bounds the staleness."
- **Why does every ordering end with `id`?** "Sort keys tie a lot, for example `sales_count = 0`.
  Without a tiebreaker, pages could overlap or skip products."

## Auth and sessions

Docs: [flows/auth-and-sessions.md](flows/auth-and-sessions.md),
[ADR 0004](adr/0004-sessions-behind-the-next-proxy.md).

- **Key decision.** Django sessions, not JWT. The browser only talks to the Next origin, which
  rewrites `/api/*` to Django, so the `sessionid` and `csrftoken` cookies are first-party. Server
  Components forward the visitor's cookies. 401 means not logged in, 403 is a CSRF or permission
  failure, and another user's order is a 404.
- **Trade-off.** Every browser API call takes an extra hop through Next, the SSE stream needed
  special headers to get through that proxy unbuffered, and any Server Component that reads
  cookies is dynamic and can't be cached.
- **At 100×.**
  - **Sessions live in Postgres:** no session engine is configured, so Django's default database
    backend reads the session table on every authenticated request.
  - **Next becomes a proxy tier** that has to scale with the API, not only with page renders.
  - **Login and register have no rate limit** (on the "Before deploying" list), so credential
    stuffing would scale with the traffic.
- **What I'd do differently.** Put a reverse proxy (nginx or similar) in front from the start,
  routing `/api/*` to Django, the stream path to the ASGI service, and the rest to Next. It keeps
  the same-origin cookies without making Next the proxy, and would have avoided the SSE
  compression problem. Sessions in a cache-backed store at scale.

**Likely questions**

- **Why not JWT?** "Logout and revocation are immediate (delete the session), no token is readable
  by page scripts, there's no refresh-token flow to build, and the same-origin proxy makes the
  cookies first-party, so there's no CORS or third-party cookie problem."
- **Why do you need `CSRF_TRUSTED_ORIGINS`?** "Behind the proxy Django sees `Host: backend:8000`
  but the browser's `Origin`, so the origin check would fail. I list the browser origins
  explicitly. I don't trust `X-Forwarded-Host`, because the backend port is published and anyone
  reaching it directly could set that header."
- **Why is login explicitly `csrf_protect`ed?** "DRF's `SessionAuthentication` only enforces CSRF
  for authenticated requests, and login is anonymous. Without it, another site could log a
  visitor into the attacker's account."
- **Why re-read the CSRF token on every request?** "Django rotates it at login. A token cached
  before login would be stale afterwards."
- **Why a 404 for someone else's order?** "A 403 would confirm the order exists. Staff endpoints
  go further: anonymous users and customers both get 404 ([ADR 0013](adr/0013-staff-pages-404.md))."

## Checkout and concurrency

Docs: [flows/cart-checkout-stock.md](flows/cart-checkout-stock.md),
[ADR 0015](adr/0015-stock-reserved-at-checkout-under-row-locks.md),
[ADR 0016](adr/0016-idempotency-key-for-checkout.md).

- **Key decision.** Stock is taken at checkout, not at add-to-cart or payment, and held by a
  `Reservation` for `RESERVATION_TTL_MINUTES` (15). Checkout uses pessimistic row locks in one
  project-wide order (Cart → Order → PaymentIntent → Offers by ascending id; Products after commit),
  an `F()` decrement with `CHECK (stock >= 0)`, and conditional `UPDATE … WHERE status='active'`
  releases. An `Idempotency-Key` row is written in the same transaction as the order.
- **Trade-off.** Concurrent buyers of one offer wait on its row lock. Unpaid orders hold stock for
  up to 15 minutes plus a sweeper minute. The lock order is a rule that reviewers must enforce,
  not something the database checks.
- **At 100×.**
  - **A flash sale on one offer serialises.** The offer stays locked for the rest of the checkout
    transaction: creating the order, one item row per unit, the reservations, the history row, the
    outbox event and the idempotency row. Throughput on that offer is bounded by one transaction
    at a time, and waiting checkouts hold database connections.
  - **Expired holds come back in batches.** The sweeper runs every 60 s, one transaction per
    order, 100 per batch, looping until none are left; at 100× it just loops longer.
- **What I'd do differently.** For a hot single-line purchase, a conditional
  `UPDATE … WHERE stock >= qty` without the up-front lock would shorten the critical section; the
  multi-line, report-every-short-line case is why I didn't start there. I'd also make the lock
  order checkable (one helper that takes locks in order) instead of a convention.

**Likely questions**

- **How do you prevent overselling?** "Checkout locks the offers with `select_for_update()` in
  ascending id order, checks every line, then decrements in SQL. `CHECK (stock >= 0)` is the
  database backstop. `test_two_buyers_one_last_unit` runs two real concurrent checkouts with a
  barrier: one wins, the other gets `out_of_stock`, stock ends at 0."
- **Why pessimistic locks rather than optimistic or `SERIALIZABLE`?** "A cart has several lines
  that must succeed or fail together, and the error lists every short line. Locking all offers
  first gives a stable view to check them all before any decrement. A per-line conditional update
  can't report every short line without extra reads, and `SERIALIZABLE` would push retry loops
  into every write path. Contention is on a few hot rows, where a short wait beats fail-and-retry."
- **How do you avoid deadlocks?** "One global lock order. Every path takes locks in it, and
  `test_opposite_cart_order_does_not_deadlock` checks out the same two offers from two carts in
  opposite orders at the same instant."
- **What if the client retries checkout after a timeout?** "It sends the same `Idempotency-Key`. The
  key row is inserted in the same transaction as the order and stores the response, so a retry
  replays it. A concurrent duplicate waits on the unique index, then replays. A failure rolls the
  key back, so a retry after 'out of stock' runs fresh."
- **How is stock returned exactly once?** "Releases are a conditional
  `UPDATE … WHERE status = 'active'`, and stock comes back only if that changed a row. If the
  sweeper and a late cancel race, only one can flip it. Both also lock the order and re-check its
  status."

## Payments and webhooks

Docs: [flows/payments.md](flows/payments.md), [ADR 0005](adr/0005-fake-payment-provider.md),
[ADR 0006](adr/0006-payment-intent-vs-ledger.md).

- **Key decision.** A Stripe-shaped fake provider behind a `PaymentGateway` protocol. Two models:
  `PaymentIntent` for the provider lifecycle, `Payment` for the settled ledger. The webhook is a
  plain Django view that verifies an HMAC over the raw bytes, dedupes on `ProviderEvent`, locks
  order then intent, and decides from the event's own `created` time. A success for an order that
  can't take it is flagged `needs_refund` and never revives the order.
- **Trade-off.** No real provider's quirks are exercised, there's no refund logic (only the flag
  and a `PaymentRefundDue` event), and a decline cancels the order, so a mistyped card means
  checking out again.
- **At 100×.**
  - **Refunds are manual,** so at 100× the flagged intents become an operations queue.
  - **Contention is per order:** the webhook locks one order and its intent, so it scales out
    with API processes.
  - **Retries pile up.** The worker retries each failed delivery up to 6 times with backoff, so a
    backend outage turns into a burst of signed retries once it recovers.
- **What I'd do differently.** Build the refund call on the gateway and a refund state on the
  intent, and let a declined intent be retried within the hold, as Stripe does.

**Likely questions**

- **Why a fake provider instead of Stripe test mode?** "Stripe is invite-only in India and needs a
  registered business, and the data is in BRL, which an Indian gateway wouldn't handle. The fake
  also makes late, duplicate and out-of-order webhooks deterministic, in tests and on demand. A
  real provider is one more `PaymentGateway` class."
- **How do you verify a webhook?** "`v1 = HMAC-SHA256(secret, "<t>." + raw_body)`, with the
  timestamp inside the signature and a 300 s tolerance against replays, compared with
  `hmac.compare_digest`, several `v1` values allowed for rotation. It's a plain Django view
  because DRF would hand me re-serialised data that no longer matches the bytes. JSON is parsed
  only after the signature checks out."
- **What happens with duplicate or out-of-order webhooks?** "`ProviderEvent` is unique on
  `(provider, provider_event_id)`; a duplicate returns 200 'duplicate'. Order is decided by the
  event's `created` time: a decline older than an applied success is `ignored_stale`, and a
  success paid in time is approved however late it arrives."
- **What if someone clicks Pay twice?** "The partial unique index `uniq_open_intent_per_order`
  allows one open intent per order, and the provider call uses the idempotency key
  `order:<id>:intent`, so both clicks reach the same provider payment. `create_payment` runs
  outside any transaction, because it may do network I/O."
- **What if processing fails halfway?** "The webhook runs in one transaction, including the
  `ProviderEvent` row. A crash rolls everything back, the endpoint returns 500, and the provider's
  retry starts from scratch.
  `test_a_webhook_that_fails_partway_rolls_back_and_applies_once_on_retry` crashes it after
  `pay()` has applied everything."

## Event pipeline

Docs: [flows/event-pipeline.md](flows/event-pipeline.md),
[ADR 0001](adr/0001-redis-streams-over-kafka.md), [ADR 0002](adr/0002-transactional-outbox-and-relay.md),
[ADR 0003](adr/0003-state-based-idempotent-consumers.md).

- **Key decision.** A transactional outbox written only by services, a dedicated relay
  (`SKIP LOCKED` batches of 100, stops at the first Redis error), Redis Streams with one consumer
  group per consumer, a `ProcessedEvent` dedupe row in the handler's transaction, ack after commit,
  state-based handlers, reclaim after 60 s idle, and a dead-letter stream after 5 deliveries.
- **Trade-off.** Delivery is at least once and unordered, so every handler must be idempotent and
  recompute rather than apply deltas. Redis persists with `appendfsync everysec`, so a hard crash
  can lose about a second of published entries, and streams are trimmed to about 100,000 entries.
  One Redis serves Celery, streams and Pub/Sub.
- **At 100×.**
  - **The relay is one round trip per event.** It sends one `XADD` per row, without pipelining.
  - **Events are scattered across streams only by aggregate,** with no partitioning. Each consumer
    is one thread, so to go faster you add consumer processes to the same group, which the design
    allows.
  - **Bookkeeping tables become the biggest in the database:** the outbox (7 days),
    `ProcessedEvent` (up to one row per consumer per event, 90 days) and `EventLog` (90 days).
    Purging them is a large `DELETE`.
  - **A lagging group could fall off the end of a stream:** past about 100,000 entries, it would
    miss events.
  - **The analytics consumer is already the bottleneck** (below).
- **What I'd do differently.** Pipeline the `XADD`s per batch, partition the outbox, `EventLog`
  and `ProcessedEvent` by time so retention is a partition drop, and give the event streams their
  own Redis, separate from the Celery broker.

**Likely questions**

- **Why an outbox, instead of publishing to Redis from the service?** "Postgres and Redis can't
  share a transaction. Publishing before commit can announce a change that rolls back; publishing
  after commit loses the event if the process dies in between. The outbox row commits or rolls
  back with the change."
- **Why not Django signals or the view?** "Views miss every non-HTTP caller: the webhook-driven
  `pay()`, the sweeper, the replay. Signals fire on row saves, not business meaning, don't fire for
  queryset updates like the `F()` stock decrement, and hide side effects. The service has both the
  meaning and the transaction."
- **Is it exactly once?** "Delivery is at least once. Each consumer inserts
  `ProcessedEvent(consumer, event_id)` in the same transaction as its side effects and acks after
  commit, so database side effects happen effectively once
  (`test_crash_after_commit_before_ack_does_not_apply_twice`). Side effects outside the database,
  like email, need their own idempotency."
- **What about ordering?** "There's none once entries are reclaimed or more than one relay runs.
  So handlers recompute from the database. Then the result doesn't depend on arrival order, and
  replaying the whole stream is safe."
- **Why Redis Streams and not Kafka?** "Redis was already in the stack, and Streams give me what I
  need: consumer groups, acks, a pending list, reclaim and replay. Kafka would add a cluster to
  run for no benefit at this scale. I'd move for many consuming teams, long retention, or
  throughput that needs partitions."

## Live order tracking

Docs: [flows/live-tracking.md](flows/live-tracking.md),
[ADR 0007](adr/0007-sse-signal-plus-snapshot.md).

- **Key decision.** Server-Sent Events from a separate ASGI `stream` service. The `order_live`
  consumer publishes a stateless Pub/Sub signal; the stream subscribes, then reads a snapshot from
  the database (the same serializer as the order API) and sends it as `id: <version>`. The page
  calls `router.refresh()` only when the version changes.
- **Trade-off.** One more service to deploy and route, with its own proxy checklist (buffering,
  timeouts). One Redis connection per open stream. Pub/Sub loses messages, which the design
  absorbs with snapshots, reconnects and a fallback poll.
- **At 100×.** Every open order page costs a Redis connection, a database read per signal, and a
  reconnect every 300 s, each with an ownership check and a fresh snapshot read. With 10,000 open
  pages that's 10,000 Redis connections, the size of Redis's default client limit, and about 33
  reconnects per second, each doing two reads, before any order changes. Each `router.refresh()`
  also re-renders the whole order page on the server.
- **What I'd do differently.** Start with the documented fix: one shared subscriber per `stream`
  process, pattern-subscribed to `live:order:*`, fanning out to per-connection queues.

**Likely questions**

- **Why SSE and not websockets?** "Updates only flow server to browser, and there are only a few
  per order. SSE is plain HTTP through the existing proxy, with automatic reconnect and
  `Last-Event-ID` built in. Websockets were out of scope, and would add a protocol upgrade for
  two-way traffic I don't need."
- **Why not put the new state in the message?** "Pub/Sub is fire-and-forget. If the message is only
  'this order changed' and the stream re-reads the database, a dropped signal is fixed by the
  next one, a reconnect or the poll, and a duplicate just costs a read."
- **Why a separate ASGI service?** "An open stream under WSGI holds a worker thread for minutes.
  Under ASGI it's a suspended coroutine. But the rest of the API is sync Django, which under ASGI
  would queue on one thread-sensitive executor, so only this path runs there, and the view refuses
  to stream under WSGI."
- **What did you have to do to get SSE through the Next proxy?** "Next's rewrite proxy compresses
  responses, which buffered the stream completely: 10 bytes arrived in 35 s. `Cache-Control:
  no-transform` stops that, `X-Accel-Buffering: no` covers nginx-style proxies, and a 15 s
  heartbeat stays under the proxy's 30 s idle timeout."
- **What if Redis is down?** "The stream falls back to re-reading the database every 5 s. If the
  browser's EventSource gives up entirely, the page refreshes every 15 s."

## Notifications

Docs: [flows/notifications.md](flows/notifications.md).

- **Key decision.** Decide, then send. The `notifications` consumer renders the email and inserts a
  pending `Notification` row (unique `(event_id, kind)`) in its transaction, then enqueues a Celery
  send on commit. The sender locks one row with `SKIP LOCKED`, sends, and marks it sent in the same
  transaction; failures back off from 30 s, doubling to 1 h, up to 8 attempts. Beat sweeps due rows
  every 30 s.
- **Trade-off.** One gap remains: a crash after SMTP accepted the message but before the commit
  sends it again, once, with the same `Message-ID`. The content is frozen when the consumer handles
  the event, so a retry hours later sends the original text.
- **At 100×.** Sending is one row per transaction; the limits are the SMTP provider's rate limits
  and the beat sweep scanning a bigger pending set. A provider outage at 100× leaves a large
  backlog that all retries on the same backoff schedule.
- **What I'd do differently.** Use a transactional email API that accepts an idempotency key, if
  the provider has one, which would close the duplicate gap, and spread retries with jitter.

**Likely questions**

- **Why not send the email inside the consumer?** "An email can't be rolled back, and SMTP can be
  slow or down. Sending inside the transaction would either send an email for a rolled-back change
  or hold the transaction open on the network."
- **How do you avoid duplicate emails?** "Two guards: `ProcessedEvent` dedupes redelivered events,
  and the unique `(event_id, kind)` catches the rest, for example after `ProcessedEvent` rows are
  purged."
- **What if the Celery broker is down at commit?** "The enqueue is `robust=True`, so it only logs.
  The row stays pending and the 30-second beat sweep sends it."
- **Can an email still be sent twice?** "Yes, in one case: the process dies after SMTP accepted the
  message, before the row is marked sent. SMTP can't take part in the transaction, so I make the
  `Message-ID` deterministic, and a client can spot the duplicate."
- **Do replays send emails?** "No. The consumer skips `order_source == "replay"`, or a replay would
  email thousands of historical orders to one dev account."

## Analytics

Docs: [flows/analytics.md](flows/analytics.md),
[ADR 0011](adr/0011-analytics-projections-recompute.md),
[ADR 0012](adr/0012-order-source-without-default.md).

- **Key decision.** Four projection tables keyed by (São Paulo purchase day, source[, category or
  state]). `recompute_days()` takes `pg_advisory_xact_lock` per day in ascending order, deletes the
  rows and re-inserts them from the orders. The `analytics` consumer does that for the order's day
  on every order event. Every metric is per source (`olist`, `app`, `replay`).
- **Trade-off.** Correct under duplicates, reordering and concurrency, but recomputing a whole day
  per event is the slowest consumer: about 64 events/s, with p95 latency of 74.67 s during a
  `--speed 0` replay (measured 2026-11-09).
- **At 100×.** Live traffic all lands on the same day, today. Every event recomputes today, and
  each recompute scans all of today's orders, so the work per day grows with the square of the
  day's orders. All those recomputes take the same advisory lock (`analytics:app:<today>`), so
  adding consumer instances wouldn't help: they would queue on the lock.
- **What I'd do differently.** Coalesce each read batch to its distinct (day, source) pairs (the
  planned fix). Beyond that, a per-order fact row, recomputed from that one order on each event and
  summed per day, keeps the state-based property without re-reading a whole day.

**Likely questions**

- **Why projections instead of aggregating on request?** "The cost of aggregating grows with
  history on every dashboard view. Projections make reads small sums."
- **Why not increment counters?** "Delivery is at least once and unordered; increments
  double-count on redelivery and go wrong out of order. Recomputing from the orders gives the same
  rows whatever the arrival order."
- **Why the advisory lock?** "Two recomputes of the same day, say the consumer and the backfill,
  would both delete nothing and both insert. The unique keys would turn that into an error; the
  lock makes them queue instead. Taking day locks in ascending order prevents deadlocks."
- **Why report per source?** "A day of app test orders would flatten two years of history, and
  replay copies must be comparable with the originals. `Order.source` has no default, so a new
  creation path can't forget to set it."
- **Why does the delivery chart group by purchase week?** "Every projection is keyed by purchase
  day, so the recompute for an order touches exactly one day. The cost is that a late delivery is
  attributed to the week the order was bought."

## Replay

Docs: [flows/replay.md](flows/replay.md), [ADR 0014](adr/0014-replay-through-real-services.md).

- **Key decision.** Re-enact imported history as **copies** (`source='replay'`, one per original)
  advanced through the real services on a simulated clock. Each step applies only while the copy
  is in its from-status, under the order lock. One running replay at a time, enforced by a partial
  unique index, with a heartbeat, takeover after 5 minutes of silence, and conditional updates so a
  taken-over runner stops itself.
- **Trade-off.** Olist has no invoiced, canceled or unavailable times, so they're synthesized. The
  order services gained replay-only paths (`cancel_paid`, `mark_unavailable`) that refuse other
  orders.
- **At 100×.** The 2,000-order replay applied 9,896 steps in 110.2 s, one transaction per step,
  about 90 events/s. The full dataset is about 50 times bigger; at the same rate that's well over
  an hour at `--speed 0`, and the analytics consumer, at about 64 events/s, would fall further
  behind for the whole run. And one copy per original means the replay can't multiply history to
  generate 100× load.
- **What I'd do differently.** Partition a run across several runners by order (the per-copy
  locks already make overlapping runners safe), and allow several copies per original for load
  tests.

**Likely questions**

- **Why copies rather than replaying the original orders?** "Replaying in place would destroy the
  imported history and couldn't be cleanly undone. Copies are separable by `source`, excluded from
  prices, sales counts and public counts, and `replay_reset` removes every trace."
- **Why go through the real services instead of writing events directly?** "Events without orders
  behind them would show nothing in consumers that read the database: analytics, the live page,
  the timelines. Real service calls also exercise the real transitions, history and outbox."
- **How do you stop two replays at once?** "A partial unique index `one_running_replay` on
  `status='running'`. Two processes starting together race on the insert, and one gets an
  `IntegrityError`. A read-then-insert check would let both through."
- **What if the replay process freezes and resumes later?** "If it's silent for 5 minutes another
  process marks it failed and takes over. Every runner write is `UPDATE … WHERE id = ? AND
  status = 'running'`, so the resumed runner sees zero rows updated and stops before its next step
  (`test_a_taken_over_run_stops_without_writing_further_steps`)."
- **How do you know the replay is correct?** "On 2026-11-09 the replay's analytics equalled the
  imported ones: 2,000 orders, 1,976 paid, GMV R$ 316.909,40. And in browser QA, all six KPIs for
  20–30 Nov 2017 matched."

## Staff tools

Docs: [flows/staff-tools.md](flows/staff-tools.md), [ADR 0013](adr/0013-staff-pages-404.md).

- **Key decision.** Staff endpoints and pages answer 404 to everyone else (`IsStaffOr404`), with a
  neutral page title and the staff header rendered only after the data check. The explorer reads
  `EventLog`, not the 7-day outbox. Health shows per-group pending and lag from Redis. Dead-letter
  retry re-adds the original entry with the same event id, once per DLQ entry.
- **Trade-off.** A streamed page's not-found still has HTTP status 200, so the title needs
  client-side care (a `MutationObserver`). The staff endpoints have no query-count tests yet.
- **At 100×.** `EventLog` holds 90 days of every event; its indexes cover type and time, and
  aggregate id and time, but a filter that matches neither scans a large table, and so does
  counting a broad filter for pagination. Dead letters are retried one at a time, which doesn't
  work for a burst of hundreds after an outage.
- **What I'd do differently.** A bulk retry by consumer and error, query-count tests for the staff
  endpoints, and time-partitioned `EventLog`.

**Likely questions**

- **Why 404 rather than 403 for non-staff?** "A 401 or 403 confirms the endpoint exists. For the
  pages, a streamed Next route has already sent 200 by the time `notFound()` runs, so the static
  shell can't reveal anything either: neutral title, no staff chrome until the check passes."
- **How does a dead-letter retry avoid double-applying?** "The retry re-adds the entry with the
  same event id, so every group on the stream sees it. Groups that already processed it find their
  `ProcessedEvent` row and just ack. The consumer that dead-lettered it has no row, because each
  attempt rolled back, so only it does the work. A unique `DeadLetterRetry` row makes a second click
  a no-op."
- **How do you find where an event is stuck?** "The order timeline lists each event with the
  consumers that *should* process it, computed from the registered consumers, and when each did
  from `ProcessedEvent`. A missing timestamp is exactly where it's stuck."
- **Why does the explorer read `EventLog` instead of the outbox?** "The outbox is a delivery
  buffer, purged after 7 days. `EventLog` is written once per event by its own consumer and kept
  for 90 days."

## Testing

Docs: [testing.md](testing.md).

- **Key decision.** Tests run against real Postgres and real Redis (DB 15, its own prefix), with
  Celery's in-memory broker. Concurrency is tested with real threads and connections released by a
  barrier. Query counts are pinned. The review rule: a fix is accepted only after its new test has
  been shown to fail without it; the guard is temporarily removed, the test must turn red, then
  the guard is restored. e2e runs on an isolated, freshly seeded compose project.
- **Trade-off.** e2e takes about 4–9 minutes, because a second full stack runs the Next dev server
  next to the dev one. There's no CI, and pages are covered only by the e2e smoke tests.
- **At 100×** (of contributors and tests rather than traffic). Without CI, tests run only when
  someone runs them. The e2e lock allows one run per machine. The backend tests share the compose
  Redis's DB 15 and one key prefix, cleared per test, so two backend runs on one machine would
  interfere.
- **What I'd do differently.** CI from the first commit, and e2e against a production build once
  the behaviour differences are understood.

**Likely questions**

- **How do you test race conditions?** "`run_concurrently()` starts functions in separate threads,
  each with its own connection, released by a `threading.Barrier`, in `transaction=True` tests so
  commits are real. That covers the last unit of stock, opposite lock orders, duplicate
  idempotency keys, concurrent sweepers, the sweeper racing a webhook, and two replay runners."
- **How do you know a test actually tests the fix?** "Mutation checks: I remove the guard, the test
  must go red, then I restore it. For example, without the webhook's `transaction.atomic()`, the
  partial-failure test fails."
- **Why real Postgres in tests and not SQLite?** "The code relies on `FOR UPDATE`, `SKIP LOCKED`,
  partial indexes, advisory locks and full-text search. None of that exists in SQLite."
- **How do you stop e2e from touching dev data?** "It runs a separate compose project whose
  database is on tmpfs, and before anything writes it checks, statically and then live on every
  Django service, that the database is `ecommerce_e2e` and the server is the e2e container. Any
  mismatch tears down and exits."
- **What isn't tested?** "The payment-after-expiry path is never made to fail partway, staff
  endpoints have no query-count tests, there's no CI and no visual or accessibility tests, and
  throughput figures come from one measured run ([testing.md](testing.md#known-gaps))."

---

## How I built it

> **Draft: rewrite this section in your own words before using it.**

I planned and reviewed the work with Claude (in chat) and implemented it with Claude Code. Every
change followed the same loop:
1. a written plan that I reviewed and approved (files, models, endpoints);
2. a test that fails without the fix, shown by removing the guard and watching it turn red;
3. browser QA before the commit.

The design decisions are mine, and I can defend each one; the [ADRs](adr/README.md) record the
options I weighed and why I chose as I did. The project's working rules are in `CLAUDE.md`: plan
before coding, vertical slices, tests with every change, explain non-obvious choices.

**Likely follow-ups**

- **How much did AI write?** "Most of the code was typed by Claude Code. What I did was decide and
  check: I chose the architecture and the trade-offs, reviewed every plan before any code was
  written, and accepted a change only with a failing-then-passing test and a browser check. When a
  plan or a fix was wrong I sent it back. Several of the bugs below were found by me checking docs
  against code."
- **Walk me through this file.** "Pick any service or consumer and I'll explain it line by line:
  why the locks are taken in that order, what happens if it crashes between two statements, which
  test covers it." Prepare for this one: re-read the core files before an interview, at least
  `apps/orders/services.py`, `apps/events/consumer.py`, `apps/events/relay.py`,
  `apps/payments/services.py` and `apps/orders/stream.py`.

---

## Bugs found, and how

Five real bugs, each fixed with a test that failed without the fix. Several were found by checking
the docs against the code: diagrams, numbers and untested rows.

### 1. The order stream missed changes made while it connected

- **Symptom.** An order page could show stale state after a change, until the next signal, a
  reconnect (up to 300 s) or the fallback poll.
- **Root cause.** The stream read the snapshot, sent it, and only **then** subscribed to the
  order's Pub/Sub channel. A change committed between the read and the subscription published a
  signal nobody was listening for.
- **How found.** Reviewing the live-tracking doc's sequence diagram: it showed snapshot, then
  subscribe, which leaves a window in which a change is missed. The code matched the diagram, and
  a new test proved it: on the old order it timed out with the page still showing "created".
- **Fix.** Subscribe first, then read and send. A change before the subscription is in the read; a
  change after it sends a signal; a signal for a change the read already has is absorbed by the
  version check. The ownership check stays before the stream starts, so another user's order is
  still a 404.
- **Test.** `test_a_change_committed_while_subscribing_is_not_missed` commits a change during the
  subscription without publishing a signal; it timed out on the old order.
- **Lesson.** With a lossy signal channel, subscribe before you read state.
- Docs: [flows/live-tracking.md](flows/live-tracking.md#stream-lifecycle).

### 2. The refund-due email for a duplicate payment

- **Symptom.** A second successful payment for an order that was already paid flagged a refund
  correctly, but the email told the customer the order had been canceled. A follow-up found the
  email also printed the internal `refund_reason` string verbatim.
- **Root cause.** The template assumed every refund-due case was a canceled order, and used the
  stored reason as customer text.
- **How found.** Checking each payments-doc claim against the code found a row of the
  late/out-of-order table with no test: a success on an already-approved order. Writing that test
  exposed the wrong email text.
- **Fix.** The email maps each stored reason to customer-facing text, with a generic fallback,
  and a second payment for a paid order gets its own wording. The stored reason stays unchanged on
  the intent and in the event payload.
- **Tests.** `test_a_second_payment_for_a_paid_order_flags_a_refund_and_one_email` (order, ledger
  and stock unchanged, exactly one email) and `test_refund_reasons_are_shown_in_customer_terms`,
  both failing on the old template. In the same commit,
  `test_a_webhook_that_fails_partway_rolls_back_and_applies_once_on_retry` was added, and shown to
  fail without the webhook's transaction.
- **Lesson.** Cover every row of a decision table with a test, including the "defensive" rows.
- Docs: [flows/payments.md](flows/payments.md#refund-due).

### 3. A navigation race after login and checkout

- **Symptom.** 3 of 6 full e2e runs failed: after login or checkout the URL stayed on `/login` or
  `/checkout`, even though the checkout `POST` had returned 201.
- **Root cause.** The forms called `router.push()` or `router.replace()` and then immediately
  `router.refresh()`, to re-render the header (a Server Component in the root layout). When the
  refresh's request stalled, the navigation never completed.
- **How found.** The e2e diagnostics commit (`1cdfda2`) kept Playwright traces on the host. The
  trace showed the checkout `POST` at 201, the navigation's request at 200, and the refresh's
  request still pending after more than 20 s. A no-refresh experiment on a branch confirmed the
  cause: every navigation reached its URL.
- **Fix.** After login, register, logout and checkout, navigate with a full page load
  (`window.location.assign`): the header renders fresh and there's no refresh to race.
- **Test.** The e2e helpers assert the header after login shows the account menu, and after
  checkout an empty cart. With the fix undone (a soft navigation without a refresh), that
  assertion failed on "Cart, 1 item". Afterwards: 5 of 5 full runs passed, 25/25 tests, no
  retries.
- **Lesson.** Don't call `router.refresh()` right after a soft navigation: it targets the current
  route, and the navigation can stall behind it.
- Docs: [flows/auth-and-sessions.md](flows/auth-and-sessions.md#after-an-auth-change-a-full-page-load),
  [flows/cart-checkout-stock.md](flows/cart-checkout-stock.md#after-the-order-is-placed-a-full-page-load).

### 4. Credentials in the URL before hydration (exposed by bug 3)

- **Symptom.** None seen by a user yet: a latent risk.
- **How found.** The same traces showed a "Pay" click 0.9 s before hydration that sent no request
  at all. Asking what an early click does on each form showed that the login, register and
  checkout forms had **no `method`**, and their inputs had `name`s. A submit before hydration was a
  native GET: `/login?next=/shop&email=…&password=…`, putting credentials (or the shipping address)
  in the URL, browser history, access logs and `Referer` headers.
- **Fix.** `method="post"` on all three forms, and every JavaScript-driven control renders
  disabled until hydrated (`useHydrated()`), so a click can't be lost and a form can't be
  submitted natively.
- **Test.** A unit test server-renders the login form and checks `method="post"` and the disabled
  submit; Playwright waits for controls to be enabled.
- **Lesson.** A flaky test is worth a root cause: this one led to a security fix.
- Docs: [flows/auth-and-sessions.md](flows/auth-and-sessions.md#before-hydration-disabled-controls-and-post-forms).

### 5. e2e polluted the dev database

- **Symptom.** Every e2e run left two **paid** orders, lower stock, emails and events in the dev
  database.
- **Root cause.** e2e ran against the dev stack, and a paid app order can't be canceled, so
  nothing could clean up after it.
- **How found.** Checking a figure for data-model.md: 58 app orders, where 53 were expected after
  the restore. The extra 5 traced to e2e runs.
- **Fix.** `make e2e` runs a separate compose project (`ecommerce-e2e`) with its own database on
  tmpfs, its own Redis and Mailpit, and no host ports, seeded fresh each run. Guards run before
  anything writes: the project name, a static check of every Django service's database settings,
  then a live check on each service of `current_database()` and the database server's IP. Any
  mismatch tears down and exits. A run lock allows one run at a time.
- **Verified** on 2026-11-09: dev database counts and dev Mailpit identical before and after six
  runs, and no e2e volume left behind.
- **Lesson.** Tests that create irreversible state need their own environment, with checks that
  prove which database they're writing to.
- Docs: [testing.md](testing.md#the-isolated-e2e-stack).

## Sources

- Everything above is drawn from [architecture.md](architecture.md), [data-model.md](data-model.md),
  [api.md](api.md), [flows/](flows/), [adr/](adr/README.md), [testing.md](testing.md),
  [limitations-and-roadmap.md](limitations-and-roadmap.md) and
  [operations/runbook.md](operations/runbook.md).
- The bug histories: commits `cec4819`, `c008542`, `197c594`, `1cdfda2`, `cc50a83` and `c382ea6`.
- Code read for the "At 100×" reasoning: [relay.py](../backend/apps/events/relay.py) (one `XADD`
  per row), [product_stats.py](../backend/apps/events/consumers/product_stats.py)
  (`ProductsChanged` per order event), [olist_import.py](../backend/apps/core/olist_import.py)
  (`_read()`), [projections.py](../backend/apps/analytics/projections.py) (`recompute_days()`),
  [stream.py](../backend/apps/orders/stream.py), [models.py](../backend/apps/events/models.py)
  (`EventLog` indexes) and [base.py](../backend/config/settings/base.py).
