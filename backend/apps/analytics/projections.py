"""Recompute analytics projections from orders: state-based, like catalog.stats (never +/-).

``recompute_days(days, source)`` rebuilds those (day, source) rows in one transaction:
advisory-lock each day (ascending, so two recomputes can't deadlock; the same day queues
instead of double-inserting), DELETE the rows, INSERT … SELECT them again from the orders.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection, transaction

PAID = "('approved', 'invoiced', 'processing', 'shipped', 'delivered')"  # reached approved or later
CANCELED = "('canceled', 'unavailable')"
LOCAL_DAY = "(o.purchased_at AT TIME ZONE %(tz)s)::date"
SCOPE = f"o.source = %(source)s AND {LOCAL_DAY} = ANY(%(days)s)"

# Order totals: items are stored one row per unit (like Olist)
ORDER_TOTALS = """
LEFT JOIN LATERAL (
    SELECT sum(i.price + i.freight_value) AS total, count(*) AS units
    FROM orders_orderitem i WHERE i.order_id = o.id
) t ON true
"""

INSERTS = {
    "analytics_dailysales": f"""
        INSERT INTO analytics_dailysales (day, source, orders, canceled_orders, paid_orders, gmv, items, updated_at)
        SELECT {LOCAL_DAY}, o.source, count(*),
               count(*) FILTER (WHERE o.status IN {CANCELED}),
               count(*) FILTER (WHERE o.status IN {PAID}),
               coalesce(sum(t.total) FILTER (WHERE o.status IN {PAID}), 0),
               coalesce(sum(t.units) FILTER (WHERE o.status IN {PAID}), 0),
               now()
        FROM orders_order o {ORDER_TOTALS}
        WHERE {SCOPE}
        GROUP BY 1, 2
    """,
    "analytics_categorysales": f"""
        INSERT INTO analytics_categorysales (day, source, category_id, revenue, units)
        SELECT {LOCAL_DAY}, o.source, p.category_id, sum(i.price), count(*)
        FROM orders_order o
        JOIN orders_orderitem i ON i.order_id = o.id
        JOIN catalog_product p ON p.id = i.product_id
        WHERE {SCOPE} AND o.status IN {PAID}
        GROUP BY 1, 2, 3
    """,
    "analytics_statesales": f"""
        INSERT INTO analytics_statesales (day, source, state, orders, gmv)
        SELECT {LOCAL_DAY}, o.source, coalesce(nullif(o.shipping_state, ''), c.state), count(*),
               coalesce(sum(t.total) FILTER (WHERE o.status IN {PAID}), 0)
        FROM orders_order o
        JOIN customers_customer c ON c.id = o.customer_id
        {ORDER_TOTALS}
        WHERE {SCOPE}
        GROUP BY 1, 2, 3
    """,
    "analytics_deliverystats": f"""
        INSERT INTO analytics_deliverystats (day, source, delivered, delivery_seconds_total, late)
        SELECT {LOCAL_DAY}, o.source, count(*),
               sum(extract(epoch FROM o.delivered_customer_at - o.purchased_at))::bigint,
               count(*) FILTER (WHERE (o.delivered_customer_at AT TIME ZONE %(tz)s)::date > o.estimated_delivery_date)
        FROM orders_order o
        WHERE {SCOPE} AND o.status = 'delivered' AND o.delivered_customer_at IS NOT NULL
        GROUP BY 1, 2
    """,
}


def local_day(moment: datetime) -> date:
    return moment.astimezone(ZoneInfo(settings.ANALYTICS_TIMEZONE)).date()


def recompute_days(days, source: str) -> None:
    days = sorted(set(days))
    if not days:
        return
    params = {"source": source, "days": days, "tz": settings.ANALYTICS_TIMEZONE}
    with transaction.atomic(), connection.cursor() as cursor:
        for day in days:  # ascending: the same order everywhere, so no deadlocks
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"analytics:{source}:{day.isoformat()}"])
        for table, insert in INSERTS.items():
            cursor.execute(f"DELETE FROM {table} WHERE source = %(source)s AND day = ANY(%(days)s)", params)
            cursor.execute(insert, params)


def rebuild(source: str, *, chunk_days: int = 31) -> int:
    """Every day that has orders (or stale rows) for this source, in chunks: one transaction
    (and up to chunk_days advisory locks) at a time. Returns the number of days."""
    tz = settings.ANALYTICS_TIMEZONE
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT (purchased_at AT TIME ZONE %s)::date FROM orders_order WHERE source = %s "
            "UNION SELECT day FROM analytics_dailysales WHERE source = %s "
            "UNION SELECT day FROM analytics_deliverystats WHERE source = %s",
            [tz, source, source, source],
        )
        days = sorted(row[0] for row in cursor.fetchall())
    for start in range(0, len(days), chunk_days):
        recompute_days(days[start:start + chunk_days], source)
    return len(days)
