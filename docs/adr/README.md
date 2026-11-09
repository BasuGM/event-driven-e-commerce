# Architecture decision records

Each record captures one significant decision: the context it was made in, the options
considered, what was decided, and what that costs. The date is the commit that introduced the
decision (the design discussion came before it).

The context and options are written from the code and CLAUDE.md, plus the author's rationale.

| # | Decision | Status | Date |
|---|---|---|---|
| [0001](0001-redis-streams-over-kafka.md) | Redis Streams over Kafka | Accepted | 2026-10-09 |
| [0002](0002-transactional-outbox-and-relay.md) | Transactional outbox + dedicated relay | Accepted | 2026-10-23 |
| [0003](0003-state-based-idempotent-consumers.md) | State-based, idempotent consumers | Accepted | 2026-10-23 |
| [0004](0004-sessions-behind-the-next-proxy.md) | Django sessions over JWT, behind the Next proxy | Accepted | 2026-10-14 |
| [0005](0005-fake-payment-provider.md) | Fake payment provider behind `PaymentGateway` | Accepted | 2026-11-04 |
| [0006](0006-payment-intent-vs-ledger.md) | `PaymentIntent` vs the `Payment` ledger | Accepted | 2026-11-04 |
| [0007](0007-sse-signal-plus-snapshot.md) | SSE: Pub/Sub signal + DB snapshot, on a separate ASGI service | Accepted | 2026-11-04 |
| [0008](0008-postgres-full-text-search.md) | Postgres full-text search over a search engine | Accepted | 2026-10-13 |
| [0009](0009-no-inventory-consumer.md) | No inventory consumer (yet) | Accepted | 2026-11-04 |
| [0010](0010-money-as-decimal-strings.md) | Money as `Decimal`, serialised as decimal strings | Accepted | 2026-10-13 |
| [0011](0011-analytics-projections-recompute.md) | Analytics projections: DELETE + INSERT under advisory locks | Accepted | 2026-11-09 |
| [0012](0012-order-source-without-default.md) | `Order.source` with no default | Accepted | 2026-11-09 |
| [0013](0013-staff-pages-404.md) | Staff pages answer 404 to everyone else | Accepted | 2026-11-05 |
| [0014](0014-replay-through-real-services.md) | Replay: copies through the real services | Accepted | 2026-11-09 |
| [0015](0015-stock-reserved-at-checkout-under-row-locks.md) | Stock reserved at checkout, under row locks, in a fixed lock order | Accepted | 2026-10-14 |
| [0016](0016-idempotency-key-for-checkout.md) | `Idempotency-Key` for checkout | Accepted | 2026-10-14 |
| [0017](0017-cache-invalidation-by-consumer.md) | Product cache revalidated by an event consumer | Accepted | 2026-10-23 |

## Template

```markdown
# NNNN. Title

- **Status:** Proposed | Accepted | Superseded by NNNN
- **Date:** YYYY-MM-DD (commit `abc1234`)

## Context
What forces were at play: requirements, constraints, what already existed.

## Options considered
1. **Option** — what it would mean; why it was or wasn't chosen.

## Decision
What was decided, in one or two sentences, then the specifics.

## Consequences
What gets easier, what gets harder, what is now a known limitation.

## Links
Code, docs and tests that implement or verify it.
```
