"""Keeps Product.sales_count (and min_price) current from order events, then announces which
products changed so caches can be invalidated *after* the new values are committed."""

from __future__ import annotations

from django.db import connection

from apps.catalog.stats import apply_product_stats, lock_products
from apps.orders.events import ORDER_EVENTS

from ..consumer import Consumer
from ..outbox import record_event
from ..streams import Event

PRODUCTS_CHANGED = "ProductsChanged"


class ProductStatsConsumer(Consumer):
    name = "product_stats"
    streams = ("order",)
    event_types = ORDER_EVENTS

    def handle(self, event: Event) -> None:
        lines = event.payload.get("lines", [])
        ids = sorted({line["product_id"] for line in lines})
        if not ids:
            return
        # A recompute from the orders table, not +/- deltas: the result is the same whatever
        # order events arrive in, and however often one is replayed.
        with connection.cursor() as cursor:
            lock_products(cursor, ids)
            apply_product_stats(cursor, ids, ("sales", "min_price"))
        # Same transaction (outbox): the cache consumer only hears about it once committed
        record_event(
            PRODUCTS_CHANGED,
            "product",
            ",".join(map(str, ids))[:64],
            {
                "product_ids": ids,
                "slugs": sorted({line["product_slug"] for line in lines}),
                "cause_event_id": event.id,
                "cause_event_type": event.type,
            },
        )
