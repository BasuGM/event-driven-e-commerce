# Olist import

The shop is seeded with the real
[Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce):
99,441 orders placed in Brazil between September 2016 and October 2018 (counted from
`olist_orders_dataset.csv`). It contains customers, sellers,
products, order items, payments and reviews. It has no product names, descriptions, prices
or stock, so the importer derives or generates those. This page explains what the importer
does, and why it can be run again safely.

## What you run

```
make seed          # import_olist --size small, then seed_dev_users, then backfill_analytics
make seed-large    # the same with --size large (the whole dataset)
```

The command is `python manage.py import_olist --size small|large [--data-dir DIR]
[--order-count N] [--seed N]`
([import_olist.py](../../backend/apps/core/management/commands/import_olist.py)).

- **Where it reads from.** The CSVs come from `OLIST_DATA_DIR`, which defaults to `/data/olist`
  inside the container. That's the repo's `data/olist/`, mounted read-only.
- **Missing files.** The command stops with a message listing the missing files and the Kaggle
  URL to download them from.

**On 2026-11-09 the small seed in the dev database contained:**
- 2,000 orders and 2,241 order items;
- 1,732 products. 1,709 of them are in one of 63 categories, and 23 have no category.
  The `catalog_category` table holds 71 rows, because every category in Olist's translation file
  is imported, including the 8 with no product in the small sample;
- 795 sellers and 1,751 offers;
- 1,996 reviews.

## Steps

All of this is in [backend/apps/core/olist_import.py](../../backend/apps/core/olist_import.py).

1. **Check that all eight CSVs exist.**
2. **Choose the orders.**
   - `large` reads every row.
   - `small` sorts the order IDs and takes a seeded random sample: 2,000 orders, seed 42.
   - It then keeps only the items, payments, reviews, products, sellers and customers those
     orders reference. So every foreign key resolves, and the same seed always yields the same
     subset, whatever the CSV row order.
3. **Write each table in dependency order:** categories, sellers, products, customers, orders,
   items, payments, reviews. Each table is written in its own transaction, in batches of 2,000.
4. **Derive offers and recompute the product stats** with set-based SQL, in one transaction
   (below).

## Re-running is safe

Every table is written with `bulk_create(update_conflicts=True)`. In Postgres that is
`INSERT … ON CONFLICT (natural key) DO UPDATE`. The natural keys are Olist's own:

| Table | Conflict key |
|---|---|
| Category | `name` (Portuguese) |
| Seller, Product, Customer, Order | `external_id` |
| OrderItem | (`order`, `item_number`) |
| Payment | (`order`, `sequential`) |
| Review | (`external_id`, `order`): one Olist review can cover several orders |

A second run updates rows in place, and never duplicates them
(`test_reimport_is_idempotent`).

One detail matters here. Postgres refuses an `ON CONFLICT DO UPDATE` that touches the same row
twice in one statement. So the importer drops in-file duplicates of the natural key before
writing, and counts them as skipped with the reason "duplicate".

## Messy rows

Each row is validated in Python before it's written. A bad row is skipped, counted by reason,
and logged (at most five rows per reason; after that they're only counted). It never stops the
import. The summary table at the end shows, for each table, rows written, new, in the DB,
skipped by reason, and notes.

- **Skip reasons:**
  - an unknown customer, order, product or seller (a broken reference);
  - an invalid status or payment type;
  - a missing required value, or an unparseable timestamp, date, number or amount;
  - a review score outside 1–5;
  - a missing `customer_unique_id`;
  - a duplicate.
- **Notes** are rows that are kept with a caveat:
  - "no category, imported uncategorised";
  - "no translation, pt name used". Olist's translation file lacks a few categories, such as
    `pc_gamer`, which keep their Portuguese name.

The test fixtures in [backend/tests/fixtures/olist/](../../backend/tests/fixtures/olist/) are
tiny CSVs that deliberately contain these cases:
- `test_skipped_rows_are_counted_by_reason`;
- `test_messy_values`;
- `test_review_shared_by_two_orders_is_kept_once_per_order`.

## Transformations

- **Time zones.** Olist timestamps are Brazilian local time without an offset. They're parsed
  as `America/Sao_Paulo` and stored in UTC (`test_timestamps_converted_from_sao_paulo_to_utc`).
- **Customers.** Olist issues a new `customer_id` for every order. The importer collapses these
  into one `Customer` per `customer_unique_id`, the real person, using the address from their
  latest order. The per-order ID is kept on `Order.olist_customer_id`.
- **Orders** get `source='olist'`, and keep the Olist status, including the historical
  `processing`. The importer writes no `OrderStatusHistory` rows and emits **no events**. It
  isn't the order flow, and replaying 2,000 historical orders through the consumers is what
  [replay](replay.md) is for.

## Generated product text

Olist products are anonymous: an ID, a category and some dimensions. For a usable storefront,
`generate_product_text()` in [backend/apps/catalog/enrichment.py](../../backend/apps/catalog/enrichment.py)
derives a name, slug and description:

- **The random generator is seeded from `sha256(external_id)`**, never the global `random`. The
  same product always gets the same text, regardless of import order or batch size.
- **Each category maps to a group with its own vocabulary.** A name is
  *adjective + material + noun*. The pinned test example is product `1e9e8ef0…` in
  `bed_bath_table`, which becomes "Breathable Percale Throw Blanket", slug
  `breathable-percale-throw-blanket-1e9e8ef0`.
- **The slug is the slugified name plus the first 8 characters of the external ID.** So slugs
  are unique even when two products get the same name (`test_import_generates_unique_slugs`).
- **The description** loosely follows Olist's `product_description_lenght` (sic) and
  mentions the real dimensions when they exist.

`test_generated_text_is_pinned` pins example outputs. Changing a word list renames products and
changes their slugs, which are URLs, so treat it like a data migration.

## Offers, prices and stock

Olist sells through many sellers, so the shop's unit of sale is an **offer**: one seller
selling one product. Offers are derived from order items by `OFFERS_SQL` in
[backend/apps/catalog/stats.py](../../backend/apps/catalog/stats.py):

- **Price and freight are the exact median** of that (product, seller) pair's item prices and
  freight values.
  - The median is computed in `numeric` as the mean of the two middle values.
  - `percentile_cont` would go through `float8`.
- **Stock is synthetic and deterministic.**
  - It's derived from an md5 of the two IDs: one bucket in ten gets 0, the rest 1–50 units.
  - It's set **only when the offer is first created**:
    `ON CONFLICT … DO UPDATE SET price, freight` never touches `stock`.
  - After that, stock belongs to the order flow. A re-seed never undoes a sale
    (`test_reseed_never_overwrites_live_stock`).
- **Replay copies are excluded** (`WHERE o.source <> 'replay'`), so replaying history can't
  move prices.

The same file then recomputes the denormalised product columns. Each is one `UPDATE … FROM`
over every product:

| Statement | Columns | Rule |
|---|---|---|
| `SALES_SQL` | `sales_count`, `first_sold_at` | Units on orders that aren't `canceled`/`unavailable`, excluding replay copies |
| `RATINGS_SQL` | `rating_avg`, `rating_count` | Each Olist review counted once per product (`DISTINCT` on the review ID) |
| `MIN_PRICE_SQL` | `min_price` | Cheapest offer **with stock**; null means sold out |
| `SEARCH_VECTOR_SQL` | `search_vector` | Product name (weight A) + category names in English and Portuguese (weight B) |

Every statement updates only rows whose value actually changes (`IS DISTINCT FROM`). A re-run
on unchanged data therefore writes nothing (`test_reimport_changes_nothing`). The cost is a
handful of statements whatever the data size: no per-row Python.

The order flow reuses the same SQL scoped to a few product IDs
([cart-checkout-stock.md](cart-checkout-stock.md)). `make backfill-sales` re-runs only
`SALES_SQL`. It's for a bulk change to imported data, since the importer emits no events for
consumers to react to.

## Snapshots

Parsing the full dataset is slow, so a seeded database can be saved and restored:

- `make snapshot`: `pg_dump -Fc` into `data/snapshots/`.
- `make restore`: `pg_restore --clean` of the newest dump. **This replaces the current
  database**, so take a snapshot first if it holds anything you want to keep.

Snapshots don't include the Redis event streams. See
[operations/runbook.md](../operations/runbook.md).

## Sources

- [backend/apps/core/olist_import.py](../../backend/apps/core/olist_import.py), [backend/apps/core/management/commands/](../../backend/apps/core/management/commands/)
- [backend/apps/catalog/enrichment.py](../../backend/apps/catalog/enrichment.py), [backend/apps/catalog/stats.py](../../backend/apps/catalog/stats.py)
- [Makefile](../../Makefile) (`seed`, `seed-large`, `snapshot`, `restore`, `backfill-sales`)
- Tests: [test_import_olist.py](../../backend/tests/test_import_olist.py), [test_enrichment.py](../../backend/tests/test_enrichment.py), [test_offers_stats.py](../../backend/tests/test_offers_stats.py)
