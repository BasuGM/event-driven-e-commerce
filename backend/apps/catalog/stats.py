"""Set-based derivation of offers and denormalised product stats.

Everything here is a handful of SQL statements over whole tables (no per-row Python loops), so
it costs the same few round trips for 2,000 orders or 100,000. Raw SQL because the ORM has no
median aggregate and cannot express ``UPDATE ... FROM``.

Each UPDATE only touches rows whose value actually changes (``IS DISTINCT FROM``), so a re-run
on unchanged data writes nothing and reports 0.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import connection

# Deterministic synthetic stock from the two Olist IDs: md5 -> 28-bit int (always positive).
# One bucket in ten is out of stock; the rest get 1..50 units.
_HASH_SQL = "('x' || substr(md5({product_ext} || {seller_ext}), 1, 7))::bit(28)::int"
STOCK_SQL = (
    "CASE WHEN {h} % 10 = 0 THEN 0 ELSE 1 + ({h} / 10) % 50 END"
)


def stock_sql(product_ext: str, seller_ext: str) -> str:
    h = _HASH_SQL.format(product_ext=product_ext, seller_ext=seller_ext)
    return STOCK_SQL.format(h=h)


OFFERS_SQL = f"""
WITH pairs AS (
    SELECT
        oi.product_id,
        oi.seller_id,
        -- Exact median in numeric: mean of the lower and upper middle values
        -- (identical for odd counts). percentile_cont would go through float8.
        round(
            (percentile_disc(0.5) WITHIN GROUP (ORDER BY oi.price)
             + percentile_disc(0.5) WITHIN GROUP (ORDER BY oi.price DESC)) / 2,
            2
        ) AS price,
        p.external_id AS product_ext,
        s.external_id AS seller_ext
    FROM orders_orderitem oi
    JOIN catalog_product p ON p.id = oi.product_id
    JOIN catalog_seller s ON s.id = oi.seller_id
    GROUP BY oi.product_id, oi.seller_id, p.external_id, s.external_id
)
INSERT INTO catalog_offer (product_id, seller_id, price, stock)
SELECT product_id, seller_id, price, {stock_sql("product_ext", "seller_ext")}
FROM pairs
ON CONFLICT (product_id, seller_id) DO UPDATE
    SET price = EXCLUDED.price, stock = EXCLUDED.stock
    WHERE (catalog_offer.price, catalog_offer.stock)
        IS DISTINCT FROM (EXCLUDED.price, EXCLUDED.stock)
"""

# Each statement recomputes one group of columns for *every* product (LEFT JOIN), so a product
# that loses its last sale/review/offer is reset too.
SALES_SQL = """
UPDATE catalog_product p
SET sales_count = v.sales_count, first_sold_at = v.first_sold_at
FROM (
    SELECT p.id, count(oi.id) AS sales_count, min(o.purchased_at) AS first_sold_at
    FROM catalog_product p
    LEFT JOIN orders_orderitem oi ON oi.product_id = p.id
    LEFT JOIN orders_order o ON o.id = oi.order_id
    GROUP BY p.id
) v
WHERE p.id = v.id
  AND (p.sales_count, p.first_sold_at) IS DISTINCT FROM (v.sales_count, v.first_sold_at)
"""

# A review counts once per product it covers: DISTINCT on the Olist review ID, because one
# review can be attached to several orders (one Review row per order).
RATINGS_SQL = """
UPDATE catalog_product p
SET rating_avg = v.rating_avg, rating_count = v.rating_count
FROM (
    SELECT p.id, round(avg(pr.score), 2) AS rating_avg, count(pr.review_ext) AS rating_count
    FROM catalog_product p
    LEFT JOIN (
        SELECT DISTINCT oi.product_id, r.external_id AS review_ext, r.score
        FROM orders_review r
        JOIN orders_orderitem oi ON oi.order_id = r.order_id
    ) pr ON pr.product_id = p.id
    GROUP BY p.id
) v
WHERE p.id = v.id
  AND (p.rating_avg, p.rating_count) IS DISTINCT FROM (v.rating_avg, v.rating_count)
"""

MIN_PRICE_SQL = """
UPDATE catalog_product p
SET min_price = v.min_price
FROM (
    SELECT p.id, min(ofr.price) FILTER (WHERE ofr.stock > 0) AS min_price
    FROM catalog_product p
    LEFT JOIN catalog_offer ofr ON ofr.product_id = p.id
    GROUP BY p.id
) v
WHERE p.id = v.id AND p.min_price IS DISTINCT FROM v.min_price
"""

# Name weighs most (A); category names (English and Portuguese) help as B.
SEARCH_VECTOR_SQL = """
UPDATE catalog_product p
SET search_vector = v.vector
FROM (
    SELECT p.id,
           setweight(to_tsvector('english', p.name), 'A')
           || setweight(to_tsvector('english',
                  coalesce(replace(c.name_english, '_', ' '), '') || ' '
                  || coalesce(replace(c.name, '_', ' '), '')), 'B') AS vector
    FROM catalog_product p
    LEFT JOIN catalog_category c ON c.id = p.category_id
) v
WHERE p.id = v.id AND p.search_vector IS DISTINCT FROM v.vector
"""


@dataclass
class StatsResult:
    offers_written: int
    offers_created: int
    offers_total: int
    products_changed: dict[str, int]


def refresh_offers_and_stats() -> StatsResult:
    """Derive offers from order items, then refresh every denormalised Product column.

    Call inside a transaction (the importer does) so readers never see half-refreshed stats.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM catalog_offer")
        before = cursor.fetchone()[0]
        cursor.execute(OFFERS_SQL)
        offers_written = cursor.rowcount
        cursor.execute("SELECT count(*) FROM catalog_offer")
        after = cursor.fetchone()[0]

        changed = {}
        for label, sql in (
            ("sales", SALES_SQL),
            ("ratings", RATINGS_SQL),
            ("min_price", MIN_PRICE_SQL),
            ("search", SEARCH_VECTOR_SQL),
        ):
            cursor.execute(sql)
            changed[label] = cursor.rowcount
    return StatsResult(offers_written, after - before, after, changed)
