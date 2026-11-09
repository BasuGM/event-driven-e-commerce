"""Order emails: one pending row per (event, kind), sent after commit, retried, never twice."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail
from django.utils import timezone

from apps.core.formatting import format_brl
from apps.events.consumers.notifications import NotificationsConsumer
from apps.events.relay import publish_batch
from apps.fake_provider.provider import FAIL, SUCCEED, SUCCEED_LATER, choose
from apps.notifications.models import Notification
from apps.notifications.sender import send_due, send_one
from apps.orders.services import cancel, release_expired

pytestmark = pytest.mark.django_db


def consume(events_redis, consumer_cls=NotificationsConsumer):
    """Publish the outbox and let the notifications consumer process everything."""
    consumer = consumer_cls(events_redis, consumer_name="t1")
    consumer.ensure_groups()
    publish_batch(events_redis)
    consumer.run_once(claim=False)
    return consumer


def kinds():
    return sorted(Notification.objects.values_list("kind", flat=True))


@pytest.mark.parametrize("value, text", [
    ("0", "R$ 0,00"), ("75.01", "R$ 75,01"), ("1234.5", "R$ 1.234,50"), ("1234567.891", "R$ 1.234.567,89"),
])
def test_format_brl_matches_the_storefront(value, text):
    assert format_brl(Decimal(value)) == text


def test_order_placed_writes_one_pending_email_with_lines_totals_and_link(events_redis, placed_order):
    order, user, (a, b) = placed_order
    consume(events_redis)

    [n] = Notification.objects.all()
    assert (n.kind, n.status, n.recipient, n.order_id) == ("order_placed", "pending", user.email, order.pk)
    number = f"#{order.external_id[:8]}"
    assert n.subject == f"We've received order {number}"
    assert f"2 x {a.product.name}  R$ 119,80" in n.body_text
    assert "Total:    R$ 154,80" in n.body_text
    assert f"http://shop.test/orders/{order.external_id}" in n.body_text
    assert "R$ 154,80" in n.body_html and f"http://shop.test/orders/{order.external_id}" in n.body_html
    assert mail.outbox == []  # written, not sent: sending happens after commit, elsewhere


@pytest.mark.parametrize(
    "act, kind",
    [
        (lambda o, f, run: run(choose(f, SUCCEED)), "order_paid"),
        (lambda o, f, run: run(choose(f, FAIL)), "payment_failed"),
        (lambda o, f, run: cancel(o.pk), "order_canceled"),
        (lambda o, f, run: release_expired(now=timezone.now() + timedelta(hours=1)), "reservation_expired"),
    ],
)
def test_each_order_event_kind_produces_one_pending_row(events_redis, awaiting_payment, run_deliveries, act, kind):
    order, _, fake = awaiting_payment
    act(order, fake, run_deliveries)
    consume(events_redis)
    assert kinds() == sorted(["order_placed", kind])


def test_a_late_payment_gets_a_refund_due_email(events_redis, awaiting_payment, run_deliveries):
    order, intent, fake = awaiting_payment
    deliveries = choose(fake, SUCCEED_LATER, delay=60)
    release_expired(now=timezone.now() + timedelta(hours=1))
    run_deliveries(deliveries)
    consume(events_redis)

    assert kinds() == ["order_placed", "refund_due", "reservation_expired"]
    refund = Notification.objects.get(kind="refund_due")
    assert refund.subject == f"Refund due for order #{order.external_id[:8]}"
    assert "refund of R$ 154,80" in refund.body_text


def test_a_second_payment_for_a_paid_order_flags_a_refund_and_one_email(
    events_redis, awaiting_payment, run_deliveries
):
    """Defensive path: the shop never opens a second intent for a paid order (start_payment
    refuses), but a provider could still deliver a second success. Built directly here."""
    from apps.events.models import OutboxEvent
    from apps.fake_provider.gateway import FakeGateway
    from apps.fake_provider.models import FakeIntent
    from apps.payments.models import PaymentIntent

    order, first, fake = awaiting_payment
    run_deliveries(choose(fake, SUCCEED))
    order.refresh_from_db()
    assert order.status == "approved"
    stock = dict(order.reservations.values_list("offer_id", "offer__stock"))

    second = FakeGateway().create_payment(
        amount=first.amount, currency="BRL", reference=order.external_id,
        return_url="/", expires_at=None, idempotency_key=f"order:{order.external_id}:second",
    )
    intent = PaymentIntent.objects.create(
        order=order, provider="fake", provider_payment_id=second.id, amount=first.amount,
    )
    run_deliveries(choose(FakeIntent.objects.get(pk=second.id), SUCCEED, twice=True))

    order.refresh_from_db()
    intent.refresh_from_db()
    assert order.status == "approved"  # untouched
    assert (intent.status, intent.needs_refund, intent.refund_reason) == ("succeeded", True, "order already approved")
    assert order.payments.count() == 1  # the ledger has only the first payment
    assert dict(order.reservations.values_list("offer_id", "offer__stock")) == stock  # stock unchanged
    assert list(
        OutboxEvent.objects.filter(aggregate_id=order.external_id).order_by("occurred_at", "id")
        .values_list("event_type", flat=True)
    ) == ["OrderPlaced", "OrderPaid", "PaymentRefundDue"]  # the duplicate delivery added nothing

    consume(events_redis)
    [refund] = Notification.objects.filter(kind="refund_due")
    assert refund.subject == f"Refund due for order #{order.external_id[:8]}"
    assert "a second payment of R$ 154,80 was received for an order that was already paid" in refund.body_text
    assert "after the order was canceled" not in refund.body_text
    assert "refund of R$ 154,80" in refund.body_text


def test_a_refund_due_for_a_canceled_order_says_so(events_redis, awaiting_payment, run_deliveries):
    order, _, fake = awaiting_payment
    deliveries = choose(fake, SUCCEED_LATER, delay=60)
    release_expired(now=timezone.now() + timedelta(hours=1))
    run_deliveries(deliveries)
    consume(events_redis)

    refund = Notification.objects.get(kind="refund_due")
    assert (
        "We received your payment of R$ 154,80, but the order had already been canceled, "
        "so we couldn't accept it." in refund.body_text
    )
    assert "paid after the order was canceled" not in refund.body_text  # never the raw reason
    assert "already paid" not in refund.body_text


@pytest.mark.parametrize("reason, text", [
    ("paid after the stock hold expired", "but your payment arrived after the stock hold expired"),
    ("paid after the order was canceled", "but the order had already been canceled"),
    ("something new we never mapped", "but the order could no longer take a payment"),
])
def test_refund_reasons_are_shown_in_customer_terms(placed_order, reason, text):
    """Stored reasons (PaymentIntent.refund_reason, event payloads) stay as they are; the email
    maps them, with a generic fallback, and never prints the raw string."""
    from apps.notifications.rendering import render
    from apps.orders.events import order_payload

    order, user, _ = placed_order
    order.status = "canceled"
    payload = order_payload(order, reason="refund_due", now=timezone.now())
    payload["payment"] = {"amount": "154.80", "refund_reason": reason}
    _, body_text, body_html = render("refund_due", payload, recipient_name="Ana")

    assert f"We received your payment of R$ 154,80, {text}, so we couldn't accept it." in body_text
    assert reason not in body_text and reason not in body_html


def test_a_duplicate_or_replayed_event_never_makes_a_second_email(events_redis, placed_order):
    consume(events_redis)
    # The same stream entries again for the same group: ProcessedEvent stops them
    NotificationsConsumer(events_redis, consumer_name="t1").run_once(claim=True)

    class Replay(NotificationsConsumer):  # a new group reads the stream from the start
        name = "notifications_replay"

    consume(events_redis, Replay)  # no ProcessedEvent for this group: the unique row stops it

    assert Notification.objects.count() == 1
    assert send_due() == {"sent": 1}
    assert send_due() == {}
    assert len(mail.outbox) == 1


def test_sending_happens_only_after_the_consumer_commits(events_redis, placed_order, django_capture_on_commit_callbacks):
    with mock.patch("apps.notifications.tasks.send_notification.delay") as delay:
        with django_capture_on_commit_callbacks() as callbacks:
            consume(events_redis)
            assert mail.outbox == [] and not delay.called  # nothing inside the transaction
        for callback in callbacks:
            callback()
    delay.assert_called_once_with(Notification.objects.get().pk)


def test_a_send_failure_is_retried_later_and_sent_exactly_once(events_redis, placed_order):
    consume(events_redis)
    n = Notification.objects.get()
    now = timezone.now()

    with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=ConnectionRefusedError("smtp down")):
        assert send_one(n.pk, now=now) == "retry"
    n.refresh_from_db()
    assert (n.status, n.attempts, n.last_error) == ("pending", 1, "ConnectionRefusedError: smtp down")
    assert n.next_attempt_at == now + timedelta(seconds=30)

    assert send_one(n.pk, now=now + timedelta(seconds=10)) == "skipped"  # not due yet
    assert send_one(n.pk, now=now + timedelta(seconds=31)) == "sent"
    assert send_one(n.pk, now=now + timedelta(hours=1)) == "skipped"  # already sent

    [email] = mail.outbox
    assert email.to == [n.recipient] and email.subject == n.subject
    assert email.extra_headers["Message-ID"] == f"<notification-{n.pk}@olist-commerce.local>"
    assert email.alternatives[0].mimetype == "text/html"


def test_gives_up_after_max_attempts(events_redis, placed_order, settings):
    settings.NOTIFICATION_MAX_ATTEMPTS = 2
    consume(events_redis)
    n = Notification.objects.get()
    with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("nope")):
        assert send_one(n.pk, now=timezone.now()) == "retry"
        assert send_one(n.pk, now=timezone.now() + timedelta(hours=2)) == "failed"
    n.refresh_from_db()
    assert n.status == "failed" and mail.outbox == []


def test_end_to_end_pay_on_the_fake_page_to_one_confirmation_email(
    events_redis, awaiting_payment, run_deliveries, django_capture_on_commit_callbacks
):
    """checkout -> pay (fake provider) -> signed webhook -> OrderPaid -> consumer -> sender."""
    order, _, fake = awaiting_payment
    run_deliveries(choose(fake, SUCCEED, twice=True))  # the duplicate webhook is ignored

    with mock.patch("apps.notifications.tasks.send_notification.delay", side_effect=send_one):
        with django_capture_on_commit_callbacks(execute=True):
            consume(events_redis)

    order.refresh_from_db()
    assert order.status == "approved"
    paid = [m for m in mail.outbox if m.subject.startswith("Payment confirmed")]
    assert [m.subject for m in paid] == [f"Payment confirmed for order #{order.external_id[:8]}"]
    assert len(mail.outbox) == 2  # plus the "We've received order" email from OrderPlaced
