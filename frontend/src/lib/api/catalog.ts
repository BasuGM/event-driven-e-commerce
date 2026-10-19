import { cacheLife, cacheTag } from "next/cache"

import type { ShopFilters } from "@/lib/shop-params"
import { priceRangeError, toApiQuery } from "@/lib/shop-params"

import { api, withTimeout, type Category, type ProductDetail, type ProductPage, type ReviewPage } from "./client"

export async function getCategories(): Promise<Category[]> {
  const { data, error } = await withTimeout("categories", (signal) => api.GET("/api/categories/", { signal }))
  if (!data) throw new Error(`Failed to load categories: ${JSON.stringify(error)}`)
  return data
}

export type ProductsResult =
  | { status: "ok"; page: ProductPage }
  /** The API rejected the filters (e.g. a stale category slug in a shared link). */
  | { status: "invalid"; errors: Record<string, string[]> }

/** Listing is never cached: filter combinations are unbounded and stock must be fresh. */
export async function getProducts(filters: ShopFilters): Promise<ProductsResult> {
  // Same rule (and message) as the price form, for an inverted range typed into the URL
  const priceError = priceRangeError(filters)
  if (priceError) return { status: "invalid", errors: { max_price: [priceError] } }
  const { data, error, response } = await withTimeout("products", (signal) =>
    api.GET("/api/products/", { params: { query: toApiQuery(filters) }, signal }),
  )
  if (data) return { status: "ok", page: data }
  if (response.status === 404) {
    // A page past the end: show an empty page rather than an error
    return { status: "ok", page: { count: 0, next: null, previous: null, results: [] } }
  }
  if (response.status === 400) return { status: "invalid", errors: error as Record<string, string[]> }
  throw new Error(`Failed to load products (${response.status})`)
}

/**
 * Product detail is cached for a few minutes: it only changes on re-import today, and later on
 * catalog events, which can call revalidateTag(`product:${slug}`) to refresh it immediately.
 * Returns null for an unknown slug so the page can call notFound().
 */
export async function getProduct(slug: string): Promise<ProductDetail | null> {
  "use cache"
  cacheLife({ stale: 60, revalidate: 300, expire: 3600 })
  cacheTag(`product:${slug}`, "products")

  const { data, response } = await withTimeout(`product ${slug}`, (signal) =>
    api.GET("/api/products/{slug}/", { params: { path: { slug } }, signal }),
  )
  if (data) return data
  if (response.status === 404) return null
  throw new Error(`Failed to load product ${slug} (${response.status})`)
}

export async function getProductReviews(slug: string, page = 1): Promise<ReviewPage> {
  const { data, response } = await withTimeout(`reviews ${slug}`, (signal) =>
    api.GET("/api/products/{slug}/reviews/", { params: { path: { slug }, query: { page, page_size: 5 } }, signal }),
  )
  if (data) return data
  if (response.status === 404 || response.status === 400) {
    return { count: 0, next: null, previous: null, results: [] }
  }
  throw new Error(`Failed to load reviews (${response.status})`)
}
