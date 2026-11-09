"""7c: historical replay through the real order lifecycle (apps/replay)."""

import importlib
import threading
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.forms.models import model_to_dict
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.analytics.models import CategorySales, DailySales, DeliveryStats, StateSales
from apps.catalog.models import Offer, Product
from apps.catalog.stats import refresh_offers_and_stats
from apps.core.errors import InvalidTransition
from apps.events.consumers import (
    AnalyticsConsumer,
    EventLogConsumer,
    NotificationsConsumer,
    OrderLiveConsumer,
    ProductStatsConsumer,
)
from apps.events.models import EventLog, OutboxEvent, ProcessedEvent
from apps.events.relay import publish_batch
from apps.notifications.models import Notification
from apps.orders import events as order_events
from apps.orders.models import Order, OrderItem, OrderStatusHistory, Payment, Reservation
from apps.orders.services import (
    cancel_paid,
    checkout,
    deliver,
    invoice,
    mark_unavailable,
    pay,
    release_expired,
    ship,
)
from apps.replay import services
from apps.replay.models import ReplayRun

from .test_concurrency import run_concurrently

pytestmark = pytest.mark.django_db

ORDER_CONSUMERS = (EventLogConsumer, AnalyticsConsumer, ProductStatsConsumer, NotificationsConsumer, OrderLiveConsumer)
ALL_DAYS = {"date_from": "2016-01-01", "date_to": "2018-12-31"}


@pytest.fixture
def imported(olist_dir):
    """The fixture import (7 orders: delivered, an unpaid canceled one, a shipped one), turned
    into every history the replay handles: o5 unavailable, o7 canceled after shipping, o8
    processing."""
    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=StringIO())
    o = {order.external_id[-2:]: order for order in Order.objects.filter(source="olist")}
    Order.objects.filter(pk=o["o5"].pk).update(status="unavailable", delivered_carrier_at=None, delivered_customer_at=None)
    Order.objects.filter(pk=o["o7"].pk).update(status="canceled", delivered_customer_at=None)  # had shipped
    Order.objects.filter(pk=o["o8"].pk).update(status="processing", delivered_carrier_at=None, delivered_customer_at=None)
    refresh_offers_and_stats()  # a bulk change to imported data needs a stats refresh (data rules)
    return {key: Order.objects.get(pk=order.pk) for key, order in o.items()}


def replay(*, date_from=ALL_DAYS["date_from"], date_to=ALL_DAYS["date_to"], speed=0, dry_run=False):
    out = StringIO()
    argv = ["--from", date_from, "--to", date_to, "--speed", str(speed)] + (["--dry-run"] if dry_run else [])
    call_command("replay_orders", *argv, stdout=out)
    return out.getvalue()


def drain(client):
    consumers = [cls(client, consumer_name="t1") for cls in ORDER_CONSUMERS]
    for consumer in consumers:
        consumer.ensure_groups()
    while publish_batch(client).published:
        pass
    for consumer in consumers:
        while consumer.run_once(claim=False, block_ms=10):
            pass


def copies():
    return Order.objects.filter(source="replay")


def replay_events(event_type=None):
    qs = OutboxEvent.objects.filter(aggregate_id__in=copies().values("external_id"))
    return qs.filter(event_type=event_type) if event_type else qs


EXPECTED_TYPES = {
    "o1": ["OrderPlaced", "OrderPaid", "OrderInvoiced", "OrderShipped", "OrderDelivered"],
    "o3": ["OrderPlaced", "OrderCanceled"],  # canceled before payment
    "o4": ["OrderPlaced", "OrderPaid", "OrderInvoiced", "OrderShipped"],  # still in transit
    "o5": ["OrderPlaced", "OrderPaid", "OrderUnavailable"],
    "o7": ["OrderPlaced", "OrderPaid", "OrderCanceled"],  # canceled after shipping -> after approval
    "o8": ["OrderPlaced", "OrderPaid"],  # processing stays approved
}


# --- the lifecycle -------------------------------------------------------------------------------


def test_replay_reenacts_each_history_as_events_in_timestamp_order(imported):
    out = replay()
    assert "7 orders, 24 steps/events" in out and "completed: 7 orders created, 24 steps applied" in out
    assert "1 order(s) canceled after shipping" in out

    by_source = {c.replay_of.external_id[-2:]: c for c in copies().select_related("replay_of", "replay_run")}
    assert len(by_source) == 7
    for key, expected in EXPECTED_TYPES.items():
        copy = by_source[key]
        events = OutboxEvent.objects.filter(aggregate_id=copy.external_id).order_by("occurred_at", "id")
        assert [e.event_type for e in events] == expected, key
        assert all(e.payload["order_source"] == "replay" and e.payload["replay_run"] == copy.replay_run_id for e in events)

    # Final statuses follow Olist (processing -> approved); historical timestamps are copied
    statuses = {key: c.status for key, c in by_source.items()}
    assert statuses == {"o1": "delivered", "o2": "delivered", "o3": "canceled", "o4": "shipped", "o5": "unavailable",
                        "o7": "canceled", "o8": "approved"}
    src, copy = imported["o1"], by_source["o1"]
    assert (copy.purchased_at, copy.approved_at, copy.delivered_carrier_at, copy.delivered_customer_at) == (
        src.purchased_at, src.approved_at, src.delivered_carrier_at, src.delivered_customer_at)
    assert copy.customer.user.email == "replay@example.com"
    assert copy.shipping_state == src.customer.state and copy.estimated_delivery_date == src.estimated_delivery_date
    assert list(copy.items.values_list("product_id", "price")) == list(src.items.values_list("product_id", "price"))
    assert Payment.objects.filter(order=copy).get().value == sum(i.price + i.freight_value for i in src.items.all())

    # The whole stream is in simulated-time order (steps of all orders merged on one clock)
    simulated = [e.payload["occurred_at"] for e in replay_events().order_by("occurred_at", "id")]
    assert simulated == sorted(simulated)


def history_and_event_times(order):
    history = list(order.status_history.order_by("created_at", "id").values_list("occurred_at", flat=True))
    events = OutboxEvent.objects.filter(aggregate_id=order.external_id).order_by("occurred_at", "id")
    return history, [parse_datetime(e.payload["occurred_at"]) for e in events]


def test_history_carries_the_historical_time_of_each_step(imported, user_client):
    replay()
    copy = copies().get(replay_of=imported["o1"])
    src = imported["o1"]
    history, event_times = history_and_event_times(copy)
    # One story: each history row's occurred_at is its event's occurred_at, i.e. Olist's time
    assert history == event_times
    assert (history[0], history[1], history[3], history[4]) == (
        src.purchased_at, src.approved_at, src.delivered_carrier_at, src.delivered_customer_at)
    assert history[-1] < timezone.now() - timedelta(days=365)
    # ... and the API serves it next to the recording time
    detail = user_client(copy.customer.user).get(f"/api/orders/{copy.external_id}/").json()
    first = detail["status_history"][0]
    assert parse_datetime(first["occurred_at"]) == src.purchased_at
    assert parse_datetime(first["created_at"]) > timezone.now() - timedelta(hours=1)


def test_app_order_history_occurred_at_is_its_recording_time(placed_order):
    order, _, _ = placed_order
    pay(order.pk, "success")
    order.refresh_from_db()
    history, event_times = history_and_event_times(order)
    # Same value as the payload's (JSON keeps milliseconds)
    assert len(history) == len(event_times) == 2
    assert all(abs(h - e) < timedelta(milliseconds=1) for h, e in zip(history, event_times))
    for row in order.status_history.all():
        assert abs(row.occurred_at - row.created_at) < timedelta(seconds=1)


def test_history_backfill_recovers_replay_times_from_the_event_log(imported, events_redis, placed_order):
    """orders/0008: replay rows take their logged event's payload time, the rest created_at."""
    from django.db import connection

    backfill = importlib.import_module("apps.orders.migrations.0008_backfill_history_occurred_at").backfill
    replay(date_from="2017-10-01", date_to="2018-01-31")  # o1, o2
    drain(events_redis)  # EventLog rows
    copy = copies().get(replay_of=imported["o1"])
    expected, _ = history_and_event_times(copy)
    app_rows = OrderStatusHistory.objects.exclude(order__source="replay")
    assert app_rows.exists()
    with connection.cursor() as cursor:  # back to the pre-migration state (rolled back with the test)
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # no pending FK checks, or ALTER TABLE refuses
        cursor.execute("ALTER TABLE orders_orderstatushistory ALTER occurred_at DROP NOT NULL")
        cursor.execute("UPDATE orders_orderstatushistory SET occurred_at = NULL")
    with connection.schema_editor() as editor:
        backfill(None, editor)
    assert history_and_event_times(copy)[0] == expected
    assert not OrderStatusHistory.objects.filter(occurred_at__isnull=True).exists()
    assert all(r.occurred_at == r.created_at for r in app_rows)


def test_consumers_process_replay_events_without_touching_the_shop(imported, events_redis):
    replay(date_from="2017-10-01", date_to="2018-01-31")  # o1, o2
    drain(events_redis)
    events = replay_events()
    assert events.count() == 10
    assert EventLog.objects.filter(event_id__in=events.values("id")).count() == 10
    for name in ("event_log", "analytics", "order_live", "product_stats"):
        assert ProcessedEvent.objects.filter(consumer=name, event_id__in=events.values("id")).count() == 10, name
    # notifications subscribes to its email kinds only: OrderPlaced + OrderPaid here
    assert ProcessedEvent.objects.filter(consumer="notifications", event_id__in=events.values("id")).count() == 4
    # product_stats skipped them (no recompute, no cache invalidation); no emails
    assert not OutboxEvent.objects.filter(event_type="ProductsChanged").exists()
    assert not Notification.objects.exists()
    # analytics has the replay source on the historical purchase days
    assert DailySales.objects.filter(source="replay").count() == 2
    assert sum(r.paid_orders for r in DailySales.objects.filter(source="replay")) == 2


def test_rerun_resumes_and_adds_nothing(imported):
    replay()
    before = (copies().count(), replay_events().count(), Payment.objects.count())
    out = replay()
    assert "7 of them already have a replay copy" in out
    assert "0 orders created, 0 steps applied" in out and "24 already applied" in out
    assert (copies().count(), replay_events().count(), Payment.objects.count()) == before


def test_ctrl_c_stops_after_a_step_and_the_next_run_completes_without_duplicates(imported):
    stop = threading.Event()

    def interrupt_after_seven(step, run):
        if run.steps_applied == 7:
            stop.set()  # what the command's SIGINT handler does

    plan = services.build_plan(services.select_orders(date(2016, 1, 1), date(2018, 12, 31)))
    run = ReplayRun.objects.create(date_from=date(2016, 1, 1), date_to=date(2018, 12, 31), speed=0)
    run = services.Runner(run, plan, stop=stop, on_step=interrupt_after_seven).execute()
    assert run.status == "interrupted" and run.steps_applied == 7
    assert replay_events().count() == 7

    out = replay()
    assert "completed" in out and "17 steps applied" in out
    assert copies().count() == 7 and replay_events().count() == 24
    assert copies().filter(status="delivered").count() == 2


def test_a_stop_during_the_wait_leaves_the_pending_step_for_the_next_run(imported):
    plan = services.build_plan([imported["o1"]])
    run = ReplayRun.objects.create(date_from=date(2017, 10, 2), date_to=date(2017, 10, 2), speed=1000)
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()  # Ctrl-C while it waits (capped at MAX_SLEEP) for step 2
    started = time.monotonic()
    run = services.Runner(run, plan, stop=stop).execute()
    assert time.monotonic() - started < services.MAX_SLEEP
    assert run.status == "interrupted" and run.steps_applied == 1  # placed, payment still pending
    assert copies().get().status == "created"


def test_dry_run_writes_nothing(imported):
    out = replay(dry_run=True)
    assert "7 orders, 24 steps/events" in out and "Dry run: nothing written." in out
    for part in ("delivered 2", "canceled 2", "shipped 1", "unavailable 1", "approved 1"):
        assert part in out.split("Final statuses: ")[1].splitlines()[0]
    assert not copies().exists() and not ReplayRun.objects.exists() and not replay_events().exists()


def test_command_validates_its_range(imported):
    with pytest.raises(CommandError, match="before"):
        replay(date_from="2018-01-02", date_to="2018-01-01")
    with pytest.raises(CommandError, match="Imported orders span 2017-10-02..2018-08-01"):
        replay(date_from="2020-01-01", date_to="2020-01-31")


# --- the shop is untouched, and reset restores everything ------------------------------------------


def shop_snapshot():
    return {
        "imported": [model_to_dict(o) for o in Order.objects.filter(source="olist").order_by("pk")],
        "items": list(OrderItem.objects.filter(order__source="olist").order_by("pk").values()),
        "offers": list(Offer.objects.order_by("pk").values("pk", "price", "freight", "stock")),
        "products": list(Product.objects.order_by("pk").values(
            "pk", "sales_count", "first_sold_at", "min_price", "rating_avg", "rating_count")),
    }


def projections():
    return [
        sorted(model.objects.values_list(*fields), key=repr)  # category_id may be None
        for model, fields in (
            (DailySales, ("day", "source", "orders", "canceled_orders", "paid_orders", "gmv", "items")),
            (CategorySales, ("day", "source", "category_id", "revenue", "units")),
            (StateSales, ("day", "source", "state", "orders", "gmv")),
            (DeliveryStats, ("day", "source", "delivered", "delivery_seconds_total", "late")),
        )
    ]


def test_replay_leaves_the_shop_alone_and_reset_removes_every_trace(imported, events_redis):
    call_command("backfill_analytics", stdout=StringIO())
    shop, analytics = shop_snapshot(), projections()
    replay()
    drain(events_redis)
    # Stock, prices, sales counts and the imported orders are unchanged, even after a full
    # offers + stats refresh (what a re-import runs) over data that now includes replay copies
    refresh_offers_and_stats()
    assert shop_snapshot() == shop
    assert DailySales.objects.filter(source="replay").exists()
    assert not Reservation.objects.exists()

    out = StringIO()
    call_command("replay_reset", stdout=out)
    assert "Removed 7 replayed orders, 24 outbox events, 24 event log rows" in out.getvalue()
    assert not copies().exists() and not ReplayRun.objects.exists()
    assert not EventLog.objects.filter(payload__order_source="replay").exists()
    assert not ProcessedEvent.objects.exists()  # only replay events were processed in this test
    assert projections() == analytics
    assert shop_snapshot() == shop


def test_reset_of_one_run_keeps_the_others(imported):
    replay(date_from="2017-10-01", date_to="2017-12-31")  # o1
    replay(date_from="2018-01-01", date_to="2018-02-28")  # o2
    first, second = ReplayRun.objects.order_by("pk")
    call_command("replay_reset", "--run", str(first.pk), "--force", stdout=StringIO())
    assert list(copies().values_list("replay_run_id", flat=True)) == [second.pk]
    assert list(ReplayRun.objects.values_list("pk", flat=True)) == [second.pk]


def test_reset_refuses_while_a_run_is_marked_running(imported):
    ReplayRun.objects.create(date_from=date(2017, 1, 1), date_to=date(2017, 1, 2), speed=0)
    with pytest.raises(CommandError, match="is running: stop it first"):
        call_command("replay_reset", stdout=StringIO())


# --- nothing but the replay moves a replay order ---------------------------------------------------


@pytest.fixture
def unpaid_copy(imported):
    """A replay copy left 'created' (stopped right after its first step)."""
    run = ReplayRun.objects.create(date_from=date(2017, 10, 2), date_to=date(2017, 10, 2), speed=0, status="interrupted")
    src = imported["o1"]
    return services.create_copy(src, run, services.replay_customer(), src.purchased_at)


def test_the_sweeper_never_touches_a_replay_order(unpaid_copy, make_offer):
    # Even with an expired active reservation (copies never get one), the sweeper skips it
    Reservation.objects.create(order=unpaid_copy, offer=make_offer(), quantity=1,
                               expires_at=unpaid_copy.purchased_at + timedelta(minutes=15))
    assert release_expired(now=timezone.now() + timedelta(days=1)) == 0
    unpaid_copy.refresh_from_db()
    assert unpaid_copy.status == "created"


def test_the_replay_user_can_watch_but_not_act(unpaid_copy, user_client):
    client = user_client(unpaid_copy.customer.user)
    url = f"/api/orders/{unpaid_copy.external_id}/"
    detail = client.get(url).json()
    assert (detail["source"], detail["can_pay"], detail["can_cancel"]) == ("replay", False, False)

    for response in (client.post(url + "cancel/"), client.post(url + "payment/"), client.get(url + "payment/return/")):
        assert response.status_code == 409
        assert response.json()["code"] == "replay_read_only"
    unpaid_copy.refresh_from_db()
    assert unpaid_copy.status == "created"

    replay(date_from="2017-10-02", date_to="2017-10-02")  # the replay still moves it on
    unpaid_copy.refresh_from_db()
    assert unpaid_copy.status == "delivered"


# --- the fulfilment services ------------------------------------------------------------------------


def test_fulfilment_services_follow_the_state_machine_and_record_events(placed_order):
    order, _, _ = placed_order
    with pytest.raises(InvalidTransition):
        invoice(order.pk)  # unpaid
    pay(order.pk, "success")
    with pytest.raises(InvalidTransition):
        ship(order.pk)  # not invoiced yet
    invoice(order.pk)
    with pytest.raises(InvalidTransition):
        cancel_paid(order.pk)  # only while approved
    ship(order.pk)
    order = deliver(order.pk)
    assert order.status == "delivered" and order.delivered_carrier_at and order.delivered_customer_at
    types = list(OutboxEvent.objects.filter(aggregate_id=order.external_id).order_by("occurred_at").values_list("event_type", flat=True))
    assert types == ["OrderPlaced", "OrderPaid", "OrderInvoiced", "OrderShipped", "OrderDelivered"]
    assert set(types) <= order_events.ORDER_EVENTS
    assert list(order.status_history.values_list("reason", flat=True)) == [
        "checkout", "payment_succeeded", "invoiced", "shipped", "delivered"]


def test_paid_cancel_and_unavailable_are_refused_for_non_replay_orders(placed_order, imported):
    """A real paid cancellation needs refunds and restocking (out of scope): until then only
    replay copies may take these transitions."""
    order, _, (a, _) = placed_order
    pay(order.pk, "success")
    shipped_olist = imported["o4"]
    Order.objects.filter(pk=shipped_olist.pk).update(status="approved")
    for target in (order, shipped_olist):
        for action in (cancel_paid, mark_unavailable):
            with pytest.raises(InvalidTransition, match="only replayed orders"):
                action(target.pk)
        target.refresh_from_db()
        assert target.status == "approved"
    assert not OutboxEvent.objects.filter(event_type__in=["OrderCanceled", "OrderUnavailable"]).exists()
    a.refresh_from_db()
    assert a.stock == 3  # untouched


# --- concurrent runs ---------------------------------------------------------------------------------


def one_payment_and_one_paid_event_per_copy():
    for copy in copies().exclude(status__in=["created"]):
        if copy.status == "canceled" and not copy.approved_at:
            continue  # canceled before payment
        assert Payment.objects.filter(order=copy).count() == 1, copy
        assert replay_events("OrderPaid").filter(aggregate_id=copy.external_id).count() == 1, copy


@pytest.mark.django_db(transaction=True)
def test_the_same_step_applied_concurrently_lands_once(imported):
    """pay() locks the copy (select_for_update) and checks 'created' under that lock, in the
    transaction that transitions: the loser sees 'approved' and raises InvalidTransition."""
    run = ReplayRun.objects.create(date_from=date(2017, 1, 1), date_to=date(2018, 12, 31), speed=0, status="interrupted")
    customer = services.replay_customer()
    for key in ("o1", "o2", "o4", "o7", "o8"):  # a few rounds to give the race every chance
        src = imported[key]
        copy = services.create_copy(src, run, customer, src.purchased_at)
        results = run_concurrently(*[lambda: services.apply_step("approve", copy.pk, src.approved_at)] * 2)
        assert sorted(type(r).__name__ for r in results) == ["InvalidTransition", "NoneType"], results
    one_payment_and_one_paid_event_per_copy()
    assert Payment.objects.filter(order__source="replay").count() == 5


@pytest.mark.django_db(transaction=True)
def test_two_runners_over_the_same_orders_apply_every_step_exactly_once(imported):
    plan = services.build_plan(services.select_orders(date(2016, 1, 1), date(2018, 12, 31)))
    # Bypasses start_run on purpose (it would refuse the second): this is about the steps.
    # Neither run is 'running', so their final status writes are skipped (taken_over); fine here.
    runs = [ReplayRun.objects.create(date_from=date(2016, 1, 1), date_to=date(2018, 12, 31), speed=0, status="interrupted")
            for _ in range(2)]
    results = run_concurrently(*[services.Runner(run, plan).execute for run in runs])
    assert all(isinstance(r, ReplayRun) for r in results), results
    assert copies().count() == 7
    assert replay_events().count() == 24  # each planned step once, never twice
    assert sum(r.steps_applied for r in results) == 24
    one_payment_and_one_paid_event_per_copy()


def test_only_one_replay_runs_at_a_time(imported):
    run, taken_over = services.start_run(date_from=date(2017, 1, 1), date_to=date(2017, 1, 2), speed=0)
    assert run.status == "running" and taken_over is None
    with pytest.raises(services.ReplayAlreadyRunning):
        services.start_run(date_from=date(2017, 1, 1), date_to=date(2017, 1, 2), speed=0)
    with pytest.raises(CommandError, match="one replay at a time"):
        replay()
    # The database enforces it, whatever the code does (partial unique index on status='running')
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        ReplayRun.objects.create(date_from=date(2017, 1, 1), date_to=date(2017, 1, 2), speed=0, status="running")


@pytest.mark.django_db(transaction=True)
def test_two_runs_starting_at_once_cannot_both_start(imported):
    for _ in range(5):
        results = run_concurrently(*[lambda: services.start_run(date_from=date(2017, 1, 1), date_to=date(2017, 1, 2), speed=0)] * 2)
        assert sorted(type(r).__name__ for r in results) == ["ReplayAlreadyRunning", "tuple"], results
        assert ReplayRun.objects.filter(status="running").count() == 1
        ReplayRun.objects.update(status="completed")


def test_a_dead_run_is_taken_over_after_its_heartbeat_goes_stale(imported):
    dead, _ = services.start_run(date_from=date(2017, 1, 1), date_to=date(2017, 1, 2), speed=0)
    ReplayRun.objects.filter(pk=dead.pk).update(heartbeat_at=timezone.now() - services.STALE_AFTER + timedelta(seconds=30))
    with pytest.raises(services.ReplayAlreadyRunning):  # not stale yet
        services.start_run(date_from=date(2017, 1, 1), date_to=date(2017, 1, 2), speed=0)

    ReplayRun.objects.filter(pk=dead.pk).update(heartbeat_at=timezone.now() - services.STALE_AFTER - timedelta(seconds=1))
    out = replay(date_from="2017-10-02", date_to="2017-10-02")
    assert f"Replay #{dead.pk} had no heartbeat" in out and "completed" in out
    dead.refresh_from_db()
    assert dead.status == "failed" and "Abandoned" in dead.error


def test_a_taken_over_run_stops_without_writing_further_steps(imported, monkeypatch):
    """The process was frozen, another one marked its run failed: on its next heartbeat the
    runner sees 0 rows updated (WHERE status='running') and stops before another step."""
    monkeypatch.setattr(services, "HEARTBEAT_SECONDS", 0.0)  # heartbeat before every step
    run, _ = services.start_run(date_from=date(2016, 1, 1), date_to=date(2018, 12, 31), speed=0)

    def taken_over_after_five(step, run):
        if run.steps_applied == 5:
            ReplayRun.objects.filter(pk=run.pk).update(status="failed", error="Abandoned: taken over (test)")

    plan = services.build_plan(services.select_orders(date(2016, 1, 1), date(2018, 12, 31)))
    runner = services.Runner(run, plan, on_step=taken_over_after_five)
    run = runner.execute()

    assert runner.taken_over
    assert replay_events().count() == 5  # nothing after the takeover
    stored = ReplayRun.objects.get(pk=run.pk)
    assert (stored.status, stored.error) == ("failed", "Abandoned: taken over (test)")  # not overwritten
    assert run.status == "failed"


def test_the_command_reports_a_takeover(imported, monkeypatch):
    original = services.Runner._apply

    def apply_then_get_taken_over(self, step):
        original(self, step)
        ReplayRun.objects.filter(pk=self.run.pk).update(status="failed", error="Abandoned: taken over (test)")

    monkeypatch.setattr(services, "HEARTBEAT_SECONDS", 0.0)
    monkeypatch.setattr(services.Runner, "_apply", apply_then_get_taken_over)
    with pytest.raises(CommandError, match="was taken over by another process .*Stopped without applying further steps; 1 were"):
        replay()
    assert replay_events().count() == 1


def test_reset_takes_over_a_dead_run_without_force(imported):
    replay(date_from="2017-10-02", date_to="2017-10-02")
    ReplayRun.objects.update(status="running", heartbeat_at=timezone.now() - timedelta(hours=1))
    out = StringIO()
    call_command("replay_reset", stdout=out)
    assert "had no heartbeat" in out.getvalue() and "Removed 1 replayed orders" in out.getvalue()


def test_a_long_run_keeps_its_heartbeat_fresh(imported, monkeypatch):
    monkeypatch.setattr(services, "HEARTBEAT_SECONDS", 0.0)  # checkpoint on every step
    beats = []
    original = services.Runner._checkpoint

    def spy(self, **final):
        beats.append(self.run.heartbeat_at)
        return original(self, **final)

    monkeypatch.setattr(services.Runner, "_checkpoint", spy)
    replay()
    assert len(beats) >= 24


# --- after a reset -------------------------------------------------------------------------------------


@pytest.fixture
def staff_client(make_user):
    from rest_framework.test import APIClient

    user = make_user()
    user.is_staff = True
    user.save()
    client = APIClient()
    client.force_login(user)
    return client


def test_staff_pages_handle_events_of_orders_that_no_longer_exist(imported, events_redis, staff_client):
    replay(date_from="2017-10-02", date_to="2017-10-02")
    drain(events_redis)
    gone = copies().get().external_id
    call_command("replay_reset", stdout=StringIO())
    # reset removed this order's log; its timeline is simply empty (the page says "No events")
    assert not EventLog.objects.filter(aggregate_id=gone).exists()
    response = staff_client.get(f"/api/staff/orders/{gone}/events/")
    assert response.status_code == 200 and response.json() == []

    # An event still in flight during a forced reset gets logged after its order is gone:
    # the explorer reads only EventLog/ProcessedEvent, so both views still render it
    EventLog.objects.create(event_id=uuid.uuid4(), type="OrderShipped", aggregate_type="order", aggregate_id=gone,
                            stream="test-events:order", payload={"order_id": gone, "order_source": "replay"},
                            occurred_at=timezone.now())
    listing = staff_client.get("/api/staff/events/", {"aggregate_id": gone})
    assert listing.status_code == 200 and [e["type"] for e in listing.json()["results"]] == ["OrderShipped"]
    timeline = staff_client.get(f"/api/staff/orders/{gone}/events/")
    assert timeline.status_code == 200 and [e["type"] for e in timeline.json()] == ["OrderShipped"]
