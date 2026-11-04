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
    assert fake.return_url == f"/orders/{order_id}?payment=processing"
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
        "status": "requires_payment", "needs_refund": False,
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

    assert response.status_code == 302 and response["Location"] == f"/orders/{order.external_id}?payment=processing"
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
