import createClient from "openapi-fetch"

import type { components, paths } from "./schema"

export type Stats = components["schemas"]["Stats"]
export type Health = components["schemas"]["Health"]

/**
 * Typed API client for Server Components. `API_URL` is server-only (it points at the
 * backend container inside Docker), so the browser never talks to Django directly yet.
 */
export const api = createClient<paths>({
  baseUrl: process.env.API_URL ?? "http://localhost:8000",
})

export const TIMEOUT_MS = 5000

export async function getStats(): Promise<Stats> {
  const { data, error } = await api.GET("/api/stats/", {
    signal: AbortSignal.timeout(TIMEOUT_MS),
  })
  if (!data) throw new Error(`Failed to load stats: ${JSON.stringify(error)}`)
  return data
}

/** Health answers 503 with the same body when a dependency is down, so both are data. */
export async function getHealth(): Promise<Health> {
  const { data, error } = await api.GET("/api/health/", {
    signal: AbortSignal.timeout(TIMEOUT_MS),
  })
  const body = data ?? error
  if (!body) throw new Error("Empty health response")
  return body
}
