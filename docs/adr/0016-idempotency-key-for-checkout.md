# 0016. `Idempotency-Key` for checkout

- **Status:** Accepted
- **Date:** 2026-10-14 (commit `46e9db7`, Step 3)

## Context

Checkout creates an order and takes stock. A network error or timeout leaves the browser not
knowing whether the request reached the server. A blind retry could place a second order and
take the stock twice. Disabling the button doesn't help when the response is lost.

## Options considered

1. **Client-side protection only** (disable the button, or dedupe in the browser). That doesn't
   cover a request that was processed but whose response was lost.
2. **Natural-key dedupe** (for example "one order per cart contents per minute"). Fragile, and
   wrong when someone genuinely orders the same thing twice.
3. **An idempotency key stored in Redis.** A separate store from the order transaction, so a
   crash between the two leaves them disagreeing.
4. **An idempotency key stored in Postgres, in the same transaction as the work**, with the
   response.

## Decision

`POST /api/checkout/` requires an `Idempotency-Key` header: 8–255 URL-safe characters, generated
by the browser per attempt and reused on retry.
- **One transaction.** `run_idempotent` inserts `IdempotencyKey(user, key, request_hash)` in the
  same transaction as `checkout()`, and stores the successful response on it.
- **Replays and conflicts.** The same key with the same body replays the stored response
  (`Idempotent-Replayed: true`). The same key with a different body is a `409
  idempotency_conflict`.
- **Failures aren't stored**, so a retry after "out of stock" runs again.
- **Keys expire after 24 h.**

**Starting a payment needs no key.** The partial unique index `uniq_open_intent_per_order`, plus
the provider's own idempotency key `order:<id>:intent`, already make it idempotent.

## Consequences

- **A retried checkout can't create a second order,** even when two identical requests are
  concurrent (`test_concurrent_retries_with_the_same_key_create_one_order`): the second waits on
  the unique index, then replays.
- **The browser must manage attempts.** It ties a key to a fingerprint of the cart and the
  address, keeps it in `sessionStorage`, and starts a new attempt when either changes.
- **The keys table grows,** and is purged daily.

## Links

- [docs/api.md](../api.md#idempotency-key-checkout), [docs/flows/cart-checkout-stock.md](../flows/cart-checkout-stock.md)
- [backend/apps/core/idempotency.py](../../backend/apps/core/idempotency.py), [frontend/src/lib/checkout-attempt.ts](../../frontend/src/lib/checkout-attempt.ts)
