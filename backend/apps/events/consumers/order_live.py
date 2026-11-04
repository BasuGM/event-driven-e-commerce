"""Signals open order streams (SSE) that something happened to an order. The signal carries
no state; the stream re-reads the order from the database."""

from __future__ import annotations

from apps.orders import events as order_events
from apps.orders.live import publish_order_signal
from apps.payments.services import PAYMENT_REFUND_DUE

from ..consumer import Consumer
from ..streams import Event


class OrderLiveConsumer(Consumer):
    name = "order_live"
    streams = ("order",)
    event_types = frozenset(order_events.ORDER_EVENTS | {PAYMENT_REFUND_DUE})

    def handle(self, event: Event) -> None:
        # Publishing inside the transaction is fine: the order change itself was committed
        # before this event existed, and a stray or repeated signal only causes a re-read.
        publish_order_signal(event.aggregate_id, event.id)
