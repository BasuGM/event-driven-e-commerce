# 0005. Fake payment provider behind `PaymentGateway`

- **Status:** Accepted
- **Date:** 2026-11-04 (commit `33842e0`, Step 5)

## Context

The shop needs a realistic payment flow:
1. create a payment at a provider;
2. send the customer to the provider's hosted page;
3. receive the result as a signed, asynchronous webhook.

The interesting engineering is in the edge cases: late, duplicated and out-of-order webhooks,
payments that arrive after an order was canceled, and retries. Those must be reproducible in
tests and on demand.

## Options considered

1. **Stripe test mode.** It's the obvious choice, and isn't available here:
   - **Stripe is invite-only in India.** An Indian business must request an invite, and the
     account must belong to a registered business, not an individual.
   - **The currency doesn't fit.** The Olist data is in BRL, which an Indian payment gateway
     wouldn't handle.
2. **No payment step.** Orders would be approved directly. That loses the whole asynchronous
   webhook flow the project is meant to demonstrate.
3. **A fake provider in the codebase**, behind an interface a real provider can implement.

## Decision

`apps/fake_provider` is a Stripe-shaped provider for dev and tests:
- hosted page, intents and events;
- Celery delivery with retries and backoff;
- `t=…,v1=HMAC-SHA256` signatures over the raw body.

The merchant side only talks to the `PaymentGateway` protocol (`create_payment`,
`parse_webhook`). `get_gateway()` picks the implementation from `PAYMENT_PROVIDER`. The fake
needs `ALLOW_FAKE_PAYMENTS`, which only the dev and test settings set; its URLs are mounted only
then.

## Consequences

- **The hard cases are testable.** Late, duplicate and out-of-order webhooks happen
  deterministically, in tests and from the hosted page ("deliver twice", "declined then
  succeeded, out of order", "succeed after a delay", "after the stock hold expires").
- **A real provider stays pluggable.** The `PaymentGateway` interface keeps the swap to one class.
- **The merchant code is the real thing:** signature verification over raw bytes,
  `ProviderEvent` dedupe, lock order, and refund flagging.
- **Not exercised:** a real provider's quirks (API errors, rate limits, its exact event
  ordering), and refunds, which aren't implemented on either side.
- **Production requires** `ALLOW_FAKE_PAYMENTS` off, a real gateway class, and a real
  `PAYMENT_WEBHOOK_SECRET`.

## Links

- [docs/flows/payments.md](../flows/payments.md)
- [backend/apps/payments/gateway.py](../../backend/apps/payments/gateway.py), [backend/apps/fake_provider/](../../backend/apps/fake_provider/), [backend/apps/payments/signature.py](../../backend/apps/payments/signature.py)
