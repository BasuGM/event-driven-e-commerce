import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import createClient from "openapi-fetch"

import { loginHref } from "@/lib/urls"

import {
  withTimeout,
  type Cart,
  type Me,
  type OrderDetail,
  type OrderPage,
  type Shipping,
  type StaffEventPage,
  type StaffHealth,
  type StaffTimelineEvent,
} from "./client"
import type { paths } from "./schema"

/** Thrown when the backend says we're not logged in (401). Pages turn it into a redirect. */
export class NotAuthenticatedError extends Error {
  name = "NotAuthenticatedError"
}

/**
 * Typed client for Server Components acting *as the visitor*: forwards the incoming request's
 * cookies (session) to Django. Reading cookies makes the caller dynamic, so keep it under
 * <Suspense> / loading.tsx and never inside "use cache".
 */
async function asVisitor() {
  const cookieHeader = (await cookies()).toString()
  return createClient<paths>({
    baseUrl: process.env.API_URL ?? "http://localhost:8000",
    headers: cookieHeader ? { cookie: cookieHeader } : {},
  })
}

export async function getMe(): Promise<Me> {
  const api = await asVisitor()
  const { data } = await withTimeout("me", (signal) => api.GET("/api/auth/me/", { signal }))
  return data ?? { user: null, cart_count: 0 }
}

function check(response: Response, label: string): never {
  if (response.status === 401) throw new NotAuthenticatedError(label)
  throw new Error(`Failed to load ${label} (${response.status})`)
}

export async function getCart(): Promise<Cart> {
  const api = await asVisitor()
  const { data, response } = await withTimeout("cart", (signal) => api.GET("/api/cart/", { signal }))
  return data ?? check(response, "cart")
}

export async function getOrders(page = 1): Promise<OrderPage> {
  const api = await asVisitor()
  const { data, response } = await withTimeout("orders", (signal) =>
    api.GET("/api/orders/", { params: { query: { page } }, signal }),
  )
  if (data) return data
  if (response.status === 404) return { count: 0, next: null, previous: null, results: [] }
  return check(response, "orders")
}

/** null for an unknown order or someone else's (the API answers 404 for both). */
export async function getOrder(id: string): Promise<OrderDetail | null> {
  const api = await asVisitor()
  const { data, response } = await withTimeout(`order ${id}`, (signal) =>
    api.GET("/api/orders/{order_id}/", { params: { path: { order_id: id } }, signal }),
  )
  if (data) return data
  if (response.status === 404) return null
  return check(response, "order")
}

/** Shipping address of the visitor's most recent order (orders list newest first), or null. */
export async function getLastShipping(): Promise<Shipping | null> {
  const latest = (await getOrders(1)).results[0]
  if (!latest) return null
  return (await getOrder(latest.id))?.shipping ?? null
}

/** Load protected data; a 401 becomes a redirect to /login?next=<path>. */
export async function orLogin<T>(load: () => Promise<T>, path: string): Promise<T> {
  try {
    return await load()
  } catch (error) {
    if (error instanceof NotAuthenticatedError) redirect(loginHref(path))
    throw error
  }
}

// --- staff (event explorer) --------------------------------------------------------------------
// The API answers 404 to anyone who isn't staff, so null here means "not for you": the page
// calls notFound() and the staff tools stay invisible.

export type StaffEventFilters = { type?: string; aggregate_id?: string; date_from?: string; date_to?: string; page?: number }

export async function getStaffEvents(filters: StaffEventFilters): Promise<StaffEventPage | null> {
  const api = await asVisitor()
  const { data, response } = await withTimeout("staff events", (signal) =>
    api.GET("/api/staff/events/", { params: { query: filters }, signal }),
  )
  if (data) return data
  if (response.status === 404 && filters.page && filters.page > 1) {
    return { count: 0, next: null, previous: null, results: [] } // a page past the end
  }
  if (response.status === 404) return null
  if (response.status === 400) return { count: 0, next: null, previous: null, results: [] }
  throw new Error(`Failed to load events (${response.status})`)
}

export async function getStaffEventTypes(): Promise<string[] | null> {
  const api = await asVisitor()
  const { data, response } = await withTimeout("staff event types", (signal) =>
    api.GET("/api/staff/events/types/", { signal }),
  )
  if (data) return data
  if (response.status === 404) return null
  throw new Error(`Failed to load event types (${response.status})`)
}

export async function getStaffOrderTimeline(orderId: string): Promise<StaffTimelineEvent[] | null> {
  const api = await asVisitor()
  const { data, response } = await withTimeout(`staff timeline ${orderId}`, (signal) =>
    api.GET("/api/staff/orders/{order_id}/events/", { params: { path: { order_id: orderId } }, signal }),
  )
  if (data) return data
  if (response.status === 404) return null
  throw new Error(`Failed to load the order's events (${response.status})`)
}

export async function getStaffHealth(): Promise<StaffHealth | null> {
  const api = await asVisitor()
  const { data, response } = await withTimeout("staff health", (signal) => api.GET("/api/staff/health/", { signal }))
  if (data) return data
  if (response.status === 404) return null
  throw new Error(`Failed to load event health (${response.status})`)
}
