/**
 * The shop's URL search params are the single source of truth for filters, search, sort and
 * page. This module is the only translation layer between the URL and typed filters.
 */

export const ORDERINGS = ["popular", "price", "-price", "rating", "newest"] as const
export type ShopOrdering = (typeof ORDERINGS)[number]

export const ORDERING_LABELS: Record<ShopOrdering, string> = {
  popular: "Most popular",
  price: "Price: low to high",
  "-price": "Price: high to low",
  rating: "Top rated",
  newest: "Newest",
}

export type ShopFilters = {
  category?: string
  q?: string
  minPrice?: string
  maxPrice?: string
  minRating?: number
  inStock?: boolean
  ordering?: ShopOrdering
  page?: number
}

type ParamSource = URLSearchParams | Record<string, string | string[] | undefined>

const PRICE = /^\d{1,10}(\.\d{1,2})?$/
const SLUG = /^[a-z0-9-]{1,100}$/

function read(source: ParamSource, key: string): string | undefined {
  const raw = source instanceof URLSearchParams ? source.get(key) : source[key]
  const value = Array.isArray(raw) ? raw[0] : raw
  const trimmed = value?.trim()
  return trimmed ? trimmed : undefined
}

/** Parse URL params into filters, silently dropping anything invalid. */
export function parseShopParams(source: ParamSource): ShopFilters {
  const filters: ShopFilters = {}
  const category = read(source, "category")
  if (category && SLUG.test(category)) filters.category = category
  const q = read(source, "q")
  if (q) filters.q = q.slice(0, 100)
  const minPrice = read(source, "min_price")
  if (minPrice && PRICE.test(minPrice)) filters.minPrice = minPrice
  const maxPrice = read(source, "max_price")
  if (maxPrice && PRICE.test(maxPrice)) filters.maxPrice = maxPrice
  // An inverted range is kept (not silently fixed) so the page and the price form can both show
  // the same error the form gives when you type it; see priceRangeError.
  const minRating = Number(read(source, "min_rating"))
  if (Number.isInteger(minRating) && minRating >= 1 && minRating <= 5) filters.minRating = minRating
  if (read(source, "in_stock") === "true") filters.inStock = true
  const ordering = read(source, "ordering")
  if (ordering && (ORDERINGS as readonly string[]).includes(ordering)) {
    filters.ordering = ordering as ShopOrdering
  }
  const page = Number(read(source, "page"))
  if (Number.isInteger(page) && page > 1) filters.page = page
  return filters
}

/** Serialise filters to URL params in a stable order, omitting defaults. */
export function toSearchParams(filters: ShopFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.q) params.set("q", filters.q)
  if (filters.category) params.set("category", filters.category)
  if (filters.minPrice) params.set("min_price", filters.minPrice)
  if (filters.maxPrice) params.set("max_price", filters.maxPrice)
  if (filters.minRating) params.set("min_rating", String(filters.minRating))
  if (filters.inStock) params.set("in_stock", "true")
  // "popular" is the default only without a search (searching defaults to relevance)
  if (filters.ordering && (filters.ordering !== "popular" || filters.q)) {
    params.set("ordering", filters.ordering)
  }
  if (filters.page && filters.page > 1) params.set("page", String(filters.page))
  return params
}

export function shopHref(filters: ShopFilters): string {
  const query = toSearchParams(filters).toString()
  return query ? `/shop?${query}` : "/shop"
}

/** Apply a change. Anything other than a page change sends you back to page 1. */
export function updateFilters(current: ShopFilters, patch: Partial<ShopFilters>): ShopFilters {
  const next = { ...current, ...patch }
  if (!("page" in patch)) delete next.page
  for (const key of Object.keys(next) as (keyof ShopFilters)[]) {
    if (next[key] === undefined || next[key] === "" || next[key] === false) delete next[key]
  }
  return next
}

/** The price form's rule, shared with URL handling: min must not exceed max. */
export function priceRangeError(range: Pick<ShopFilters, "minPrice" | "maxPrice">): string | null {
  const { minPrice, maxPrice } = range
  if (minPrice && maxPrice && Number(minPrice) > Number(maxPrice)) return "Minimum must not exceed maximum."
  return null
}

export function hasActiveFilters(filters: ShopFilters): boolean {
  return Boolean(
    filters.category || filters.q || filters.minPrice || filters.maxPrice || filters.minRating ||
      filters.inStock,
  )
}

/** Filters -> /api/products/ query (snake_case, as the API expects). */
export function toApiQuery(filters: ShopFilters, pageSize = 24) {
  return {
    category: filters.category,
    q: filters.q,
    min_price: filters.minPrice,
    max_price: filters.maxPrice,
    min_rating: filters.minRating === undefined ? undefined : String(filters.minRating),
    in_stock: filters.inStock ? true : undefined,
    ordering: filters.ordering,
    page: filters.page,
    page_size: pageSize,
  }
}
