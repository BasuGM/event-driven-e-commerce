/**
 * Cache tag names: the single place they're spelled out. The backend's cache_invalidation
 * consumer sends the same strings (apps/events/revalidate.py: product_tag) to
 * POST /internal/revalidate after product data changes.
 *
 * Only product detail is cached; the listing and categories stay dynamic by design, so they
 * have no tags.
 */

export const ALL_PRODUCTS = "products"

export function productTag(slug: string): string {
  return `product:${slug}`
}

/** Tags the revalidate endpoint accepts. */
export const REVALIDATABLE_TAG = /^(?:product:[a-z0-9-]{1,120}|products)$/
