import createClient from "openapi-fetch"

import type { components, paths } from "./schema"

export type Stats = components["schemas"]["Stats"]
export type Health = components["schemas"]["Health"]
export type Category = components["schemas"]["Category"]
export type CategoryRef = components["schemas"]["CategoryRef"]
export type ProductListItem = components["schemas"]["ProductList"]
export type ProductDetail = components["schemas"]["ProductDetail"]
export type Offer = components["schemas"]["Offer"]
export type ProductReview = components["schemas"]["ProductReview"]
export type ProductPage = components["schemas"]["PaginatedProductListList"]
export type ReviewPage = components["schemas"]["PaginatedProductReviewList"]
export type CategoryGroup = CategoryRef["group"]
export type Me = components["schemas"]["Me"]
export type User = components["schemas"]["User"]
export type Cart = components["schemas"]["Cart"]
export type CartLine = components["schemas"]["CartLine"]
export type OrderDetail = components["schemas"]["OrderDetail"]
export type Shipping = components["schemas"]["Shipping"]
export type OrderListItem = components["schemas"]["OrderList"]
export type OrderPage = components["schemas"]["PaginatedOrderListList"]
export type OrderStatus = components["schemas"]["OrderStatusEnum"]
export type DomainError = components["schemas"]["DomainError"]
export type ShippingAddress = components["schemas"]["ShippingAddressRequest"]

/**
 * Typed API client for Server Components. `API_URL` is server-only (it points at the
 * backend container inside Docker), so the browser never talks to Django directly yet.
 */
export const api = createClient<paths>({
  baseUrl: process.env.API_URL ?? "http://localhost:8000",
})

export const TIMEOUT_MS = 5000

/** Thrown when the backend doesn't answer within TIMEOUT_MS. */
export class BackendTimeoutError extends Error {
  name = "BackendTimeoutError"
}

/**
 * Run an API call with a TIMEOUT_MS abort signal.
 *
 * fetch rejects an aborted request with a DOMException, whose `message` is read-only; Next's
 * error handling tries to rewrite it and crashes with an unhandledRejection, so rethrow a plain
 * Error. (Not an openapi-fetch middleware: middleware makes it call Math.random() per request,
 * which Next's cacheComponents prerender check rejects.)
 */
export async function withTimeout<T>(label: string, call: (signal: AbortSignal) => Promise<T>): Promise<T> {
  try {
    return await call(AbortSignal.timeout(TIMEOUT_MS))
  } catch (error) {
    // Only our own timeout becomes BackendTimeoutError. An AbortError means someone else
    // cancelled the request (e.g. Next aborting a prerender pass): let it propagate unchanged.
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new BackendTimeoutError(`Backend did not respond within ${TIMEOUT_MS} ms (${label})`, { cause: error })
    }
    throw error
  }
}

export async function getStats(): Promise<Stats> {
  const { data, error } = await withTimeout("stats", (signal) => api.GET("/api/stats/", { signal }))
  if (!data) throw new Error(`Failed to load stats: ${JSON.stringify(error)}`)
  return data
}

/** Health answers 503 with the same body when a dependency is down, so both are data. */
export async function getHealth(): Promise<Health> {
  const { data, error } = await withTimeout("health", (signal) => api.GET("/api/health/", { signal }))
  const body = data ?? error
  if (!body) throw new Error("Empty health response")
  return body
}
