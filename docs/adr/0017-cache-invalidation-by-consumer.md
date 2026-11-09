# 0017. Product cache revalidated by an event consumer

- **Status:** Accepted
- **Date:** 2026-10-23 (commit `b633ef4`, Step 4; the product page cache itself since `73666d8`, Step 2)

## Context

Product detail pages are cached by Next.js (`"use cache"` with tags). They're the same for
everyone, and read far more often than they change. When an offer sells out, or its sales count
changes, the cached page must not keep showing the old state for long. The listing is never
cached.

## Options considered

1. **No caching.** Always fresh, and every product view hits the API.
2. **A short TTL only.** Pages can be stale for up to the whole TTL after a sell-out.
3. **Revalidate from the request path:** call Next right after the order transaction commits.
   That's HTTP inside the order flow: a slow or down frontend would slow checkout, or the call
   would need its own retry logic. And `sales_count` is updated asynchronously by a consumer
   ([0003](0003-state-based-idempotent-consumers.md)), so the call could run before the new
   value exists.
4. **Revalidate from an event consumer, chained after the stats recompute.**

## Decision

Option 4, with a TTL as the backstop:
1. **The product page fetch** is cached with `cacheLife({ stale: 60, revalidate: 300, expire: 3600 })`
   and tagged `product:<slug>`.
2. **`product_stats`** recomputes the products' stats, then records `ProductsChanged` (with
   their slugs) in the same transaction.
3. **`cache_invalidation`** POSTs those tags to Next's `/internal/revalidate`. The route checks a
   shared secret with `timingSafeEqual`, and calls `revalidateTag(tag, { expire: 0 })`.

## Consequences

- **The cache is dropped only after the new values are committed.** That's the "chained so
  revalidation always follows the recompute" rule in CLAUDE.md.
- **Failures retry, with a backstop.** A failed call is retried like any consumer failure. After
  5 attempts it goes to the DLQ (retryable from `/staff/health`), and `revalidate: 300` bounds
  the staleness meanwhile.
- **A few seconds of lag.** The product page can be stale for the seconds the consumer chain
  takes. The listing and the in-stock filter are fresh immediately (`min_price` is refreshed on
  commit, and the listing isn't cached).
- **An internal endpoint to protect.** `/internal/revalidate` must stay off the public edge,
  and `REVALIDATE_SECRET` must be a real secret in production.

## Links

- [docs/flows/catalog-and-search.md](../flows/catalog-and-search.md#invalidation-when-stock-or-sales-change)
- [frontend/src/lib/api/catalog.ts](../../frontend/src/lib/api/catalog.ts), [frontend/src/app/internal/revalidate/route.ts](../../frontend/src/app/internal/revalidate/route.ts), [backend/apps/events/consumers/product_stats.py](../../backend/apps/events/consumers/product_stats.py), [backend/apps/events/consumers/cache_invalidation.py](../../backend/apps/events/consumers/cache_invalidation.py)
- Tests: `test_end_to_end_checkout_to_cache_revalidation`, `test_cache_consumer_retries_a_failing_frontend_then_dead_letters`
