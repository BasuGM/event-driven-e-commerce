# PostgreSQL

The relational database: every order, offer, event and projection lives here. PostgreSQL 17
(image `postgres:17`), reached from Django through psycopg 3.3. Official docs:
[postgresql.org/docs/17](https://www.postgresql.org/docs/17/).

## Connection settings

Django's PostgreSQL backend reads the same `POSTGRES_*` variables the container is configured
with; compose service names make `POSTGRES_HOST=db` work between containers.

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "ecommerce"),
        …
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
    }
}
```

Source: [settings/base.py](../../backend/config/settings/base.py), `DATABASES`.

## Money as `NUMERIC`, time as `timestamptz`

`DecimalField(max_digits=12, decimal_places=2)` is `numeric(12,2)`: exact, never a float. With
`USE_TZ = True` every datetime is stored as `timestamptz` in UTC; Olist's Sao Paulo times are
converted on import.

```python
TIME_ZONE = "UTC"
…
USE_TZ = True
```

Source: [settings/base.py](../../backend/config/settings/base.py). More:
[money-as-decimals](../concepts/money-as-decimals.md), [ADR 0010](../adr/0010-money-as-decimal-strings.md).

## `jsonb` columns

`JSONField` maps to `jsonb`. Event payloads and provider payloads are stored as received, so a
reader can see exactly what was sent.

```python
payload = models.JSONField()
```

Source: [events/models.py](../../backend/apps/events/models.py), `OutboxEvent`.

## Unique and check constraints

Constraints make the database the last line of defence. A line is unique per cart and offer, and
its quantity is bounded; a `PositiveIntegerField` also makes Django add `CHECK (stock >= 0)`.

```python
constraints = [
    models.UniqueConstraint(fields=["cart", "offer"], name="uniq_cart_offer"),
    models.CheckConstraint(
        condition=models.Q(quantity__gte=1, quantity__lte=MAX_LINE_QUANTITY),
        name="cart_item_quantity_1_to_10",
    ),
]
```

Source: [cart/models.py](../../backend/apps/cart/models.py), `CartItem.Meta`. More:
[constraints-as-guarantees](../concepts/constraints-as-guarantees.md).

## Partial unique index

A unique index with a `WHERE` condition: only rows in an "open" status compete. One order can
have many finished intents but at most one open one, so two "Pay" clicks reuse it.

```python
models.UniqueConstraint(
    fields=["order"], condition=Q(status__in=["requires_payment", "processing"]),
    name="uniq_open_intent_per_order",
)
```

Source: [payments/models.py](../../backend/apps/payments/models.py), `PaymentIntent.Meta`. More:
[ADR 0006](../adr/0006-payment-intent-vs-ledger.md).

## B-tree and GIN indexes

Plain indexes serve the listing's sort and filter columns; the GIN index serves full-text search.

```python
indexes = [
    GinIndex(fields=["search_vector"], name="product_search_gin"),
    models.Index(fields=["sales_count"], name="product_sales_idx"),
    …
]
```

Source: [catalog/models.py](../../backend/apps/catalog/models.py), `Product.Meta`.

## Transactions

`transaction.atomic()` wraps a unit of work in one transaction; everything commits together or
not at all. The project keeps them short and never makes an HTTP call inside one.

```python
with transaction.atomic(), connection.cursor() as cursor:
    for day in days:  # ascending: the same order everywhere, so no deadlocks
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", […])
```

Source: [analytics/projections.py](../../backend/apps/analytics/projections.py),
`recompute_days`. More: [transactions-and-isolation](../concepts/transactions-and-isolation.md).

## Row locks: `SELECT … FOR UPDATE`

Django's `select_for_update()` becomes `FOR UPDATE`: other transactions wanting the same rows
wait. Ordering by id makes every transaction lock overlapping rows in the same order, which is
what prevents deadlocks.

```python
def lock_offers(offer_ids) -> dict[int, Offer]:
    offers = Offer.objects.select_for_update().filter(id__in=set(offer_ids)).order_by("id")
    return {offer.id: offer for offer in offers}
```

Source: [orders/services.py](../../backend/apps/orders/services.py), `lock_offers`. More:
[row-locks-and-skip-locked](../concepts/row-locks-and-skip-locked.md),
[lock-ordering-and-deadlocks](../concepts/lock-ordering-and-deadlocks.md),
[ADR 0015](../adr/0015-stock-reserved-at-checkout-under-row-locks.md).

## `SKIP LOCKED`

Instead of waiting on a locked row, skip it. The relay, the reservation sweeper and the email
sender use it so several copies can run side by side without picking the same row.

```python
order = (
    Order.objects.select_for_update(skip_locked=skip_locked, of=("self",))
    .filter(pk=order_id)
    .first()
)
```

Source: [orders/services.py](../../backend/apps/orders/services.py), `lock_order`
(`of=("self",)` locks only the order row, not joined tables).

## Conditional `UPDATE` as a one-shot switch

`UPDATE … WHERE status='active'` changes a row only if it is still in the expected state, and
reports how many rows it changed. Two racing callers: exactly one gets `1`.

```python
flipped = Reservation.objects.filter(pk=reservation.pk, status=Reservation.Status.ACTIVE).update(
    status=status, resolved_at=now
)
if flipped and status == Reservation.Status.RELEASED:
    Offer.objects.filter(pk=reservation.offer_id).update(stock=F("stock") + reservation.quantity)
```

Source: [orders/services.py](../../backend/apps/orders/services.py), `_resolve_reservations`.
`F("stock") + n` makes the database do the arithmetic, so no stale read is written back.

## Upsert: `INSERT … ON CONFLICT DO UPDATE`

Re-importing the same CSVs must not duplicate rows. `bulk_create(update_conflicts=True)` is
Django's spelling of an upsert on the natural key.

```python
spec.model.objects.bulk_create(
    batch,
    update_conflicts=True,
    unique_fields=spec.unique_fields,
    update_fields=spec.update_fields,
)
```

Source: [core/olist_import.py](../../backend/apps/core/olist_import.py), `_flush`. More:
[idempotency](../concepts/idempotency.md), [olist-import](../flows/olist-import.md).

## Set-based SQL with CTEs and ordered-set aggregates

Product offers are computed by one statement over all order items. The median price is exact
(`numeric`): the mean of the lower and upper middle values, because `percentile_cont` would go
through floating point. The upsert's `WHERE … IS DISTINCT FROM` skips rows that wouldn't change.

```sql
round(
    (percentile_disc(0.5) WITHIN GROUP (ORDER BY oi.price)
     + percentile_disc(0.5) WITHIN GROUP (ORDER BY oi.price DESC)) / 2,
    2
) AS price,
…
ON CONFLICT (product_id, seller_id) DO UPDATE
    SET price = EXCLUDED.price, freight = EXCLUDED.freight
    WHERE (catalog_offer.price, catalog_offer.freight)
        IS DISTINCT FROM (EXCLUDED.price, EXCLUDED.freight)
```

Source: [catalog/stats.py](../../backend/apps/catalog/stats.py), `OFFERS_SQL`. More:
[projections-and-read-models](../concepts/projections-and-read-models.md).

## Deterministic synthetic data in SQL

Olist has no stock, so the importer derives it from `md5` of the two IDs inside Postgres: the
same offer always gets the same stock, about 10 % of offers get 0.

```python
_HASH_SQL = "('x' || substr(md5({product_ext} || {seller_ext}), 1, 7))::bit(28)::int"
STOCK_SQL = (
    "CASE WHEN {h} % 10 = 0 THEN 0 ELSE 1 + ({h} / 10) % 50 END"
)
```

Source: [catalog/stats.py](../../backend/apps/catalog/stats.py), `STOCK_SQL`.

## Full-text search

A `tsvector` column, weighted (name `A`, category `B`) and indexed with GIN, is matched with a
`tsquery`. The search term is turned into a prefix query so "duv cov" finds "duvet cover".

```sql
setweight(to_tsvector('english', p.name), 'A')
|| setweight(to_tsvector('english', coalesce(replace(c.name_english, '_', ' '), '') …), 'B')
```

```python
return SearchQuery(" & ".join(f"{w}:*" for w in words), search_type="raw", config="english")
```

Source: [catalog/stats.py](../../backend/apps/catalog/stats.py), `SEARCH_VECTOR_SQL`;
[catalog/filters.py](../../backend/apps/catalog/filters.py), `prefix_search_query`. More:
[catalog-and-search](../flows/catalog-and-search.md), [ADR 0008](../adr/0008-postgres-full-text-search.md).

## Locking a batch in a fixed order, retrying deadlocks

Product rows are locked by ascending id; SQLSTATE `40P01` (deadlock) and `40001`
(serialization failure) are retried, so a stats refresh can't fail a request that already
committed.

```python
_RETRYABLE_SQLSTATES = {"40P01", "40001"}  # deadlock_detected, serialization_failure

def lock_products(cursor, ids: list[int]) -> None:
    cursor.execute("SELECT id FROM catalog_product WHERE id = ANY(%s) ORDER BY id FOR UPDATE", [ids])
```

Source: [catalog/stats.py](../../backend/apps/catalog/stats.py), `lock_products`.

## Advisory locks

An advisory lock is a named lock the database doesn't tie to any row. `pg_advisory_xact_lock`
holds it until the transaction ends. The analytics recompute takes one per (source, day) so two
recomputes of the same day queue instead of double-inserting.

```python
cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"analytics:{source}:{day.isoformat()}"])
```

Source: [analytics/projections.py](../../backend/apps/analytics/projections.py),
`recompute_days`. More: [coordination-advisory-locks-and-leases](../concepts/coordination-advisory-locks-and-leases.md),
[ADR 0011](../adr/0011-analytics-projections-recompute.md).

## Backup and restore with `pg_dump` / `pg_restore`

Snapshots use the compressed custom format (`-Fc`), so a seeded database can be restored without
re-parsing the CSVs.

```make
snapshot: require-env
	$(DB) pg_dump -U $(POSTGRES_USER) -d $(POSTGRES_DB) -Fc \
		-f /snapshots/$(POSTGRES_DB)-$$(date +%Y%m%d-%H%M%S).dump
```

Source: [Makefile](../../Makefile), target `snapshot`.

## Not used here

- Table partitioning, replication, `LISTEN/NOTIFY` (Redis Pub/Sub does that job), extensions such
  as `pg_trgm` (search is `tsvector` only).
- `SERIALIZABLE` isolation: correctness comes from locks and constraints at the default level.
- Views and stored procedures: all logic lives in Python and plain SQL strings.
