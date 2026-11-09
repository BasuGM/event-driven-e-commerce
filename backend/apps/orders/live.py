"""Live order tracking: snapshots, their versions, and the "order changed" signal.

The signal (Redis Pub/Sub, ``<LIVE_CHANNEL_PREFIX>:order:<external_id>``) carries no state: it
only tells open streams to re-read the order. Pub/Sub can drop messages, so correctness comes
from always sending the current snapshot read from the database; a missed signal is fixed by
the next one, a reconnect, or the stream's fallback poll.
"""

from __future__ import annotations

import hashlib
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# What a live page needs to re-render (the same values the order detail API returns)
SNAPSHOT_FIELDS = ("status", "status_history", "payment", "can_pay", "can_cancel", "reservation_expires_at")
FINAL_STATUSES = frozenset({"delivered", "canceled", "unavailable"})


def snapshot_version(data: dict) -> str:
    """Content hash of the snapshot fields: equal versions = nothing new to show."""
    canonical = json.dumps({k: data.get(k) for k in SNAPSHOT_FIELDS}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def snapshot_from_detail(data: dict) -> dict:
    """The order detail API's data (which already carries ``live_version``) -> a snapshot."""
    return {**{k: data[k] for k in SNAPSHOT_FIELDS}, "version": data["live_version"]}


def read_snapshot(user, order_id: str) -> dict | None:
    """The owner's current snapshot, or None if the order isn't theirs (or doesn't exist).
    Same query and serializer as the order detail API, so the rules can't drift."""
    from .selectors import order_detail
    from .serializers import OrderDetailSerializer

    order = order_detail(user).filter(external_id=order_id).first()
    if order is None:
        return None
    return snapshot_from_detail(OrderDetailSerializer(order).data)


def is_final(snapshot: dict) -> bool:
    """Nothing more will happen: a terminal status and no payment still awaiting its webhook
    (a canceled order can still get a late "refund due" while one is pending)."""
    payment = snapshot.get("payment") or {}
    return snapshot["status"] in FINAL_STATUSES and payment.get("status") != "processing"


def channel_name(order_id: str) -> str:
    return f"{settings.LIVE_CHANNEL_PREFIX}:order:{order_id}"


def publish_order_signal(order_id: str, token: str = "") -> int:
    """Tell open streams for this order to re-read it. Best effort: a lost signal is harmless
    (state-based snapshots), so a Redis error is logged, not raised."""
    from apps.events.streams import redis_client

    try:
        return redis_client().publish(channel_name(order_id), token)
    except Exception:  # noqa: BLE001 - a missed signal only delays an update
        logger.warning("Could not publish live signal for order %s", order_id, exc_info=True)
        return 0
