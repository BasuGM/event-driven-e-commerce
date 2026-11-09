# 0014. Replay: copies through the real services

- **Status:** Accepted
- **Date:** 2026-11-09 (commit `fad9cf3`, Step 7c)

## Context

The imported Olist history is static: the importer emits no events. To see the event
pipeline, consumers, live page, explorer and dashboard under realistic traffic, the project
needs a way to re-enact history as live events. That must not disturb the shop (prices, stock,
sales counts) or the imported data, and it must be removable.

## Options considered

1. **Replay the original orders in place** (reset their status, then walk them forward). It
   destroys the imported history, and the result can't be cleanly undone.
2. **Inject events straight into the streams.** No orders would exist behind the events, so
   consumers that read the database (analytics, live page, timelines) would see nothing.
3. **A synthetic order generator.** Unrealistic distributions, and no way to check the result
   against known totals.
4. **Copies of imported orders, advanced through the real order services**, on a simulated
   clock.

## Decision

Option 4:
- **Copies.** Each original gets at most one copy (`source='replay'`, `replay_of`,
  `replay_run`, unique `replay_of`), owned by `replay@example.com`.
- **Steps.** Each step is a real service call (`pay()`, `invoice()`, `ship()`, `deliver()`,
  `mark_unavailable()`, `cancel()`, `cancel_paid()`) that transitions, writes history and records
  its event.
- **Steps are idempotent:** a step applies only while the copy is in that step's from-status,
  under the order lock.
- **Bypassed:**
  - cart, checkout and reservations, which would drain real stock;
  - the payment provider;
  - emails.
- **Excluded from the shop:** prices, sales counts and public counts ignore replay copies.
- **Only the replay moves a copy.** Endpoints answer `409 replay_read_only`, the sweeper skips
  copies, and the paid-cancel and unavailable services refuse non-replay orders.
- **One running replay at a time.** It's enforced by the partial unique index
  `one_running_replay`, with:
  - a heartbeat;
  - takeover after 5 minutes of silence;
  - self-abort through conditional updates, when a run finds it has been taken over.
- **`replay_reset`** removes every trace and rebuilds the affected projections.

## Consequences

- **Realistic traffic through every part of the system,** and a consistency check. On
  2026-11-09 the replay's analytics equalled the imported totals:
  - 2,000 orders, 1,976 paid, GMV R$ 316.909,40;
  - in browser QA, all six KPIs for 20–30 Nov 2017.
- **Fully removable.** `replay_reset` restored every baseline figure in QA.
- **Synthesized steps.** Olist has no invoiced, canceled or unavailable times, so those are made
  up (approval + 1 h). One order canceled after shipping is replayed as canceled after approval.
- **New, replay-only code paths** (paid cancel, unavailable) exist in the order services, and
  are guarded against non-replay use.
- **It exposed the analytics bottleneck** ([0011](0011-analytics-projections-recompute.md)).

## Links

- [docs/flows/replay.md](../flows/replay.md)
- [backend/apps/replay/](../../backend/apps/replay/), [backend/apps/orders/services.py](../../backend/apps/orders/services.py)
- Tests: [test_replay.py](../../backend/tests/test_replay.py)
