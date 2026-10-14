from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Offer, Product
from apps.core.models import IdempotencyKey
from apps.orders.models import Order, OrderItem, Payment, Reservation

from .conftest import ADDRESS

pytestmark = pytest.mark.django_db


def place(client, key="key-00000001", shipping=None):
    return client.post(
        "/api/checkout/", {"shipping": shipping or ADDRESS}, format="json", HTTP_IDEMPOTENCY_KEY=key
    )


def test_checkout_creates_order_reserves_and_empties_cart(user_client, make_offer, fill_cart):
    client = user_client()
    a = make_offer(stock=5, price="10.00", freight="2.00")
    b = make_offer(stock=3, price="25.50", freight="5.25")
    fill_cart(client.user, (a, 2), (b, 1))

    response = place(client)
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["status"] == "created" and len(data["id"]) == 32
    assert (data["item_count"], data["items_total"], data["freight_total"], data["total"]) == (3, "45.50", "9.25", "54.75")
    assert [(l["quantity"], l["line_total"]) for l in data["lines"]] == [(2, "20.00"), (1, "25.50")]
    assert data["shipping"]["zip_code"] == "01310-100"
    assert data["can_pay"] and data["can_cancel"] and data["payments_enabled"]
    assert [h["to_status"] for h in data["status_history"]] == ["created"]

    a.refresh_from_db(); b.refresh_from_db()
    assert (a.stock, b.stock) == (3, 2)
    order = Order.objects.get(external_id=data["id"])
    assert OrderItem.objects.filter(order=order).count() == 3  # one row per unit, like Olist
    reservations = {r.offer_id: r for r in order.reservations.all()}
    assert {k: (r.quantity, r.status) for k, r in reservations.items()} == {a.id: (2, "active"), b.id: (1, "active")}
    assert abs(reservations[a.id].expires_at - (timezone.now() + timedelta(minutes=15))) < timedelta(seconds=30)
    assert client.get("/api/cart/").json()["lines"] == []
    assert order.customer.user == client.user


def test_out_of_stock_lists_every_problem_line_and_changes_nothing(user_client, make_offer, fill_cart):
    client = user_client()
    ok, short, gone = make_offer(stock=5), make_offer(stock=1), make_offer(stock=0)
    fill_cart(client.user, (ok, 1), (short, 2), (gone, 1))

    response = place(client)
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "out_of_stock"
    assert {(l["offer_id"], l["requested"], l["available"]) for l in body["lines"]} == {
        (short.id, 2, 1), (gone.id, 1, 0)
    }
    assert Order.objects.count() == 0 and Reservation.objects.count() == 0
    assert [o.stock for o in Offer.objects.order_by("id")] == [5, 1, 0]
    assert IdempotencyKey.objects.count() == 0  # failures aren't stored: a retry runs again
    assert len(client.get("/api/cart/").json()["lines"]) == 3


def test_empty_cart_and_missing_key(user_client):
    client = user_client()
    assert place(client).json()["code"] == "empty_cart"
    response = client.post("/api/checkout/", {"shipping": ADDRESS}, format="json")
    assert response.status_code == 400 and "idempotency_key" in response.json()


def test_address_validation(user_client, make_offer, fill_cart):
    client = user_client()
    fill_cart(client.user, (make_offer(), 1))
    response = place(client, shipping={**ADDRESS, "state": "XX", "zip_code": "123"})
    assert response.status_code == 400
    assert set(response.json()["shipping"]) == {"state", "zip_code"}


# --- idempotency -------------------------------------------------------------------------------


def test_same_key_replays_the_same_order(user_client, make_offer, fill_cart):
    client = user_client()
    fill_cart(client.user, (make_offer(stock=5), 1))
    first = place(client, "retry-key-1")
    second = place(client, "retry-key-1")  # cart is empty now: only a replay can succeed
    assert (first.status_code, second.status_code) == (201, 201)
    assert second.json()["id"] == first.json()["id"]
    assert second["Idempotent-Replayed"] == "true"
    assert Order.objects.count() == 1


def test_same_key_different_body_is_409(user_client, make_offer, fill_cart):
    client = user_client()
    fill_cart(client.user, (make_offer(), 1))
    place(client, "retry-key-2")
    response = place(client, "retry-key-2", shipping={**ADDRESS, "city": "Campinas"})
    assert response.status_code == 409 and response.json()["code"] == "idempotency_conflict"


def test_keys_are_scoped_per_user(user_client, make_offer, fill_cart):
    alice, bob = user_client(), user_client()
    fill_cart(alice.user, (make_offer(), 1))
    fill_cart(bob.user, (make_offer(), 1))
    assert place(alice, "shared-uuid-key").status_code == 201
    assert place(bob, "shared-uuid-key").status_code == 201
    assert Order.objects.count() == 2


def test_expired_key_is_treated_as_new(user_client, make_offer, fill_cart):
    client = user_client()
    fill_cart(client.user, (make_offer(stock=5), 1))
    place(client, "old-key-0001")
    IdempotencyKey.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    fill_cart(client.user, (make_offer(stock=5), 1))
    assert place(client, "old-key-0001").status_code == 201
    assert Order.objects.count() == 2


# --- snapshots, stats, ownership --------------------------------------------------------------


def test_price_and_freight_are_snapshotted(user_client, make_offer, fill_cart):
    client = user_client()
    offer = make_offer(price="50.00", freight="5.00")
    fill_cart(client.user, (offer, 2))
    order_id = place(client).json()["id"]
    Offer.objects.filter(pk=offer.pk).update(price=Decimal("999.00"), freight=Decimal("99.00"))

    data = client.get(f"/api/orders/{order_id}/").json()
    assert (data["items_total"], data["freight_total"], data["total"]) == ("100.00", "10.00", "110.00")


def test_min_price_updates_when_last_unit_is_reserved(
    user_client, make_offer, fill_cart, django_capture_on_commit_callbacks
):
    cheap = make_offer(stock=1, price="10.00")
    pricier = make_offer(stock=4, price="30.00", product=cheap.product)
    Product.objects.filter(pk=cheap.product_id).update(min_price=Decimal("10.00"))
    client = user_client()
    fill_cart(client.user, (cheap, 1))

    with django_capture_on_commit_callbacks(execute=True):
        order_id = place(client).json()["id"]
    assert Product.objects.get(pk=cheap.product_id).min_price == Decimal("30.00")

    with django_capture_on_commit_callbacks(execute=True):
        client.post(f"/api/orders/{order_id}/cancel/")
    assert Product.objects.get(pk=cheap.product_id).min_price == Decimal("10.00")
    assert pricier.product_id == cheap.product_id


def test_orders_are_private(user_client, make_offer, fill_cart):
    owner, other = user_client(), user_client()
    fill_cart(owner.user, (make_offer(), 1))
    order_id = place(owner).json()["id"]
    assert other.get(f"/api/orders/{order_id}/").status_code == 404
    assert other.post(f"/api/orders/{order_id}/pay/", {"outcome": "success"}, format="json").status_code == 404
    assert other.post(f"/api/orders/{order_id}/cancel/").status_code == 404
    assert other.get("/api/orders/").json()["count"] == 0


def test_order_list_newest_first_with_totals(user_client, make_offer, fill_cart, django_assert_max_num_queries):
    client = user_client()
    for i in range(3):
        fill_cart(client.user, (make_offer(price="10.00", freight="1.00"), i + 1))
        place(client, f"list-key-{i:04d}")
    with django_assert_max_num_queries(4):  # session, user, count, page
        data = client.get("/api/orders/").json()
    assert data["count"] == 3
    assert [o["item_count"] for o in data["results"]] == [3, 2, 1]
    assert data["results"][0]["total"] == "33.00"
    assert data["results"][0]["reservation_expires_at"]


def test_order_detail_query_count(user_client, make_offer, fill_cart, django_assert_max_num_queries):
    client = user_client()
    fill_cart(client.user, *((make_offer(), 2) for _ in range(4)))
    order_id = place(client).json()["id"]
    with django_assert_max_num_queries(5):  # session, user, order+totals, items(+joins), history
        client.get(f"/api/orders/{order_id}/")


# --- pay / cancel ------------------------------------------------------------------------------


@pytest.fixture
def placed(user_client, make_offer, fill_cart):
    client = user_client()
    offer = make_offer(stock=5, price="40.00", freight="4.00")
    fill_cart(client.user, (offer, 2))
    order_id = place(client).json()["id"]
    return client, offer, order_id


def test_pay_success_commits_and_approves(placed):
    client, offer, order_id = placed
    response = client.post(f"/api/orders/{order_id}/pay/", {"outcome": "success"}, format="json")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved" and not data["can_pay"] and not data["can_cancel"]
    assert [h["reason"] for h in data["status_history"]] == ["checkout", "payment_succeeded"]
    order = Order.objects.get(external_id=order_id)
    assert set(order.reservations.values_list("status", flat=True)) == {"committed"}
    assert Payment.objects.get(order=order).value == Decimal("88.00")
    offer.refresh_from_db()
    assert offer.stock == 3  # stays sold

    again = client.post(f"/api/orders/{order_id}/pay/", {"outcome": "success"}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "invalid_transition"


def test_pay_fail_releases_and_cancels(placed):
    client, offer, order_id = placed
    data = client.post(f"/api/orders/{order_id}/pay/", {"outcome": "fail"}, format="json").json()
    assert data["status"] == "canceled"
    assert data["status_history"][-1]["reason"] == "payment_failed"
    offer.refresh_from_db()
    assert offer.stock == 5


def test_pay_after_expiry_is_409_and_cancels(placed):
    client, offer, order_id = placed
    Reservation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    response = client.post(f"/api/orders/{order_id}/pay/", {"outcome": "success"}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "reservation_expired"
    order = Order.objects.get(external_id=order_id)
    assert order.status == "canceled"  # committed even though the request "failed"
    assert order.status_history.last().reason == "reservation_expired"
    offer.refresh_from_db()
    assert offer.stock == 5


def test_customer_cancel(placed):
    client, offer, order_id = placed
    data = client.post(f"/api/orders/{order_id}/cancel/").json()
    assert data["status"] == "canceled" and data["status_history"][-1]["reason"] == "customer_canceled"
    offer.refresh_from_db()
    assert offer.stock == 5
    # cancelling again (or cancelling a paid order) is a 409, stock untouched
    assert client.post(f"/api/orders/{order_id}/cancel/").status_code == 409
    offer.refresh_from_db()
    assert offer.stock == 5


def test_fake_payments_can_be_disabled(placed, settings):
    client, _, order_id = placed
    settings.ALLOW_FAKE_PAYMENTS = False
    assert client.post(f"/api/orders/{order_id}/pay/", {"outcome": "success"}, format="json").status_code == 404
    assert client.get(f"/api/orders/{order_id}/").json()["payments_enabled"] is False


# --- expiry sweeper ----------------------------------------------------------------------------


def test_sweeper_releases_expired_orders_once(placed):
    from apps.orders.services import release_expired

    _, offer, order_id = placed
    later = timezone.now() + timedelta(minutes=16)
    assert release_expired(now=timezone.now()) == 0  # not expired yet
    assert release_expired(now=later) == 1

    order = Order.objects.get(external_id=order_id)
    assert order.status == "canceled"
    history = list(order.status_history.values_list("from_status", "to_status", "reason"))
    assert history[-1] == ("created", "canceled", "reservation_expired")
    offer.refresh_from_db()
    assert offer.stock == 5
    assert set(order.reservations.values_list("status", flat=True)) == {"released"}

    assert release_expired(now=later) == 0  # second run changes nothing
    offer.refresh_from_db()
    assert offer.stock == 5 and order.status_history.count() == 2


def test_sweeper_ignores_paid_orders(placed):
    from apps.orders.services import release_expired

    client, offer, order_id = placed
    client.post(f"/api/orders/{order_id}/pay/", {"outcome": "success"}, format="json")
    assert release_expired(now=timezone.now() + timedelta(days=1)) == 0
    offer.refresh_from_db()
    assert offer.stock == 3


def test_stock_check_constraint_blocks_negative_stock(make_offer):
    from django.db import IntegrityError, transaction

    offer = make_offer(stock=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Offer.objects.filter(pk=offer.pk).update(stock=-1)
