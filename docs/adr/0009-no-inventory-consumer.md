# 0009. No inventory consumer (yet)

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded in CLAUDE.md in commit `33842e0`, after the event pipeline landed in Step 4)

## Context

With an event pipeline in place, it's tempting to move stock handling into it: an "inventory"
consumer reacting to order events, plus stock events such as "StockLow" or "OutOfStock" (names
not used in the code). The question is which stock behaviour belongs in the synchronous order
flow, and which belongs in consumers.

## Options considered

1. **An inventory consumer owns stock.** Checkout would emit an event, and a consumer would
   decrement stock. Oversell protection would then be eventual: two buyers could both be
   accepted for the last unit before the consumer catches up.
2. **Stock stays synchronous, and the events report it.** Checkout reserves stock under row
   locks. `min_price` (the in-stock filter) is refreshed right after commit. Stock-driven cache
   refreshes already flow through `product_stats → ProductsChanged → cache_invalidation`.

## Decision

Option 2, as recorded in CLAUDE.md:
- **Oversell protection stays synchronous** in `checkout()`.
- **`min_price` stays on-commit**, because the in-stock filter must be right at once.
- **Stock events would have no reader yet.** When a feature needs one, such as back-in-stock
  alerts or restocking, emit an "OfferStockChanged" event from `services.py`, where every stock
  change already happens, and build the consumer together with it.

## Consequences

- **The strongest guarantees stay where they're cheapest to keep:** "never oversell" and "the
  listing's stock filter is correct" live in one transaction, plus an on-commit refresh.
- **There's no event-sourced stock history.** Stock changes are only visible indirectly, through
  order events.
- **Adding a stock event later is a local change.** Every stock mutation is in one module.

## Links

- [docs/flows/cart-checkout-stock.md](../flows/cart-checkout-stock.md), [docs/flows/event-pipeline.md](../flows/event-pipeline.md#why-some-things-are-not-events)
- [backend/apps/orders/services.py](../../backend/apps/orders/services.py), [backend/apps/catalog/stats.py](../../backend/apps/catalog/stats.py) (`refresh_product_stats_on_commit`)
