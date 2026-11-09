# 0006. `PaymentIntent` vs the `Payment` ledger

- **Status:** Accepted
- **Date:** 2026-11-04 (commit `33842e0`, Step 5)

## Context

Olist's data already has `orders.Payment`: a settled-payments ledger per order (sequential
number, type, installments, value). The imported orders and analytics rely on that shape.

A provider's payment, however, has a lifecycle of its own, much of which never becomes settled
money:
- created, the customer on the hosted page, "processing";
- succeeded or failed;
- duplicates, and late arrivals for orders that were canceled meanwhile.

## Options considered

1. **One table.** Add a `status` (and provider fields) to `orders.Payment`. Every consumer of the
   ledger would then have to filter out unsettled rows, and Olist's shape would get
   provider-specific columns.
2. **Two tables with two jobs.**
   - `payments.PaymentIntent` holds the provider lifecycle: one open intent per order,
     `processing` UI state, and `needs_refund`.
   - `orders.Payment` remains the settled ledger, written only by `services.pay()` on success.

## Decision

Two tables. `PaymentIntent` is unique on `provider_payment_id`. The partial unique index
`uniq_open_intent_per_order` (open statuses: `requires_payment`, `processing`) allows only one
open intent per order. `ProviderEvent` records every applied webhook once, with its outcome.

## Consequences

- **The ledger contains only settled money**, in the same shape for imported and app orders.
- **The messy states live outside it:** abandoned, failed and duplicate payments, and money for
  orders that can't take it (`needs_refund`). They live in `PaymentIntent` and `ProviderEvent`,
  where the admin can filter them.
- **Paying again is safe.** Repeated clicks, or paying after "processing" went overdue, reuse
  the same open intent, so the provider sees one payment and can't double-charge.
- **Two models to explain.** Docstrings on both models point at each other.

## Links

- [docs/flows/payments.md](../flows/payments.md), [docs/data-model.md](../data-model.md)
- [backend/apps/payments/models.py](../../backend/apps/payments/models.py), [backend/apps/orders/models.py](../../backend/apps/orders/models.py) (`Payment`), [backend/apps/orders/services.py](../../backend/apps/orders/services.py) (`pay`)
