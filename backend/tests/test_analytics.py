"""7b: analytics projections (consumer + backfill), exact decimals, sources, and the staff API."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.analytics.models import CategorySales, DailySales, DeliveryStats, StateSales
from apps.analytics.projections import local_day, rebuild, recompute_days
from apps.events.consumers.analytics import AnalyticsConsumer
from apps.events.relay import publish_batch
from apps.orders.models import Order
from apps.orders.services import cancel, checkout, pay

from .test_concurrency import run_concurrently

pytestmark = pytest.mark.django_db

PAID = {"approved", "invoiced", "processing", "shipped", "delivered"}
CANCELED = {"canceled", "unavailable"}


def consume(events_redis):
    consumer = AnalyticsConsumer(events_redis, consumer_name="t1")
    consumer.ensure_groups()
    publish_batch(events_redis)
    consumer.run_once(claim=False)


def daily(source, day):
    return DailySales.objects.filter(source=source, day=day).values(
        "orders", "canceled_orders", "paid_orders", "gmv", "items"
    ).first()


# --- the consumer keeps the right rows current ---------------------------------------------------


def test_order_events_update_their_days_rows(events_redis, placed_order):
    order, user, (a, b) = placed_order
    today = local_day(order.purchased_at)
    consume(events_redis)
    # Placed but unpaid: counted as an order, not as revenue
    assert daily("app", today) == {"orders": 1, "canceled_orders": 0, "paid_orders": 0, "gmv": Decimal("0.00"), "items": 0}
    assert not CategorySales.objects.exists()

    pay(order.pk, "success")
    consume(events_redis)
    assert daily("app", today) == {
        "orders": 1, "canceled_orders": 0, "paid_orders": 1, "gmv": Decimal("154.80"), "items": 3,
    }
    # Category revenue = item prices only (freight isn't per category)
    assert {(c.category_id, c.revenue, c.units) for c in CategorySales.objects.all()} == {
        (a.product.category_id, Decimal("129.80"), 3),
    }
    [state] = StateSales.objects.all()
    assert (state.state, state.orders, state.gmv) == ("SP", 1, Decimal("154.80"))  # the shipping state
    assert not DailySales.objects.exclude(source="app").exists()  # other sources untouched


def test_created_and_canceled_orders_count_as_orders_but_not_revenue(events_redis, make_user, make_offer, fill_cart, address):
    buyer = make_user()
    fill_cart(buyer, (make_offer(price="50.00", freight="5.00"), 1))
    unpaid = checkout(buyer, address)
    fill_cart(buyer, (make_offer(price="70.00", freight="0.00"), 1))
    canceled = checkout(buyer, address)
    cancel(canceled.pk)
    fill_cart(buyer, (make_offer(price="10.00", freight="1.00"), 2))
    paid = checkout(buyer, address)
    pay(paid.pk, "success")
    consume(events_redis)

    row = daily("app", local_day(unpaid.purchased_at))
    assert row == {"orders": 3, "canceled_orders": 1, "paid_orders": 1, "gmv": Decimal("22.00"), "items": 2}


def test_days_are_sao_paulo_purchase_days(events_redis, placed_order):
    order, _, _ = placed_order
    # 02:30 UTC on the 5th is 23:30 on the 4th in Sao Paulo (UTC-3)
    Order.objects.filter(pk=order.pk).update(purchased_at=datetime(2026, 11, 5, 2, 30, tzinfo=UTC))
    recompute_days([date(2026, 11, 4)], "app")
    assert daily("app", date(2026, 11, 4))["orders"] == 1
    assert daily("app", date(2026, 11, 5)) is None


# --- backfill = direct computation ---------------------------------------------------------------


def direct(source):
    """The same metrics computed in Python straight from the orders."""
    sales = defaultdict(lambda: {"orders": 0, "canceled_orders": 0, "paid_orders": 0, "gmv": Decimal("0.00"), "items": 0})
    categories = defaultdict(lambda: [Decimal("0.00"), 0])
    states = defaultdict(lambda: [0, Decimal("0.00")])
    deliveries = defaultdict(lambda: [0, 0, 0])
    for order in Order.objects.filter(source=source).select_related("customer").prefetch_related("items__product"):
        day = local_day(order.purchased_at)
        items = list(order.items.all())
        total = sum((i.price + i.freight_value for i in items), Decimal("0.00"))
        row = sales[day]
        row["orders"] += 1
        row["canceled_orders"] += order.status in CANCELED
        state = states[(day, order.shipping_state or order.customer.state)]
        state[0] += 1
        if order.status in PAID:
            row["paid_orders"] += 1
            row["gmv"] += total
            row["items"] += len(items)
            state[1] += total
            for item in items:
                categories[(day, item.product.category_id)][0] += item.price
                categories[(day, item.product.category_id)][1] += 1
        if order.status == "delivered" and order.delivered_customer_at:
            d = deliveries[day]
            d[0] += 1
            d[1] += int((order.delivered_customer_at - order.purchased_at).total_seconds())
            d[2] += local_day(order.delivered_customer_at) > order.estimated_delivery_date
    return sales, categories, states, deliveries


def test_backfill_matches_a_direct_computation(olist_dir, events_redis, placed_order):
    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=StringIO())
    order, _, _ = placed_order
    pay(order.pk, "success")
    out = StringIO()
    call_command("backfill_analytics", stdout=out)
    assert "olist" in out.getvalue()

    for source in ("olist", "app"):
        sales, categories, states, deliveries = direct(source)
        assert {
            r.day: {"orders": r.orders, "canceled_orders": r.canceled_orders, "paid_orders": r.paid_orders, "gmv": r.gmv, "items": r.items}
            for r in DailySales.objects.filter(source=source)
        } == dict(sales)
        assert {(r.day, r.category_id): [r.revenue, r.units] for r in CategorySales.objects.filter(source=source)} == dict(categories)
        assert {(r.day, r.state): [r.orders, r.gmv] for r in StateSales.objects.filter(source=source)} == dict(states)
        # seconds are truncated per order in Python and summed exactly in SQL: allow < 1 s per order
        db_deliveries = {r.day: [r.delivered, r.delivery_seconds_total, r.late] for r in DeliveryStats.objects.filter(source=source)}
        assert db_deliveries.keys() == deliveries.keys()
        for day, (count, seconds, late) in deliveries.items():
            assert db_deliveries[day][0] == count and db_deliveries[day][2] == late
            assert abs(db_deliveries[day][1] - seconds) <= count
    assert DailySales.objects.filter(source="olist").exists() and DeliveryStats.objects.filter(source="olist").exists()

    # Re-running changes nothing (and a rebuild removes rows of days that no longer have orders)
    before = list(DailySales.objects.order_by("day", "source").values_list("day", "source", "orders", "gmv"))
    rebuild("olist")
    assert list(DailySales.objects.order_by("day", "source").values_list("day", "source", "orders", "gmv")) == before


# --- concurrency -----------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_concurrent_recomputes_of_the_same_day_queue_instead_of_double_inserting(placed_order):
    order, _, _ = placed_order
    pay(order.pk, "success")
    day = local_day(order.purchased_at)
    recompute_days([day], "app")
    expected = daily("app", day)

    for _ in range(5):
        results = run_concurrently(lambda: recompute_days([day], "app"), lambda: recompute_days([day - timedelta(days=1), day], "app"))
        assert results == [None, None], results  # no IntegrityError, no deadlock
        assert daily("app", day) == expected
        assert DailySales.objects.filter(source="app", day=day).count() == 1


# --- staff API ------------------------------------------------------------------------------------


@pytest.fixture
def staff_client(make_user):
    from rest_framework.test import APIClient

    user = make_user()
    user.is_staff = True
    user.save()
    client = APIClient()
    client.force_login(user)
    return client


def test_dashboard_is_staff_only(user_client):
    from rest_framework.test import APIClient

    assert APIClient().get("/api/staff/analytics/").status_code == 404
    assert user_client().get("/api/staff/analytics/").status_code == 404


def test_dashboard_kpis_are_exact_and_filter_by_source_and_date(staff_client, make_user, make_offer, fill_cart, address):
    buyer = make_user()
    for _ in range(3):  # 3 paid orders of 33.33 + 0.01 freight = 100.02 total
        fill_cart(buyer, (make_offer(price="33.33", freight="0.01"), 1))
        pay(checkout(buyer, address).pk, "success")
    fill_cart(buyer, (make_offer(price="5.00", freight="0.00"), 1))
    cancel(checkout(buyer, address).pk)
    rebuild("app")
    DailySales.objects.create(day=date(2017, 11, 24), source="olist", orders=7, canceled_orders=0, paid_orders=7,
                              gmv=Decimal("700.00"), items=7)

    app = staff_client.get("/api/staff/analytics/", {"source": "app"}).json()
    assert app["kpis"]["orders"] == 4 and app["kpis"]["canceled_orders"] == 1 and app["kpis"]["cancel_rate"] == 0.25
    assert app["kpis"]["gmv"] == "100.02" and app["kpis"]["aov"] == "33.34"  # 100.02 / 3, rounded half up
    assert [s["state"] for s in app["by_state"]] == ["SP"]

    everything = staff_client.get("/api/staff/analytics/").json()
    assert everything["kpis"]["orders"] == 11 and everything["first_day"] == "2017-11-24"
    olist_day = staff_client.get("/api/staff/analytics/", {"source": "all", "date_from": "2017-11-24", "date_to": "2017-11-24"}).json()
    assert olist_day["kpis"]["gmv"] == "700.00" and len(olist_day["daily"]) == 1
    bad = staff_client.get("/api/staff/analytics/", {"date_from": "2018-01-02", "date_to": "2018-01-01"})
    assert bad.status_code == 400
    assert staff_client.get("/api/staff/analytics/", {"source": "nope"}).status_code == 400
