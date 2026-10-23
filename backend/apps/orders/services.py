"""Checkout, payment, cancellation and reservation expiry.

Every change to ``Offer.stock`` after the import happens in this module, and every order state
change records its domain event (``events.record_order_event``) in the same transaction.

Lock-order rule (prevents deadlocks): Cart (owner only) -> Order -> Offers in ascending id.
No code path takes these locks in a different order, so no two transactions can each hold a
lock the other is waiting for. Products are locked separately, also in ascending id, by
``refresh_product_stats`` (after commit, in its own transaction).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.cart.models import Cart
from apps.catalog.models import Offer
from apps.catalog.stats import refresh_product_stats_on_commit
from apps.core.errors import EmptyCart, InvalidTransition, OutOfStock, ReservationExpired
from apps.customers.models import Customer

from . import events
from .models import Order, OrderItem, Payment, Reservation
from .state import transition

SHIPPING_LIMIT = timedelta(days=3)


@dataclass(frozen=True)
class ShippingAddress:
    full_name: str
    street: str
    city: str
    state: str
    zip_code: str


def new_external_id() -> str:
    """32-char lowercase hex, the same shape as Olist IDs."""
    return uuid.uuid4().hex


def lock_offers(offer_ids) -> dict[int, Offer]:
    """Lock offers in ascending id order. ORDER BY ... FOR UPDATE locks rows as they come out
    of the sort, so every transaction acquires overlapping offers in the same order."""
    offers = Offer.objects.select_for_update().filter(id__in=set(offer_ids)).order_by("id")
    return {offer.id: offer for offer in offers}


def lock_order(order_id: int, *, skip_locked: bool = False) -> Order | None:
    # of=("self",): lock only the order row, never the joined customer
    order = (
        Order.objects.select_for_update(skip_locked=skip_locked, of=("self",))
        .filter(pk=order_id)
        .first()
    )
    if order is None and not skip_locked:
        raise Order.DoesNotExist(order_id)
    return order


def order_totals(order: Order) -> tuple[Decimal, Decimal]:
    totals = order.items.aggregate(items=Sum("price"), freight=Sum("freight_value"))
    return totals["items"] or Decimal("0.00"), totals["freight"] or Decimal("0.00")


# --- checkout --------------------------------------------------------------------------------


def checkout(user, address: ShippingAddress, *, now: datetime | None = None) -> Order:
    """Turn the user's cart into an order, holding stock for RESERVATION_TTL_MINUTES.

    Runs in one transaction: lock cart -> lock offers (by id) -> check every line -> decrement
    stock + reserve -> create order with price/freight snapshots -> empty cart. Any shortage
    rolls everything back and raises OutOfStock listing each problem line.
    """
    now = now or timezone.now()
    with transaction.atomic():
        # Serialises two checkouts of the same cart (two tabs): the second waits, then sees it empty.
        cart = Cart.objects.select_for_update().filter(user=user).first()
        lines = list(cart.items.order_by("id")) if cart else []
        if not lines:
            raise EmptyCart("Your cart is empty.")

        offers = lock_offers(line.offer_id for line in lines)
        short = [line for line in lines if offers[line.offer_id].stock < line.quantity]
        if short:
            names = dict(
                Offer.objects.filter(id__in=[l.offer_id for l in short]).values_list("id", "product__name")
            )
            raise OutOfStock(
                "Some items don't have enough stock.",
                lines=[
                    {
                        "offer_id": line.offer_id,
                        "product": names[line.offer_id],
                        "requested": line.quantity,
                        "available": offers[line.offer_id].stock,
                    }
                    for line in short
                ],
            )

        customer = _customer_for(user, address)
        order = Order.objects.create(
            external_id=new_external_id(),
            customer=customer,
            olist_customer_id=new_external_id(),  # Olist issues a per-order customer id too
            status=Order.Status.CREATED,
            purchased_at=now,
            shipping_name=address.full_name,
            shipping_street=address.street,
            shipping_city=address.city,
            shipping_state=address.state,
            shipping_zip=address.zip_code,
        )
        # Olist stores one item row per unit: keep that shape so Step 2's stats SQL still holds.
        items, number = [], 0
        for line in lines:
            offer = offers[line.offer_id]
            for _ in range(line.quantity):
                number += 1
                items.append(
                    OrderItem(
                        order=order, item_number=number, product_id=offer.product_id,
                        seller_id=offer.seller_id, shipping_limit_at=now + SHIPPING_LIMIT,
                        price=offer.price, freight_value=offer.freight,  # snapshots
                    )
                )
        OrderItem.objects.bulk_create(items)

        expires_at = now + timedelta(minutes=settings.RESERVATION_TTL_MINUTES)
        for line in lines:
            # Decrement in the database: the CHECK (stock >= 0) constraint is the backstop.
            Offer.objects.filter(pk=line.offer_id).update(stock=F("stock") - line.quantity)
        Reservation.objects.bulk_create(
            Reservation(offer_id=line.offer_id, order=order, quantity=line.quantity, expires_at=expires_at)
            for line in lines
        )
        order.status_history.create(from_status="", to_status=Order.Status.CREATED, reason="checkout")
        events.record_order_event(events.ORDER_PLACED, order, reason="checkout", now=now)
        cart.items.all().delete()
        refresh_product_stats_on_commit(offer.product_id for offer in offers.values())
    return order


def _customer_for(user, address: ShippingAddress) -> Customer:
    zip_prefix = address.zip_code.replace("-", "")[:5]
    customer = Customer.objects.filter(user=user).first()
    if customer is None:
        return Customer.objects.create(
            external_id=new_external_id(), user=user, zip_code_prefix=zip_prefix,
            city=address.city.lower(), state=address.state,
        )
    # Like the import: the address of the latest order wins
    customer.zip_code_prefix, customer.city, customer.state = zip_prefix, address.city.lower(), address.state
    customer.save(update_fields=["zip_code_prefix", "city", "state"])
    return customer


# --- reservations ----------------------------------------------------------------------------


def _resolve_reservations(order: Order, status: str, now: datetime) -> set[int]:
    """Commit or release the order's active reservations exactly once. Returns product ids.

    Each reservation flips with a conditional UPDATE ... WHERE status='active'; stock is only
    returned when that update actually changed the row, so a reservation can never be released
    (or committed) twice, even if two code paths race.
    """
    active = list(order.reservations.filter(status=Reservation.Status.ACTIVE).order_by("offer_id"))
    if not active:
        return set()
    offers = lock_offers(r.offer_id for r in active)  # order already locked: order -> offers
    for reservation in active:
        flipped = Reservation.objects.filter(pk=reservation.pk, status=Reservation.Status.ACTIVE).update(
            status=status, resolved_at=now
        )
        if flipped and status == Reservation.Status.RELEASED:
            Offer.objects.filter(pk=reservation.offer_id).update(stock=F("stock") + reservation.quantity)
    return {offers[r.offer_id].product_id for r in active}


def _release_and_cancel(order: Order, reason: str, now: datetime) -> None:
    product_ids = _resolve_reservations(order, Reservation.Status.RELEASED, now)
    transition(order, Order.Status.CANCELED, reason, now=now)
    refresh_product_stats_on_commit(product_ids)


def _has_expired_reservations(order: Order, now: datetime) -> bool:
    return order.reservations.filter(status=Reservation.Status.ACTIVE, expires_at__lte=now).exists()


# --- payment and cancellation ----------------------------------------------------------------


def pay(order_id: int, outcome: str, *, now: datetime | None = None) -> Order:
    """Simulated payment. success -> approved (stock stays sold); fail -> canceled (stock back).

    Paying after the reservation expired cancels the order, *commits that*, then raises
    ReservationExpired (the raise happens outside the transaction so the cancel isn't undone).
    """
    now = now or timezone.now()
    expired = False
    with transaction.atomic():
        order = lock_order(order_id)
        if order.status != Order.Status.CREATED:
            raise InvalidTransition(
                f"Only unpaid orders can be paid; this order is '{order.status}'.",
                current_status=order.status,
            )
        if _has_expired_reservations(order, now):
            _release_and_cancel(order, "reservation_expired", now)
            events.record_order_event(
                events.RESERVATION_EXPIRED, order, reason="reservation_expired", now=now,
                source="payment_attempt",
            )
            expired = True
        elif outcome == "success":
            product_ids = _resolve_reservations(order, Reservation.Status.COMMITTED, now)
            transition(order, Order.Status.APPROVED, "payment_succeeded", now=now)
            items_total, freight_total = order_totals(order)
            Payment.objects.create(
                order=order, sequential=order.payments.count() + 1,
                payment_type=Payment.PaymentType.CREDIT_CARD, installments=1,
                value=items_total + freight_total,
            )
            events.record_order_event(events.ORDER_PAID, order, reason="payment_succeeded", now=now)
            refresh_product_stats_on_commit(product_ids)
        else:
            _release_and_cancel(order, "payment_failed", now)
            events.record_order_event(events.PAYMENT_FAILED, order, reason="payment_failed", now=now)
    if expired:
        raise ReservationExpired(
            "The stock hold for this order expired before payment, so the order was canceled.",
            current_status=Order.Status.CANCELED,
        )
    return order


def cancel(order_id: int, *, reason: str = "customer_canceled", now: datetime | None = None) -> Order:
    """Customer cancellation: only while the order is still unpaid (created)."""
    now = now or timezone.now()
    with transaction.atomic():
        order = lock_order(order_id)
        if order.status != Order.Status.CREATED:
            raise InvalidTransition(
                f"Only unpaid orders can be canceled; this order is '{order.status}'.",
                current_status=order.status,
            )
        _release_and_cancel(order, reason, now)
        events.record_order_event(events.ORDER_CANCELED, order, reason=reason, now=now)
    return order


# --- expiry sweeper --------------------------------------------------------------------------


def release_expired(*, now: datetime | None = None, limit: int = 100) -> int:
    """Cancel unpaid orders whose reservations expired and return their stock.

    Each order is handled in its own transaction. SKIP LOCKED means a concurrent sweeper (or a
    pay/cancel already holding the order) is skipped rather than waited on; the state is then
    re-checked under the lock. Safe to run twice, and concurrently.
    """
    now = now or timezone.now()
    candidates = list(
        Order.objects.filter(
            status=Order.Status.CREATED,
            reservations__status=Reservation.Status.ACTIVE,
            reservations__expires_at__lte=now,
        )
        .values_list("id", flat=True)
        .distinct()
        .order_by("id")[:limit]
    )
    released = 0
    for order_id in candidates:
        with transaction.atomic():
            order = lock_order(order_id, skip_locked=True)
            if order is None or order.status != Order.Status.CREATED:
                continue
            if not _has_expired_reservations(order, now):
                continue
            _release_and_cancel(order, "reservation_expired", now)
            events.record_order_event(
                events.RESERVATION_EXPIRED, order, reason="reservation_expired", now=now, source="sweeper"
            )
            released += 1
    return released
