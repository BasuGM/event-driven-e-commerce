"""Historical replay: re-enact imported Olist orders through the real order lifecycle.

Each imported order becomes one *copy* (``source='replay'``, ``replay_of`` = the original),
owned by the replay dev user. Its history is turned into steps with timestamps:

    place (purchased) -> approve (approved_at, via the real ``pay()``) -> invoice (synthesized)
    -> ship (carrier date) -> deliver (customer date)          or -> unavailable / cancel

All steps of all selected orders are merged by timestamp and applied on a simulated clock.
Every step goes through ``apps/orders/services.py`` (transition + history + outbox event), so
the relay, every consumer, the live order page, the explorer and the dashboard see a real
event flow.

What the replay bypasses: cart + checkout (reserving would drain real stock: historical orders
were fulfilled long ago), the payment provider and its webhooks, and notification emails. Stock
is never touched; the stats/offers SQL and the product_stats consumer ignore replay orders.

Steps are idempotent: a step only applies while the copy is still in that step's from-status,
and there is at most one copy per original (unique ``replay_of``). Re-running a range (after
Ctrl-C, or overlapping) resumes; nothing is duplicated.
"""

from __future__ import annotations

import logging
import threading
import time as monotonic_time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import redis
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.analytics.projections import local_day, recompute_days
from apps.catalog.stats import refresh_product_stats
from apps.core.errors import InvalidTransition
from apps.customers.models import Customer
from apps.events.models import EventLog, OutboxEvent, ProcessedEvent
from apps.events.streams import stream_name
from apps.notifications.models import Notification
from apps.orders import events as order_events
from apps.orders import services as order_services
from apps.orders.models import Order, OrderItem, OrderStatusHistory

from .models import ReplayRun

logger = logging.getLogger(__name__)

OLIST_TZ = ZoneInfo("America/Sao_Paulo")  # Olist dates are Brazilian local time
REPLAY_USERNAME = "replay"
REPLAY_EMAIL = "replay@example.com"
SYNTHETIC_GAP = timedelta(hours=1)  # Olist has no invoiced/canceled/unavailable timestamps
MAX_SLEEP = 2.0  # seconds: a quiet simulated night never stalls the replay for long
SAVE_EVERY = 50  # steps between ReplayRun progress saves
HEARTBEAT_SECONDS = 30.0  # a running run saves (heartbeat_at) at least this often
STALE_AFTER = timedelta(minutes=5)  # a running run silent this long is presumed dead

S = Order.Status

# The status a copy must be in for a step to apply (None: the copy must not exist yet)
FROM_STATUS = {
    "place": None,
    "approve": S.CREATED,
    "invoice": S.APPROVED,
    "ship": S.INVOICED,
    "deliver": S.SHIPPED,
    "unavailable": S.APPROVED,
    "cancel_unpaid": S.CREATED,
    "cancel_paid": S.APPROVED,
}
TO_STATUS = {
    "place": S.CREATED, "approve": S.APPROVED, "invoice": S.INVOICED, "ship": S.SHIPPED,
    "deliver": S.DELIVERED, "unavailable": S.UNAVAILABLE, "cancel_unpaid": S.CANCELED,
    "cancel_paid": S.CANCELED,
}


@dataclass(frozen=True, order=True)
class Step:
    at: datetime  # simulated (historical) time
    source_id: int  # the original order's pk (ties: oldest order first)
    index: int  # position in that order's own sequence
    kind: str


# --- selection and planning ------------------------------------------------------------------


def day_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """[from 00:00, to+1 00:00) in Sao Paulo time, like the importer and the dashboard."""
    start = datetime.combine(date_from, time.min, tzinfo=OLIST_TZ)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=OLIST_TZ)
    return start, end


def select_orders(date_from: date, date_to: date, limit: int | None = None):
    start, end = day_bounds(date_from, date_to)
    qs = (
        Order.objects.filter(source=Order.Source.OLIST, purchased_at__gte=start, purchased_at__lt=end)
        .select_related("customer")
        .order_by("purchased_at", "id")
    )
    return list(qs[:limit] if limit else qs)


def plan_order(src: Order) -> tuple[list[Step], bool]:
    """The steps that re-enact ``src``, with non-decreasing times. Returns (steps, adjusted):
    adjusted = the history isn't legal as-is (canceled after shipping is canceled right after
    approval instead; ``shipped -> canceled`` is illegal)."""
    steps: list[Step] = []
    at = src.purchased_at

    def add(kind: str, given: datetime | None) -> None:
        nonlocal at
        # Missing time: synthesize one; out-of-order Olist dates are clamped to never go back
        at = max(at, given) if given else at + SYNTHETIC_GAP
        steps.append(Step(at, src.pk, len(steps), kind))

    add("place", src.purchased_at)
    status = src.status
    adjusted = False
    if status == S.CREATED:
        pass
    elif status == S.CANCELED:
        if src.approved_at:
            add("approve", src.approved_at)
            add("cancel_paid", None)
            adjusted = src.delivered_carrier_at is not None
        else:
            add("cancel_unpaid", None)
    elif status == S.UNAVAILABLE:
        add("approve", src.approved_at)
        add("unavailable", None)
    else:  # approved, processing (stays approved: historical only), invoiced, shipped, delivered
        add("approve", src.approved_at)
        if status in (S.INVOICED, S.SHIPPED, S.DELIVERED):
            invoiced = at + SYNTHETIC_GAP
            if src.delivered_carrier_at and src.delivered_carrier_at > at:
                invoiced = min(invoiced, at + (src.delivered_carrier_at - at) / 2)  # before pickup
            add("invoice", invoiced)
        if status in (S.SHIPPED, S.DELIVERED):
            add("ship", src.delivered_carrier_at)
        if status == S.DELIVERED:
            add("deliver", src.delivered_customer_at)
    return steps, adjusted


def final_status(steps: list[Step]) -> str:
    return TO_STATUS[steps[-1].kind]


def estimate_seconds(steps: list[Step], speed: float) -> float:
    if speed <= 0:
        return 0.0
    total = 0.0
    for prev, nxt in zip(steps, steps[1:]):
        total += min(MAX_SLEEP, (nxt.at - prev.at).total_seconds() / 86400 * speed)
    return total


# --- the replay user and copies --------------------------------------------------------------


def replay_customer() -> Customer:
    """The dev user every copy belongs to (``seed_dev_users`` gives it the dev password)."""
    User = get_user_model()
    user = User.objects.filter(username=REPLAY_USERNAME).first()
    if user is None:
        user = User(username=REPLAY_USERNAME, email=REPLAY_EMAIL, first_name="Rita", last_name="Replay")
        user.set_unusable_password()
        user.save()
    customer = Customer.objects.filter(user=user).first()
    if customer is None:
        customer = Customer.objects.create(
            external_id=order_services.new_external_id(), user=user, zip_code_prefix="01310",
            city="sao paulo", state="SP",
        )
    return customer


def create_copy(src: Order, run: ReplayRun, customer: Customer, at: datetime) -> Order | None:
    """Create the replay copy of ``src`` (status created) with its items, history row and
    OrderPlaced event, in one transaction. None if another run created it first."""
    try:
        with transaction.atomic():
            copy = Order.objects.create(
                external_id=order_services.new_external_id(),
                source=Order.Source.REPLAY,
                customer=customer,
                olist_customer_id=order_services.new_external_id(),
                status=S.CREATED,
                purchased_at=src.purchased_at,
                estimated_delivery_date=src.estimated_delivery_date,
                # Where the historical buyer lived (Olist has no street or name)
                shipping_name="Olist customer",
                shipping_city=src.customer.city,
                shipping_state=src.customer.state,
                shipping_zip=src.customer.zip_code_prefix,
                replay_run=run,
                replay_of=src,
            )
            OrderItem.objects.bulk_create(
                OrderItem(
                    order=copy, item_number=item.item_number, product_id=item.product_id,
                    seller_id=item.seller_id, shipping_limit_at=item.shipping_limit_at,
                    price=item.price, freight_value=item.freight_value,
                )
                for item in src.items.order_by("item_number")
            )
            OrderStatusHistory.objects.create(
                order=copy, from_status="", to_status=S.CREATED, reason="replay_placed", occurred_at=at
            )
            order_events.record_order_event(order_events.ORDER_PLACED, copy, reason="replay_placed", now=at)
    except IntegrityError:  # uniq_replay_copy: a concurrent run got there first
        return None
    return copy


def apply_step(kind: str, copy_id: int, at: datetime) -> None:
    """One lifecycle step through the real order services (each locks, transitions, records)."""
    if kind == "approve":
        order_services.pay(copy_id, "success", now=at)  # ledger row + OrderPaid; no reservations
    elif kind == "invoice":
        order_services.invoice(copy_id, now=at)
    elif kind == "ship":
        order_services.ship(copy_id, now=at)
    elif kind == "deliver":
        order_services.deliver(copy_id, now=at)
    elif kind == "unavailable":
        order_services.mark_unavailable(copy_id, now=at)
    elif kind == "cancel_unpaid":
        order_services.cancel(copy_id, reason="canceled_before_payment", now=at)
    elif kind == "cancel_paid":
        order_services.cancel_paid(copy_id, now=at)
    else:
        raise ValueError(f"unknown step {kind}")


# --- one running replay at a time ----------------------------------------------------------------


class ReplayAlreadyRunning(Exception):
    def __init__(self, run: ReplayRun | None):
        self.run = run
        super().__init__(f"Replay #{run.pk} is running" if run else "Another replay just started")


def take_over_stale(now: datetime | None = None) -> ReplayRun | None:
    """Lock the running run (if any). Fresh heartbeat: raise ReplayAlreadyRunning. Silent for
    STALE_AFTER (the process died: kill -9, OOM, a closed laptop): mark it failed so a new run
    or a reset can proceed, and return it. Call inside a transaction."""
    now = now or timezone.now()
    current = ReplayRun.objects.select_for_update().filter(status=ReplayRun.Status.RUNNING).first()
    if current is None:
        return None
    if current.heartbeat_at > now - STALE_AFTER:
        raise ReplayAlreadyRunning(current)
    current.status, current.finished_at = ReplayRun.Status.FAILED, now
    current.error = f"Abandoned: no heartbeat since {current.heartbeat_at:%Y-%m-%d %H:%M:%S %Z}; taken over"
    current.save(update_fields=["status", "finished_at", "error"])
    logger.warning("Replay #%s had no heartbeat since %s: marked failed", current.pk, current.heartbeat_at)
    return current


def start_run(**fields) -> tuple[ReplayRun, ReplayRun | None]:
    """Create the running ReplayRun, or raise ReplayAlreadyRunning. Returns (run, taken_over).

    Atomic: the partial unique index one_running_replay (status='running') lets only one
    insert win, even when two processes find no running run at the same moment."""
    with transaction.atomic():
        taken_over = take_over_stale()
        try:
            with transaction.atomic():  # savepoint: the losing insert raises here
                return ReplayRun.objects.create(**fields, status=ReplayRun.Status.RUNNING), taken_over
        except IntegrityError:
            raise ReplayAlreadyRunning(None) from None


# --- the runner -------------------------------------------------------------------------------


@dataclass
class Plan:
    sources: dict[int, Order]
    steps: list[Step]
    final: Counter
    adjusted: int


def build_plan(sources: list[Order]) -> Plan:
    steps, final, adjusted = [], Counter(), 0
    for src in sources:
        order_steps, was_adjusted = plan_order(src)
        steps.extend(order_steps)
        final[final_status(order_steps)] += 1
        adjusted += was_adjusted
    steps.sort()
    return Plan({s.pk: s for s in sources}, steps, final, adjusted)


class Runner:
    """Walks the merged steps on a simulated clock. ``stop`` (set by SIGINT/SIGTERM in the
    command) ends it after the current step; the run is saved as interrupted and re-running
    the same range resumes. ``on_step`` is called after each applied step (progress, tests).

    Every write to the run is conditional on it still being 'running' (see ``_checkpoint``):
    if another process took it over (marked it failed after STALE_AFTER without a heartbeat),
    this runner stops before applying another step and sets ``taken_over``."""

    PROGRESS_FIELDS = ("cursor_at", "orders_created", "steps_applied", "steps_skipped")

    def __init__(
        self, run: ReplayRun, plan: Plan, *, stop: threading.Event | None = None,
        on_step: Callable[[Step, ReplayRun], None] | None = None,
    ):
        self.run, self.plan = run, plan
        self.stop = stop or threading.Event()
        self.on_step = on_step
        self.taken_over = False
        self.customer = replay_customer()
        # source pk -> (copy pk, status), kept current as steps apply
        self.copies: dict[int, tuple[int, str]] = {
            row["replay_of"]: (row["id"], row["status"])
            for row in Order.objects.filter(source=Order.Source.REPLAY, replay_of__in=list(plan.sources))
            .values("replay_of", "id", "status")
        }

    def _refresh(self, source_id: int) -> None:
        row = Order.objects.filter(replay_of=source_id).values("id", "status").first()
        if row:
            self.copies[source_id] = (row["id"], row["status"])

    def _due(self, step: Step) -> bool:
        copy = self.copies.get(step.source_id)
        if step.kind == "place":
            return copy is None
        return copy is not None and copy[1] == FROM_STATUS[step.kind]

    def _checkpoint(self, **final) -> bool:
        """Write the heartbeat + progress (+ ``final`` fields) with UPDATE ... WHERE id = ? AND
        status = 'running'. 0 rows: the run was taken over (or reset away); never overwrite
        that, return False so the caller stops."""
        now = timezone.now()
        progress = {name: getattr(self.run, name) for name in self.PROGRESS_FIELDS}
        updated = ReplayRun.objects.filter(pk=self.run.pk, status=ReplayRun.Status.RUNNING).update(
            heartbeat_at=now, **progress, **final
        )
        self._saved = monotonic_time.monotonic()
        if updated:
            self.run.heartbeat_at = now
            for name, value in final.items():
                setattr(self.run, name, value)
            return True
        self.taken_over = True
        current = ReplayRun.objects.filter(pk=self.run.pk).values("status", "error", "finished_at").first()
        if current:  # keep what the taker wrote (status failed + reason)
            self.run.status, self.run.error, self.run.finished_at = current["status"], current["error"], current["finished_at"]
        logger.error("Replay #%s is no longer running (%s): this runner stops", self.run.pk, self.run.status)
        return False

    def execute(self) -> ReplayRun:
        run, last_at = self.run, None
        self._saved = monotonic_time.monotonic()
        try:
            for step in self.plan.steps:
                if self.stop.is_set():
                    break
                # Heartbeat at the top of the loop, i.e. *before* the next write: a process that
                # was frozen long enough to be taken over (> STALE_AFTER, far more than
                # HEARTBEAT_SECONDS) finds out here, before it applies anything else.
                if monotonic_time.monotonic() - self._saved >= HEARTBEAT_SECONDS and not self._checkpoint():
                    break
                if not self._due(step):
                    run.steps_skipped += 1  # already applied (resume) or past it
                    continue
                if last_at is not None and run.speed > 0:
                    delay = min(MAX_SLEEP, (step.at - last_at).total_seconds() / 86400 * run.speed)
                    if delay > 0 and self.stop.wait(delay):
                        break  # stopped while waiting: this step stays for the next run
                self._apply(step)
                last_at = step.at
                if self.on_step:
                    self.on_step(step, run)
                if run.steps_applied % SAVE_EVERY == 0 and not self._checkpoint():
                    break
        except Exception as exc:
            self._checkpoint(
                status=ReplayRun.Status.FAILED, error=f"{type(exc).__name__}: {exc}"[:2000], finished_at=timezone.now()
            )
            raise
        if not self.taken_over:
            status = ReplayRun.Status.INTERRUPTED if self.stop.is_set() else ReplayRun.Status.COMPLETED
            self._checkpoint(status=status, finished_at=timezone.now())
        return run

    def _apply(self, step: Step) -> None:
        run = self.run
        if step.kind == "place":
            copy = create_copy(self.plan.sources[step.source_id], run, self.customer, step.at)
            if copy is None:
                self._refresh(step.source_id)
                run.steps_skipped += 1
                return
            self.copies[step.source_id] = (copy.pk, copy.status)
            run.orders_created += 1
        else:
            copy_id, _ = self.copies[step.source_id]
            try:
                apply_step(step.kind, copy_id, step.at)
            except InvalidTransition:  # another run moved it meanwhile: re-read, move on
                self._refresh(step.source_id)
                run.steps_skipped += 1
                return
            self.copies[step.source_id] = (copy_id, TO_STATUS[step.kind])
        run.steps_applied += 1
        run.cursor_at = step.at


# --- reset ------------------------------------------------------------------------------------


def order_stream_backlog(client: redis.Redis) -> int | None:
    """Entries on the order stream that some consumer group hasn't finished (pending + lag).
    None if Redis can't be asked."""
    try:
        groups = client.xinfo_groups(stream_name("order"))
    except redis.ResponseError:
        return 0  # no stream yet
    except (redis.RedisError, OSError):
        return None
    return sum(g["pending"] + (g.get("lag") or 0) for g in groups)


@dataclass
class ResetResult:
    orders: int
    events: int
    event_logs: int
    processed: int
    runs: int
    days: int


def reset(run_id: int | None = None) -> ResetResult:
    """Delete replay copies (all, or one run's) and everything they produced: items, ledger
    payments and history (cascade), outbox / EventLog / ProcessedEvent / Notification rows,
    the runs. Then
    rebuild the affected (day, 'replay') projections and refresh the products' stats.

    Redis stream entries can't be deleted selectively; they're acked already (and trimmed
    eventually). Events still in flight would be logged again by event_log, hence the
    command's backlog check."""
    copies = Order.objects.filter(source=Order.Source.REPLAY)
    runs = ReplayRun.objects.all()
    if run_id is not None:
        copies, runs = copies.filter(replay_run_id=run_id), runs.filter(pk=run_id)
    rows = list(copies.values_list("id", "external_id", "purchased_at"))
    external_ids = [ext for _, ext, _ in rows]
    days = {local_day(purchased) for _, _, purchased in rows}
    product_ids = set(OrderItem.objects.filter(order_id__in=[pk for pk, _, _ in rows]).values_list("product_id", flat=True))
    with transaction.atomic():
        outbox = OutboxEvent.objects.filter(aggregate_type="order", aggregate_id__in=external_ids)
        logs = EventLog.objects.filter(aggregate_type="order", aggregate_id__in=external_ids)
        event_ids = set(outbox.values_list("id", flat=True)) | set(logs.values_list("event_id", flat=True))
        processed, _ = ProcessedEvent.objects.filter(event_id__in=event_ids).delete()
        # None are written for replay events; this catches any from a consumer running old code
        Notification.objects.filter(event_id__in=event_ids).delete()
        events, _ = outbox.delete()
        event_logs, _ = logs.delete()
        orders = len(rows)
        Order.objects.filter(pk__in=[pk for pk, _, _ in rows]).delete()
        # A run whose copies were all deleted goes too (PROTECT keeps runs that still own some)
        runs_deleted, _ = runs.filter(orders__isnull=True).delete()
    recompute_days(days, Order.Source.REPLAY)
    refresh_product_stats(product_ids, labels=("sales", "ratings", "min_price"))
    return ResetResult(orders, events, event_logs, processed, runs_deleted, len(days))
