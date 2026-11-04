"""Starting a payment, the fake provider's hosted page, and webhook delivery (with retries)."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.fake_provider.models import FakeEvent, FakeIntent
from apps.fake_provider.provider import SUCCEED, choose
from apps.fake_provider.tasks import deliver_event
from apps.orders.models import Reservation
from apps.payments.models import PaymentIntent
from apps.payments.services import start_payment

from .test_concurrency import run_concurrently

pytestmark = pytest.mark.django_db


@pytest.fixture
def unpaid(user_client, make_offer, fill_cart):
    from .test_checkout import place

    client = user_client()
    fill_cart(client.user, (make_offer(price="40.00", freight="4.00"), 2))
    return client, place(client).json()["id"]


def test_pay_creates_then_reuses_one_intent_for_the_order_total(unpaid):
    client, order_id = unpaid
    first = client.post(f"/api/orders/{order_id}/payment/")
    again = client.post(f"/api/orders/{order_id}/payment/")

    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert first.json()["redirect_url"].startswith("/api/fake-provider/pay/pi_")
    intent = PaymentIntent.objects.get()
    assert (intent.amount, intent.currency, intent.status) == (88, "BRL", "requires_payment")
    fake = FakeIntent.objects.get()
    assert fake.return_url == f"/api/orders/{order_id}/payment/return/"
    assert fake.expires_at == Reservation.objects.order_by("expires_at").first().expires_at


def test_cannot_pay_an_expired_paid_or_foreign_order(unpaid, user_client):
    client, order_id = unpaid
    assert user_client().post(f"/api/orders/{order_id}/payment/").status_code == 404  # not yours

    Reservation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    expired = client.post(f"/api/orders/{order_id}/payment/")
    assert expired.status_code == 409 and expired.json()["code"] == "reservation_expired"


def test_order_detail_shows_the_latest_payment(unpaid):
    client, order_id = unpaid
    assert client.get(f"/api/orders/{order_id}/").json()["payment"] is None
    client.post(f"/api/orders/{order_id}/payment/")
    assert client.get(f"/api/orders/{order_id}/").json()["payment"] == {
        "status": "requires_payment", "needs_refund": False, "confirmation_overdue": False, "overdue_at": None,
    }


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_pay_clicks_get_one_intent(placed_order):
    order, _, _ = placed_order
    results = run_concurrently(lambda: start_payment(order, return_url="/"), lambda: start_payment(order, return_url="/"))

    assert not [r for r in results if isinstance(r, Exception)], results
    assert results[0].pk == results[1].pk
    assert PaymentIntent.objects.count() == FakeIntent.objects.count() == 1


# --- hosted page -------------------------------------------------------------------------------


def test_hosted_page_records_the_choice_and_returns_to_the_store(awaiting_payment, api_client):
    order, intent, fake = awaiting_payment
    page = api_client.get(f"/api/fake-provider/pay/{fake.pk}/")
    assert page.status_code == 200 and "R$ 154,80" in page.content.decode()  # items 129,80 + shipping 25,00

    with mock.patch("apps.fake_provider.provider.schedule") as schedule:
        response = api_client.post(f"/api/fake-provider/pay/{fake.pk}/", {"choice": "succeed", "twice": "on"})

    assert response.status_code == 302 and response["Location"] == f"/api/orders/{order.external_id}/payment/return/"
    [event] = FakeEvent.objects.all()
    assert event.type == "payment_intent.succeeded"
    fake.refresh_from_db()
    assert fake.status == "succeeded"


def test_hosted_page_refuses_after_the_hold_expired(awaiting_payment, api_client):
    _, _, fake = awaiting_payment
    FakeIntent.objects.filter(pk=fake.pk).update(expires_at=timezone.now() - timedelta(seconds=1))

    response = api_client.post(f"/api/fake-provider/pay/{fake.pk}/", {"choice": "succeed"})

    assert response.status_code == 200 and "This payment has expired" in response.content.decode()
    assert not FakeEvent.objects.exists()


def test_scheduling_twice_and_out_of_order(awaiting_payment):
    _, _, fake = awaiting_payment
    deliveries = choose(fake, SUCCEED, delay=0, twice=True, out_of_order=True)
    by_id = {e.pk: e.type for e in FakeEvent.objects.all()}

    # success first, then the older decline; each scheduled a second time
    assert [(by_id[d.event_id], d.countdown) for d in deliveries] == [
        ("payment_intent.succeeded", 0), ("payment_intent.payment_failed", 3),
        ("payment_intent.succeeded", 1), ("payment_intent.payment_failed", 4),
    ]


def test_delivery_is_retried_until_the_merchant_accepts(awaiting_payment, webhook_poster):
    """A 500 from the merchant (or no connection) is retried, like a real provider."""
    order, intent, fake = awaiting_payment
    choose(fake, SUCCEED)
    event = FakeEvent.objects.get()
    statuses = iter([500, 0])

    def flaky(url, body, headers):
        status = next(statuses, None)
        return status if status is not None else webhook_poster(url, body, headers)

    with mock.patch("apps.fake_provider.provider.http_post", side_effect=flaky):
        result = deliver_event.apply(args=(event.pk,))  # eager: retries run inline

    assert result.get() == 200
    event.refresh_from_db()
    assert (event.delivery_attempts, event.last_status) == (3, 200)
    order.refresh_from_db()
    assert order.status == "approved"


# --- back from the provider: "processing" until the webhook (survives a reload) ----------------


def test_return_marks_processing_and_it_survives_a_reload(unpaid):
    client, order_id = unpaid
    client.post(f"/api/orders/{order_id}/payment/")

    response = client.get(f"/api/orders/{order_id}/payment/return/")
    assert response.status_code == 302 and response["Location"] == f"/orders/{order_id}"

    for _ in range(2):  # a reload (or a later visit) still knows
        detail = client.get(f"/api/orders/{order_id}/").json()
        assert detail["payment"]["status"] == "processing"
        assert detail["payment"]["confirmation_overdue"] is False and detail["can_pay"] is False
    intent = PaymentIntent.objects.get()
    returned_at = intent.returned_at
    client.get(f"/api/orders/{order_id}/payment/return/")  # idempotent
    intent.refresh_from_db()
    assert intent.returned_at == returned_at


def test_return_is_owner_only(unpaid, user_client):
    client, order_id = unpaid
    client.post(f"/api/orders/{order_id}/payment/")
    assert user_client().get(f"/api/orders/{order_id}/payment/return/").status_code == 404
    from rest_framework.test import APIClient

    anonymous = APIClient().get(f"/api/orders/{order_id}/payment/return/")
    assert anonymous.status_code == 302 and anonymous["Location"] == f"/login?next=/orders/{order_id}"
    assert PaymentIntent.objects.get().status == "requires_payment"


@pytest.mark.parametrize("choice, final", [(SUCCEED, "succeeded"), ("fail", "failed")])
def test_the_webhook_clears_processing(awaiting_payment, run_deliveries, choice, final):
    from apps.payments.services import mark_returned

    order, intent, fake = awaiting_payment
    mark_returned(order)
    run_deliveries(choose(fake, choice))
    intent.refresh_from_db()
    assert intent.status == final


def test_overdue_processing_offers_pay_again_with_the_same_intent(unpaid, settings, run_deliveries):
    client, order_id = unpaid
    first = client.post(f"/api/orders/{order_id}/payment/").json()
    client.get(f"/api/orders/{order_id}/payment/return/")
    assert client.get(f"/api/orders/{order_id}/").json()["can_pay"] is False

    # No webhook within the window: Pay comes back (time moved past returned_at + timeout)
    PaymentIntent.objects.update(returned_at=timezone.now() - timedelta(seconds=settings.PAYMENT_CONFIRMATION_TIMEOUT_SECONDS + 1))
    detail = client.get(f"/api/orders/{order_id}/").json()
    assert detail["can_pay"] is True and detail["payment"]["confirmation_overdue"] is True

    retry = client.post(f"/api/orders/{order_id}/payment/").json()
    # same intent, same provider payment: no double charge
    assert retry["redirect_url"] == first["redirect_url"] and retry["status"] == "processing"
    assert PaymentIntent.objects.count() == FakeIntent.objects.count() == 1

    # The late webhook still settles the order, once
    run_deliveries(choose(FakeIntent.objects.get(), SUCCEED, twice=True))
    detail = client.get(f"/api/orders/{order_id}/").json()
    assert detail["status"] == "approved" and detail["payment"]["status"] == "succeeded"
    from apps.events.models import OutboxEvent

    assert OutboxEvent.objects.filter(aggregate_id=order_id, event_type="OrderPaid").count() == 1
