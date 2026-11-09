# Notifications (email)

Customers get an email when an order is placed, paid, declined, canceled, expired, or when a
refund is due. Emails are driven by domain events. They are **never sent inside a database
transaction**: an email can't be rolled back, and SMTP can be slow or down.

In development every email lands in Mailpit (`make mail` prints its URL; default
http://localhost:8025).

## Two steps: decide, then send

```
order event ──▶ notifications consumer ──▶ Notification row (pending)   ← in the consumer's transaction
                                              │ on commit
                                              ▼
                                Celery send_notification ──▶ SMTP        ← its own transaction, row locked
                                Celery beat send_due_notifications (30 s) ── retries + lost enqueues
```

### 1. The consumer writes a pending row

The `notifications` consumer is in
[backend/apps/events/consumers/notifications.py](../../backend/apps/events/consumers/notifications.py).

**Which events it handles:**

| Event | Email kind |
|---|---|
| `OrderPlaced` | `order_placed` |
| `OrderPaid` | `order_paid` |
| `PaymentFailed` | `payment_failed` |
| `OrderCanceled` | `order_canceled` |
| `ReservationExpired` | `reservation_expired` |
| `PaymentRefundDue` | `refund_due` |

Fulfilment events (invoiced, shipped, delivered, unavailable) send no email. Neither do replay
orders: the consumer skips `order_source == "replay"` (`is_replay()`), because a replay would
otherwise email thousands of historical orders to the replay account.

**What it does for an event:**

1. Looks up the recipient from the payload's `user_id`. A user without an email is skipped,
   with a log line.
2. **Renders the email now**: the subject, plain text and HTML, from
   `notifications/order_email.{txt,html}` with the order's lines and totals
   ([rendering.py](../../backend/apps/notifications/rendering.py)). Money is formatted with
   `format_brl` ("R$ 1.234,50"), and links use `FRONTEND_PUBLIC_URL`.
3. Inserts a pending `Notification` row **in the consumer's transaction**, together with the
   consumer's `ProcessedEvent` row ([event-pipeline.md](event-pipeline.md)).
4. Registers `transaction.on_commit(...)` to enqueue the Celery task `send_notification`.

**What the email is rendered from.** Rendering happens when the consumer handles the event,
usually seconds after it was recorded:
- **From the event payload:** the order id, status, lines (quantities, unit prices) and totals,
  and for a refund the payment amount and reason. These are as of the moment the event was
  recorded.
- **From the database, when the event is handled:** only the product **names** (falling back to
  the slug) and the recipient's email address.

The result is stored on the `Notification` row, and the sender sends exactly that. A retry hours
later sends the same content, even if the order has moved on since.

**Two guards against a duplicate email:**

- **`ProcessedEvent(consumer, event_id)`** is the consumer framework's dedupe. A redelivered
  event is acknowledged without running the handler.
- **The unique constraint `(event_id, kind)` on `Notification`.** If the same event is handled
  again anyway, the insert fails inside a savepoint, and the handler returns without enqueuing
  anything. That happens when `ProcessedEvent` rows were purged (after 90 days), or under a new
  consumer group.

### 2. The sender sends it

`send_one()` is in [backend/apps/notifications/sender.py](../../backend/apps/notifications/sender.py).
It runs **one notification per transaction**:

1. **Lock the row.** `SELECT … FOR UPDATE SKIP LOCKED`, restricted to `status = 'pending'` and
   `next_attempt_at <= now`. A row another sender is working on is skipped, not waited for. A row
   that's already sent, or not due yet, is "skipped".
2. **Send** through Django's mailer (`MAILERS["default"]`; SMTP to Mailpit in dev). The message
   has a **deterministic `Message-ID`**: `<notification-<id>@olist-commerce.local>`.
3. **On success:** mark the row `sent` with `sent_at`, in the same transaction.
4. **On any exception:** increment `attempts`, store `last_error`, and schedule
   `next_attempt_at` with exponential backoff: 30 s, 60 s, 120 s, … capped at 1 hour. After
   `NOTIFICATION_MAX_ATTEMPTS` (8) attempts, the row becomes `failed` and an error is logged.

**The safety net.** Celery beat runs `send_due_notifications` every 30 s. It sends every pending
row that's due: retries whose backoff has passed, and rows whose enqueue was lost. For example,
the broker was down at commit time; the `on_commit` hook uses `robust=True`, so that failure
is only logged. So an email is delayed at most about 30 s by a lost task, never dropped.

## Guarantees

| Failure | What happens |
|---|---|
| The consumer crashes before commit | No row, no `ProcessedEvent`; the event is redelivered and handled again |
| The broker is down after commit | The row stays pending; the beat sweep sends it within ~30 s |
| SMTP is down | The row is retried with backoff, then marked `failed` after 8 attempts |
| Two senders pick the same row | `SKIP LOCKED`: only one sends it |
| The same event is delivered twice | `ProcessedEvent`, then the unique `(event_id, kind)` |
| **The process dies after SMTP accepted the message, before the commit** | **The row is still pending, so the email is sent again once.** The `Message-ID` is the same, so a mail client or Mailpit can recognise the duplicate |

That last row is the one gap that remains. Closing it would need the SMTP server to take part in
the database transaction, which it can't. Every outbound side effect without its own
idempotency key has this shape.

## Tests

[backend/tests/test_notifications.py](../../backend/tests/test_notifications.py) covers:
- one pending row per event kind;
- the refund-due email for a late payment;
- no second email for a duplicate or replayed event;
- sending only after the consumer commits (`django_capture_on_commit_callbacks`);
- a failed send retried and sent exactly once;
- giving up after the maximum attempts;
- an end-to-end test from paying on the fake page to exactly one confirmation email.

## Sources

- [backend/apps/events/consumers/notifications.py](../../backend/apps/events/consumers/notifications.py)
- [backend/apps/notifications/](../../backend/apps/notifications/) (models, rendering, sender, tasks, templates)
- [backend/apps/core/formatting.py](../../backend/apps/core/formatting.py), [backend/config/settings/base.py](../../backend/config/settings/base.py) (`MAILERS`, `NOTIFICATION_MAX_ATTEMPTS`, beat schedule)
