# 0015. Stock reserved at checkout, under row locks, in a fixed lock order

- **Status:** Accepted
- **Date:** 2026-10-14 (commit `46e9db7`, Step 3)

## Context

Two buyers must never both get the last unit. Stock should be held while a buyer pays, but not
forever, and not by people who merely put something in a cart. Payment confirmation arrives
asynchronously, later.

## Options considered

**When to take stock:**
1. **At add-to-cart.** Abandoned carts would lock stock away from people ready to pay.
2. **At payment confirmation.** A buyer could pay for something that sold out while they were on
   the provider's page.
3. **At checkout, held for a short payment window** (a reservation with a TTL), and released on
   decline, cancel or expiry.

**How to make it race-free:**
1. **Optimistic or conditional updates.** Either a version column, or a per-line conditional
   `UPDATE … SET stock = stock - qty WHERE stock >= qty`. The conditional update is atomic,
   lock-free, and needs no retries.
2. **`SERIALIZABLE` isolation** with retry on serialization failures.
3. **Pessimistic row locks** (`SELECT … FOR UPDATE`) in one fixed, global lock order.

## Decision

Stock is decremented **at checkout**, with a `Reservation` per offer that expires after
`RESERVATION_TTL_MINUTES` (15). It's taken under **row locks**, in the project-wide order:

```
Cart (owner) → Order → PaymentIntent → Offers (ascending id) … then, after commit, Products (ascending id)
```

- **The decrement** happens in SQL, with `F()`.
- **The backstop** is `CHECK (stock >= 0)` in the database.
- **Releases** use a conditional `UPDATE … WHERE status = 'active'`, so stock comes back exactly
  once.
- **The expiry sweeper** uses `SKIP LOCKED`, one order per transaction.

Why pessimistic locks rather than conditional updates or `SERIALIZABLE`:
- **All or nothing, with every problem reported.** A cart has several lines, which must succeed
  or fail together, and the error must list every short line. Locking all the offers first, in
  ascending id order, gives checkout a stable view: it can check every line before any
  decrement.
- **Conditional updates don't fit that.** A per-line `UPDATE … WHERE stock >= qty` can't report
  all the short lines without extra reads, and it complicates all-or-nothing.
- **`SERIALIZABLE` would push retry loops into every write path.**
- **Waiting suits the contention.** It concentrates on a few hot offers, where a short wait beats
  fail-and-retry.
- **Safety nets.** The fixed lock order prevents deadlocks, and `CHECK (stock >= 0)` is the
  backstop.

## Consequences

- **Overselling is impossible, by construction and by constraint**
  (`test_two_buyers_one_last_unit`). An out-of-stock checkout lists every short line at once.
- **No deadlocks between the order flow's paths**
  (`test_opposite_cart_order_does_not_deadlock`), as long as every new code path follows the
  lock order. That's a rule reviewers must enforce.
- **Hot offers serialise checkouts.** Concurrent buyers of the same offer wait on its row lock.
  That's fine at this scale, and the obvious contention point at much larger scale.
- **Unpaid orders hold stock for up to 15 minutes,** plus up to a minute until the sweeper runs.
- **Reliance on the services.** Every stock change after the import must go through
  `apps/orders/services.py`. That's a documented rule, not something the database enforces.

## Links

- [docs/flows/cart-checkout-stock.md](../flows/cart-checkout-stock.md)
- [backend/apps/orders/services.py](../../backend/apps/orders/services.py), [backend/apps/catalog/models.py](../../backend/apps/catalog/models.py) (`Offer.stock`), [backend/tests/test_concurrency.py](../../backend/tests/test_concurrency.py)
