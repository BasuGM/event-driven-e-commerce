"""The first consumers: product stats (sales_count) and Next.js cache invalidation."""

import json
import urllib.error
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command

from apps.catalog.models import Product
from apps.events.consumers import CacheInvalidationConsumer, ProductStatsConsumer
from apps.events.models import OutboxEvent, ProcessedEvent
from apps.events.relay import publish_batch
from apps.events.streams import dlq_stream, stream_name
from apps.orders.services import cancel, checkout

pytestmark = pytest.mark.django_db


def started(cls, client):
    c = cls(client, consumer_name="t1")
    c.ensure_groups()
    return c


def sales(offer):
    return Product.objects.get(pk=offer.product_id).sales_count


def ok_response():
    response = mock.MagicMock(status=204)
    response.__enter__.return_value = response
    return response


def test_sales_count_follows_order_events_and_excludes_canceled_orders(events_redis, placed_order):
    order, _, (a, b) = placed_order
    stats = started(ProductStatsConsumer, events_redis)
    assert sales(a) == 0  # not updated synchronously any more: the consumer owns it

    publish_batch(events_redis)
    stats.run_once(claim=False)
    assert (sales(a), sales(b)) == (2, 1)

    cancel(order.pk)
    publish_batch(events_redis)
    stats.run_once(claim=False)
    assert (sales(a), sales(b)) == (0, 0)  # the canceled order no longer counts

    changed = OutboxEvent.objects.filter(event_type="ProductsChanged").order_by("occurred_at")
    assert changed.count() == 2
    payload = changed.last().payload
    assert payload["product_ids"] == sorted([a.product_id, b.product_id])
    assert payload["slugs"] == sorted([a.product.slug, b.product.slug])
    assert payload["cause_event_type"] == "OrderCanceled"


def test_backfill_recounts_sales_without_canceled_orders(make_user, make_offer, fill_cart, address):
    offer = make_offer(stock=10)
    kept, dropped = make_user(), make_user()
    fill_cart(kept, (offer, 1))
    checkout(kept, address)
    fill_cart(dropped, (offer, 3))
    cancel(checkout(dropped, address).pk)
    # What Step 3 left behind: every unit counted, canceled or not
    Product.objects.filter(pk=offer.product_id).update(sales_count=4)

    out = StringIO()
    call_command("backfill_sales_count", stdout=out)

    assert sales(offer) == 1
    assert "1 product(s) changed" in out.getvalue()
    call_command("backfill_sales_count", stdout=out)  # idempotent
    assert "0 product(s) changed" in out.getvalue()


def products_changed(client, slugs):
    client.xadd(
        stream_name("product"),
        {"id": "00000000-0000-0000-0000-000000000001", "type": "ProductsChanged", "aggregate_type": "product",
         "aggregate_id": "1", "version": "1", "occurred_at": "2026-10-23T00:00:00+00:00",
         "payload": json.dumps({"product_ids": [1], "slugs": slugs})},
    )


def test_cache_consumer_revalidates_product_tags_with_the_secret(events_redis):
    cache = started(CacheInvalidationConsumer, events_redis)
    products_changed(events_redis, ["lamp-1a2b3c4d", "rug-9f8e7d6c"])

    with mock.patch("urllib.request.urlopen", return_value=ok_response()) as urlopen:
        cache.run_once(claim=False)

    request = urlopen.call_args.args[0]
    assert request.full_url == "http://frontend.test/internal/revalidate"
    assert request.get_header("X-revalidate-secret") == "test-revalidate-secret"
    assert json.loads(request.data) == {"tags": ["product:lamp-1a2b3c4d", "product:rug-9f8e7d6c"]}
    assert ProcessedEvent.objects.filter(consumer="cache_invalidation").count() == 1


def test_cache_consumer_retries_a_failing_frontend_then_dead_letters(events_redis):
    cache = started(CacheInvalidationConsumer, events_redis)
    products_changed(events_redis, ["lamp-1a2b3c4d"])
    error = urllib.error.HTTPError("http://frontend.test/internal/revalidate", 500, "boom", {}, None)

    with mock.patch("urllib.request.urlopen", side_effect=error) as urlopen:
        cache.run_once(claim=False)
        assert not ProcessedEvent.objects.exists()  # the failed attempt rolled back
        for _ in range(3):
            cache.run_once(claim=True)

    assert urlopen.call_count == 3  # deliveries 1-3; the 4th goes straight to the DLQ
    [(_, dead)] = events_redis.xrange(dlq_stream())
    assert dead["dlq_consumer"] == "cache_invalidation"
    assert dead["dlq_error"] == "RevalidateError: revalidate returned 500"


def test_end_to_end_checkout_to_cache_revalidation(events_redis, placed_order):
    order, _, (a, b) = placed_order
    stats, cache = started(ProductStatsConsumer, events_redis), started(CacheInvalidationConsumer, events_redis)

    publish_batch(events_redis)  # OrderPlaced -> events:order
    stats.run_once(claim=False)  # sales_count + ProductsChanged (outbox)
    publish_batch(events_redis)  # ProductsChanged -> events:product
    with mock.patch("urllib.request.urlopen", return_value=ok_response()) as urlopen:
        cache.run_once(claim=False)

    assert sales(a) == 2
    tags = json.loads(urlopen.call_args.args[0].data)["tags"]
    assert tags == sorted([f"product:{a.product.slug}", f"product:{b.product.slug}"])
    assert not OutboxEvent.objects.filter(published_at__isnull=True).exists()
