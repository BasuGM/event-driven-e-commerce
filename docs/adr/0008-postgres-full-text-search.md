# 0008. Postgres full-text search over a search engine

- **Status:** Accepted
- **Date:** 2026-10-13 (commit `73666d8`, Step 2)

## Context

The storefront needs product search as you type, combined with the shop's filters (category,
price, rating, stock) and its sort orders. Products have generated English names and Olist
categories in Portuguese and English.

## Options considered

1. **A dedicated engine** (Meilisearch, Elasticsearch, Typesense). These offer typo tolerance,
   faceting and relevance tuning. They're another service, plus an index to keep in sync with
   prices, stock and names.
2. **`ILIKE '%…%'`.** No ranking and no stemming, and it can't use a normal index.
3. **Postgres full-text search.** A stored `tsvector` with a GIN index, prefix `tsquery`
   matching, and `SearchRank`.

## Decision

Postgres FTS:
- **The vector.** `Product.search_vector` combines the name (weight A) and the category names
  (weight B, English and Portuguese). It's refreshed by the same set-based SQL as the other
  product stats.
- **Matching and ranking.** Queries become prefix matches (`duv:* & cov:*`), ranked by relevance
  unless the visitor picks a sort.

Why:
- **It's fast enough.** The catalog is small (1,732 products), and GIN-indexed full-text search
  is fast enough for it.
- **Nothing extra to run or sync.** It adds no extra service and no index to keep in sync.
- **Consistent results.** Results stay transactionally consistent with prices and stock.

## Consequences

- **Search and filters are one SQL query**, so pagination and counts are exact.
- **No typo tolerance and no faceting.** Prefix matching handles partial words, but not
  misspellings.
- **The deferred upgrade** is Meilisearch (typo tolerance, faceting), once catalog size or search
  quality demands it. The catalog API's contract (`q` plus filters) wouldn't need to change.

## Links

- [docs/flows/catalog-and-search.md](../flows/catalog-and-search.md)
- [backend/apps/catalog/filters.py](../../backend/apps/catalog/filters.py) (`prefix_search_query`), [backend/apps/catalog/stats.py](../../backend/apps/catalog/stats.py) (`SEARCH_VECTOR_SQL`)
- Tests: `test_search_matches_word_prefixes_in_name`, `test_search_ranks_name_matches_above_category_matches`
