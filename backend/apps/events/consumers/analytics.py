"""Keeps the analytics projections current: on every order event, recompute that order's
purchase day for its source (state-based; replays and duplicates change nothing)."""

from __future__ import annotations

from apps.analytics.projections import local_day, recompute_days
from apps.orders.events import ORDER_EVENTS
from apps.orders.models import Order

from ..consumer import Consumer
from ..streams import Event


class AnalyticsConsumer(Consumer):
    name = "analytics"
    streams = ("order",)
    event_types = ORDER_EVENTS

    def handle(self, event: Event) -> None:
        order = Order.objects.filter(external_id=event.aggregate_id).values("source", "purchased_at").first()
        if order is None:  # deleted since (e.g. a replay reset rebuilt its days already)
            return
        recompute_days([local_day(order["purchased_at"])], order["source"])
