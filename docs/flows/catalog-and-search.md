# Catalog and search

The storefront lets anyone browse by category, filter by price, rating and stock, search by
name, and open a product to compare sellers' offers. The catalog endpoints are public. They
read only denormalised, indexed columns, so a listing never aggregates order data at request
time.

## What the visitor sees

- **`/shop`** is the listing: category, price range, minimum rating, in-stock-only, search box,
  sort order and pagination.
  - Everything is in the URL, so a filtered view can be shared or reloaded.
  - A stale or invalid link shows the API's 400 messages instead of an error page.
- **`/shop/<slug>`** is the product page: the generated description, dimensions, every seller's
  offer (cheapest first, each marked in stock or not), and the reviews.

## Backend

### Endpoints and validation

- **Endpoints.** `GET /api/categories/`, `/api/products/`, `/api/products/{slug}/` and
  `/api/products/{slug}/reviews/` are in
  [backend/apps/catalog/views.py](../../backend/apps/catalog/views.py).
- **No session work at all.** They set `authentication_classes = []`, not just
  `permission_classes`, so a catalog request never reads the session or user tables.
- **Validated parameters.** Query parameters go through `ProductListQuerySerializer` in
  [filters.py](../../backend/apps/catalog/filters.py) before any query runs:
  - an unknown category slug, a negative price, a rating outside 1–5, `max_price < min_price`,
    or an unknown ordering is a 400 with a message per field;
  - the same serializer documents the parameters in OpenAPI.

  Parameter reference: [api.md](../api.md#catalog-backendappscatalog).

### Filtering on denormalised columns

`filter_products()` filters on columns of `catalog_product` only:

| Filter | Column | Why it works |
|---|---|---|
| `min_price` / `max_price` | `min_price` | The cheapest offer **with stock**, maintained by `MIN_PRICE_SQL` |
| `in_stock=true` / `false` | `min_price IS NOT NULL` / `IS NULL` | `min_price` is null exactly when no offer has stock |
| `min_rating` | `rating_avg` | Each review counted once per product |
| `category` | `category_id` | |
| ordering | `sales_count`, `min_price`, `rating_avg`, `first_sold_at` | Each has a B-tree index |

How these columns are computed is in [olist-import.md](olist-import.md#offers-prices-and-stock).
Keeping them current as orders happen is the job of the order flow
([cart-checkout-stock.md](cart-checkout-stock.md)) and the `product_stats` consumer
([event-pipeline.md](event-pipeline.md)).

Every ordering ends with `id`. When sort keys tie, which is common for `sales_count = 0`, rows
still have a stable order, so pages never overlap or skip products.

### Search

Search uses Postgres full-text search, not a separate search engine:

- **The vector.** `Product.search_vector` is a stored `tsvector` with a GIN index
  (`product_search_gin`). It's built by `SEARCH_VECTOR_SQL`: the product name with weight A,
  plus the category's English and Portuguese names with weight B.
- **Prefix matching.** `prefix_search_query()` turns `duv cov` into the tsquery
  `duv:* & cov:*`, so a word can be matched by its start while the visitor is still typing.
  - Only `\w+` word characters reach `to_tsquery`, so punctuation can't produce a syntax error.
  - A query of only punctuation is simply ignored
    (`test_search_ignores_punctuation_only_query`).
- **Ranking.** With a search term and no explicit ordering, results are ranked by `SearchRank`,
  so a name match beats a category match
  (`test_search_ranks_name_matches_above_category_matches`). An explicit ordering wins over
  relevance.

**Why Postgres FTS instead of a dedicated engine.**
- **It's fast enough.** The catalog is small (1,732 products in the small seed), and GIN-indexed
  full-text search handles it comfortably.
- **Nothing extra to run or sync.** It adds no service and no separate index: the vector is
  refreshed by the same SQL as the other stats.
- **Consistent results.** Results are transactionally consistent with prices and stock.
- **The deferred upgrade** is Meilisearch, for typo tolerance and faceting, once catalog size or
  search quality demands it.

### Product detail and reviews

- **Product detail.** One query for the product and its category, plus one prefetch for the
  offers with their sellers, cheapest first.
- **Offers don't expose stock numbers**, only `in_stock`
  (`test_detail_has_offers_cheapest_first_without_stock_numbers`).
- **Reviews** come from orders that contain the product. One Olist review can be attached to
  several orders, and an order can contain the product twice. So the query uses
  `DISTINCT ON` the review, and shows each review once, newest first.

Query counts are pinned:
- the list takes 2 queries, or 3 with a category filter;
- detail takes 2, reviews 3 and categories 1.

The source is [test_catalog_api.py](../../backend/tests/test_catalog_api.py).

## Frontend

### URL as the single source of truth

[frontend/src/lib/shop-params.ts](../../frontend/src/lib/shop-params.ts) is the only place that
translates between URL search parameters and typed `ShopFilters`:
- `parseShopParams()` reads the URL and drops anything invalid;
- `toSearchParams()` and `shopHref()` build links;
- `toApiQuery()` builds the API request.

Filter controls never hold their own state: they navigate to a new URL. Back/forward, reloads
and shared links therefore all reproduce the same view. Pages that read `searchParams` sit
under a `<Suspense>` boundary or a `loading.tsx`, as `cacheComponents` requires.

### What is cached and what isn't

[frontend/src/lib/api/catalog.ts](../../frontend/src/lib/api/catalog.ts):

| Fetch | Cached? | Why |
|---|---|---|
| `getProducts()` (listing) | No | Filter combinations are unbounded, and stock must be fresh |
| `getCategories()` | No | Cheap (1 query), and changes only on import |
| `getProduct(slug)` (detail) | Yes: `"use cache"`, `cacheLife({ stale: 60, revalidate: 300, expire: 3600 })` | A product page is the same for everyone, and read far more often than it changes |
| `getProductReviews()` | No | Rendered in its own `<Suspense>` below the cached part |

The cached detail carries two cache tags from
[frontend/src/lib/cache-tags.ts](../../frontend/src/lib/cache-tags.ts):
- `product:<slug>`, from `productTag(slug)`;
- `products`, from `ALL_PRODUCTS`. Nothing sends this tag today. It's a lever for a bulk
  revalidation.

### Invalidation when stock or sales change

A cached product page must not show an offer as in stock after it sold out. Invalidation is
event-driven:

1. **An order changes stock.** Checkout, payment, cancel or expiry records an order event in the
   same transaction.
2. **The `product_stats` consumer recomputes.** It recomputes `sales_count` and `min_price` for
   the products on that order. Then, **in the same transaction**, it records a
   `ProductsChanged` event with their slugs
   ([product_stats.py](../../backend/apps/events/consumers/product_stats.py)).
3. **The `cache_invalidation` consumer posts the tags.** It reads `ProductsChanged` and POSTs
   `{"tags": ["product:<slug>", …]}` to the frontend's `/internal/revalidate`, with the header
   `x-revalidate-secret` ([revalidate.py](../../backend/apps/events/revalidate.py)).
4. **The frontend route drops the entries.** The route
   [app/internal/revalidate/route.ts](../../frontend/src/app/internal/revalidate/route.ts):
   - compares the secret with `timingSafeEqual`;
   - accepts only tags matching `REVALIDATABLE_TAG`;
   - calls `revalidateTag(tag, { expire: 0 })`.

   `expire: 0` means the stale entry is never served again: the next visit fetches fresh data.

Chaining through `ProductsChanged` guarantees that the cache is dropped only **after** the new
stats are committed.

**If the frontend is down:**
1. The HTTP call fails, the consumer's transaction rolls back, and the event stays pending.
   Revalidating twice is harmless.
2. A pending entry is reclaimed and retried once it has been idle for `EVENTS_CLAIM_IDLE_MS`
   (60 s).
3. After `EVENTS_MAX_DELIVERIES` (5) failed attempts, the next delivery moves it to the
   dead-letter stream `events:dlq` instead of running it again. Staff can retry it from
   `/staff/health` ([staff-tools.md](staff-tools.md)).
4. Until then, the time-based setting `revalidate: 300` is the backstop. A product page whose
   cache entry is older than 5 minutes is refreshed in the background on its next visit.

The route lives outside `/api` on purpose. `next.config.ts` rewrites `/api/*` to Django, and this
endpoint is for the backend containers, not for browsers.

The **listing** needs none of this. It's never cached, and `min_price` is refreshed right after
each order commit ([cart-checkout-stock.md](cart-checkout-stock.md)), so the in-stock filter is
correct immediately. Only the cached product page waits the few seconds the consumer chain
takes.

## Guarantees and limits

- **Fresh where it matters.** The listing's prices and in-stock filter are fresh on every
  request. The product page is fresh within seconds of a stock change, or within 5 minutes
  (`revalidate: 300`) if the event chain is down.
- **One database, no sync.** Search results come from the same database as everything else, so
  there's nothing to keep in sync.
- **Search isn't fuzzy.** Prefix matching handles partial words, but not typos.

## Sources

- [backend/apps/catalog/views.py](../../backend/apps/catalog/views.py), [filters.py](../../backend/apps/catalog/filters.py), [serializers.py](../../backend/apps/catalog/serializers.py), [stats.py](../../backend/apps/catalog/stats.py), [models.py](../../backend/apps/catalog/models.py)
- [backend/apps/events/consumers/product_stats.py](../../backend/apps/events/consumers/product_stats.py), [cache_invalidation.py](../../backend/apps/events/consumers/cache_invalidation.py), [revalidate.py](../../backend/apps/events/revalidate.py)
- [frontend/src/lib/api/catalog.ts](../../frontend/src/lib/api/catalog.ts), [frontend/src/lib/shop-params.ts](../../frontend/src/lib/shop-params.ts), [frontend/src/lib/cache-tags.ts](../../frontend/src/lib/cache-tags.ts), [frontend/src/app/internal/revalidate/route.ts](../../frontend/src/app/internal/revalidate/route.ts)
- Tests: [test_catalog_api.py](../../backend/tests/test_catalog_api.py), [test_offers_stats.py](../../backend/tests/test_offers_stats.py)
