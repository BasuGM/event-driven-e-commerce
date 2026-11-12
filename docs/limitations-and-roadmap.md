# Limitations and roadmap

What the system doesn't do, where it would break first, and what could come next. The
limitations are known and recorded on purpose (CLAUDE.md's "Known issues"). Each says what the
impact is, what already mitigates it, and the planned fix if there is one. The roadmap items are
ideas, not commitments.

## Known limitations

### Events and live updates

| Limitation | Impact | Mitigation today | Fix when needed |
|---|---|---|---|
| Redis persists streams with AOF `appendfsync everysec` | A hard Redis crash can lose up to ~1 s of entries the outbox already marked published | Partly: stats and analytics are state-based, so they recover with the next event for the same order or product. A lost entry's **side effects** (its email, its live-update signal, its event-log row) are never redone | `appendfsync always` (slower writes), replicated Redis, or the "republish" command in the roadmap |
| One Redis instance serves Celery, the event streams and Pub/Sub | A single point of failure: if Redis is down, there's no task delivery, no event delivery and no live updates (the outbox keeps the events, and the stream service polls the database) | The outbox and the database fallbacks keep the data correct | Separate or replicated Redis instances ([ADR 0001](adr/0001-redis-streams-over-kafka.md)) |
| Streams are trimmed to ~100,000 entries (`MAXLEN ~`) | A consumer group lagging further than that would miss entries | Lag is visible per group on `/staff/health` | A larger `MAXLEN`, alerting on lag, or a log with retention (Kafka, see [ADR 0001](adr/0001-redis-streams-over-kafka.md)) |
| The `analytics` consumer recomputes a whole purchase day per event | ~64 events/s; during a `--speed 0` replay, p95 latency 74.67 s (measured 2026-11-09) | Fine with real traffic and replays at `--speed` ≥ 1 | Coalesce each read batch to its distinct (day, source) pairs ([flows/analytics.md](flows/analytics.md#performance)) |
| `product_stats` records `ProductsChanged` for every non-replay order event with lines, even when neither `sales_count` nor `min_price` changed | Every placement, payment or cancel of a product revalidates its cached page, so the busiest product pages, the ones caching helps most, get revalidated almost constantly | Revalidating is harmless (the next visit just fetches fresh data), and the listing isn't cached, so only the product page's cache hit rate suffers | Record `ProductsChanged` only for products whose values actually changed, comparing before and after in the recompute's own transaction ([flows/catalog-and-search.md](flows/catalog-and-search.md#invalidation-when-stock-or-sales-change)) |
| Live updates use Redis Pub/Sub, which is fire-and-forget | A stream that's briefly unsubscribed misses a signal | The signal carries no state: the next signal, a reconnect (≤ 300 s), or the fallback poll restores the right state | — (by design) |
| One Redis Pub/Sub connection per open order stream | Connections grow with open pages | Fine at this scale | One shared subscriber per `stream` process (pattern `live:order:*`), fanning out to per-connection queues |
| Only the order detail page is live | `/orders` status badges update on reload only | — | A per-user channel |
| More than one relay gives up ordering | Events can be processed out of order | Handlers are state-based ([ADR 0003](adr/0003-state-based-idempotent-consumers.md)) | — (by design) |

### Orders, payments and email

| Limitation | Impact | Mitigation today | Fix when needed |
|---|---|---|---|
| No refund logic | Money that arrives for an order that can't take it is only **flagged** | `PaymentIntent.needs_refund` (filterable in the admin), the `PaymentRefundDue` event and the customer email | A refund call on the gateway, plus a refund state on the intent |
| No paid cancellation for app orders | Once paid, an app order can't be canceled or marked unavailable | `cancel_paid` and `mark_unavailable` exist, but refuse non-replay orders | Refund + restock design (and a seller/ops UI for fulfilment) |
| A declined payment cancels the order | A mistyped card means checking out again | Checkout is quick, and the stock is released at once | Allow retrying the same intent within the hold (as Stripe does) |
| A crash after SMTP accepted an email, before the row was marked sent | That email is sent a second time | A deterministic `Message-ID` lets clients spot the duplicate | — (no SMTP-side idempotency available) |
| Fulfilment (invoice, ship, deliver) is driven only by the replay | App orders stop at `approved` | — | A seller or ops workflow calling the existing services |

### Data, search and replay

| Limitation | Impact | Fix when needed |
|---|---|---|
| Search is Postgres full-text with prefix matching | No typo tolerance, no faceting | Meilisearch, once catalog size or search quality demands it ([ADR 0008](adr/0008-postgres-full-text-search.md)) |
| Product names, descriptions, prices and stock are generated | The catalog is plausible, not real | — (Olist has none of these) |
| Replay synthesizes invoiced, canceled and unavailable times (Olist has none). One order canceled after shipping is replayed as canceled after approval | Those step times are approximations | — |

### Development and tests

| Limitation | Impact | Fix when needed |
|---|---|---|
| `make e2e` takes ~5–9 min on the isolated stack (4:37–8:42 per run, measured 2026-11-09) | Slow feedback. A second full stack runs next to the dev one, and its Next **dev** server compiles routes under memory pressure | Run e2e against a production build (`next build && next start`). It's faster, but it **changes behaviour**: no dev compiles, and prerendering at build time |
| No CI workflow | Tests run only when someone runs them | A CI pipeline running `make test` and `make e2e` |
| Known test gaps | See [testing.md](testing.md#known-gaps) | — |
| `redis` (redis-py) pinned to 6.4.0 | `kombu[redis]` (Celery's transport) requires `< 6.5` | Unpin once kombu allows it |
| next-themes 0.4.6 logs a script-tag warning under React 19 | Console noise only | A newer next-themes release |
| `npm audit` reports findings via the `shadcn` package | They're in CLI tooling, not shipped to the browser | **Never** `npm audit fix --force` (it downgrades shadcn to 1.x) |

## Not production-ready

The stack is built for local development. CLAUDE.md's "Before deploying" section is the full
checklist (it's kept in one place on purpose). In summary:

- **Servers:** the frontend runs the Next **dev** server; production needs `next build && next start`.
  A production WSGI server instead of `manage.py runserver`, and static files served
  properly. The SSE path needs to be routed to the ASGI `stream` service, with no proxy buffering
  and timeouts above the 15 s heartbeat.
- **Security:** HTTPS (HSTS), secure session and CSRF cookies, real origins in
  `CSRF_TRUSTED_ORIGINS` and `ALLOWED_HOSTS`, and rate limiting on login and register.
- **Secrets and switches:** a real `DJANGO_SECRET_KEY`, `REVALIDATE_SECRET` and
  `PAYMENT_WEBHOOK_SECRET`; `DEBUG = False`; no dev users; `ALLOW_FAKE_PAYMENTS` off and a real
  payment provider; real SMTP.
- **The webhook:** its HMAC is over the raw body. The bytes must reach Django unchanged.

## Out of scope (for now)

These are listed in CLAUDE.md:
- Kafka (Redis Streams covers the concepts);
- Kubernetes, and a microservices split;
- real payments;
- websockets;
- push notifications;
- multi-tenant analytics.

## Roadmap candidates

These are ideas, roughly in the order they'd add value. Each links to where its groundwork already
exists.

1. **CI:** run `make test` and `make e2e` on every push.
2. **Analytics batch coalescing:** removes the pipeline's bottleneck
   ([flows/analytics.md](flows/analytics.md#performance)).
3. **`ProductsChanged` only on a real change:** `product_stats` compares the products' values
   before and after its recompute, in the same transaction, and records the event only for the
   ones that changed. Busy product pages then stay cached between real changes
   ([ADR 0017](adr/0017-cache-invalidation-by-consumer.md)).
4. **Refunds and paid cancellation:** turn `needs_refund` into an actual refund, and allow
   cancelling paid app orders with restock ([flows/payments.md](flows/payments.md#refund-due)).
5. **A real payment provider:** one more `PaymentGateway` class
   ([ADR 0005](adr/0005-fake-payment-provider.md)).
6. **An inventory consumer and back-in-stock alerts:** emit an "OfferStockChanged" event from
   `services.py`, where every stock change happens ([ADR 0009](adr/0009-no-inventory-consumer.md)).
7. **Per-user live channels:** live status on `/orders`.
8. **A shared Pub/Sub subscriber** per `stream` process.
9. **Rate limiting** on login and register (also on the production checklist).
10. **e2e on a production build:** faster, with the behaviour change noted above.
11. **Meilisearch,** when search quality or catalog size calls for it.
12. **A "republish outbox events since T" command:** re-sends published outbox rows (kept for
    7 days) to recover from lost stream entries. Consumers dedupe by event id, so re-sending
    events they already applied is harmless.

## Sources

- CLAUDE.md: "Known issues", "Before deploying", "Out of scope", the live-tracking "Not done" note
- [docs/adr/](adr/), the flow documents linked above, [testing.md](testing.md)
