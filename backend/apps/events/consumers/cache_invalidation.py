"""Revalidates the Next.js product cache when product data changed (ProductsChanged)."""

from __future__ import annotations

from ..consumer import Consumer
from ..revalidate import product_tag, revalidate_tags
from ..streams import Event
from .product_stats import PRODUCTS_CHANGED


class CacheInvalidationConsumer(Consumer):
    name = "cache_invalidation"
    streams = ("product",)
    event_types = frozenset({PRODUCTS_CHANGED})

    def handle(self, event: Event) -> None:
        # The HTTP call runs inside the consumer's transaction: if it fails, the ProcessedEvent
        # row rolls back with it and the entry is retried. Revalidating twice is harmless.
        tags = [product_tag(slug) for slug in event.payload.get("slugs", [])]
        if tags:
            revalidate_tags(tags)
