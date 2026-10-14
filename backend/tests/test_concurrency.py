"""Real concurrency: separate threads, separate DB connections, committed transactions.

transaction=True makes pytest-django truncate tables after each test instead of wrapping it in
a transaction, which is what lets other connections see the committed rows.
"""

import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Offer, Product
from apps.catalog.stats import refresh_product_stats
from apps.core.errors import OutOfStock
from apps.orders.models import Order, Reservation
from apps.orders.services import checkout, release_expired

from .conftest import ADDRESS

pytestmark = pytest.mark.django_db(transaction=True)


def run_concurrently(*functions):
    """Start every function at the same moment (barrier) in its own thread; return results.

    Each result is the return value or the raised exception. Threads close their DB connection.
    """
    barrier = threading.Barrier(len(functions))
    results = [None] * len(functions)

    def worker(index, fn):
        try:
            barrier.wait()
            results[index] = fn()
        except Exception as exc:  # noqa: BLE001 - surfaced to the test
            results[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, fn)) for i, fn in enumerate(functions)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a thread hung (deadlock?)"
    return results


def test_two_buyers_one_last_unit(make_user, make_offer, fill_cart, address):
    for _ in range(5):  # a few rounds to give the race every chance
        offer = make_offer(stock=1)
        alice, bob = make_user(), make_user()
        fill_cart(alice, (offer, 1))
        fill_cart(bob, (offer, 1))

        results = run_concurrently(lambda: checkout(alice, address), lambda: checkout(bob, address))

        orders = [r for r in results if isinstance(r, Order)]
        errors = [r for r in results if isinstance(r, OutOfStock)]
        assert (len(orders), len(errors)) == (1, 1), results
        assert errors[0].extra["lines"][0]["available"] == 0
        offer.refresh_from_db()
        assert offer.stock == 0
        assert Reservation.objects.filter(offer=offer).count() == 1


def test_opposite_cart_order_does_not_deadlock(make_user, make_offer, fill_cart, address):
    a, b = make_offer(stock=100), make_offer(stock=100)
    alice, bob = make_user(), make_user()
    for _ in range(10):
        fill_cart(alice, (a, 1), (b, 1))  # A then B
        fill_cart(bob, (b, 1), (a, 1))  # B then A
        results = run_concurrently(lambda: checkout(alice, address), lambda: checkout(bob, address))
        assert all(isinstance(r, Order) for r in results), results
    a.refresh_from_db(); b.refresh_from_db()
    assert (a.stock, b.stock) == (80, 80)


def test_concurrent_retries_with_the_same_key_create_one_order(make_user, make_offer, fill_cart):
    user = make_user()
    fill_cart(user, (make_offer(stock=5), 2))

    def place():
        client = APIClient()
        client.force_login(user)
        return client.post("/api/checkout/", {"shipping": ADDRESS}, format="json", HTTP_IDEMPOTENCY_KEY="same-key-xyz")

    first, second = run_concurrently(place, place)
    assert (first.status_code, second.status_code) == (201, 201), (first.content, second.content)
    assert first.json()["id"] == second.json()["id"]
    assert Order.objects.count() == 1


def test_concurrent_sweepers_release_each_order_once(make_user, make_offer, fill_cart, address):
    offer = make_offer(stock=10)
    for _ in range(5):
        user = make_user()
        fill_cart(user, (offer, 2))
        checkout(user, address)
    offer.refresh_from_db()
    assert offer.stock == 0

    later = timezone.now() + timedelta(minutes=16)
    results = run_concurrently(lambda: release_expired(now=later), lambda: release_expired(now=later))

    assert sum(results) == 5, results  # each order released by exactly one sweeper
    offer.refresh_from_db()
    assert offer.stock == 10
    assert set(Order.objects.values_list("status", flat=True)) == {"canceled"}
    assert Reservation.objects.filter(status="released").count() == 5


def test_concurrent_stats_refreshes_over_overlapping_products(make_offer):
    offers = [make_offer(stock=3, price=f"{10 * (i + 1)}.00") for i in range(3)]
    ids = [o.product_id for o in offers]
    for _ in range(10):
        results = run_concurrently(
            lambda: refresh_product_stats(ids), lambda: refresh_product_stats(list(reversed(ids)))
        )
        assert not any(isinstance(r, Exception) for r in results), results
    assert [Product.objects.get(pk=pk).min_price for pk in ids] == [
        Decimal("10.00"), Decimal("20.00"), Decimal("30.00")
    ]
    Offer.objects.filter(pk=offers[0].pk).update(stock=0)
    refresh_product_stats([ids[0]])
    assert Product.objects.get(pk=ids[0]).min_price is None
