/**
 * Typed client for Client Components. Talks to the same origin (/api/* is proxied to Django by
 * a Next rewrite), so the session cookie travels automatically.
 *
 * CSRF: Django sets a `csrftoken` cookie (GET /api/auth/csrf/); unsafe requests must echo it in
 * X-CSRFToken. We read the cookie on *every* request because Django rotates it at login. This
 * uses openapi-fetch's `fetch` option rather than middleware (middleware calls Math.random()).
 */
import createClient from "openapi-fetch"

import type { DomainError } from "./client"
import type { paths } from "./schema"

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"])

export function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.slice(name.length + 1)) : undefined
}

export const browserApi = createClient<paths>({
  baseUrl: "",
  fetch: (request) => {
    if (!SAFE_METHODS.has(request.method)) {
      request.headers.set("X-CSRFToken", readCookie("csrftoken") ?? "")
    }
    return fetch(request)
  },
})

/** Make sure the csrftoken cookie exists before an unsafe request. */
export async function ensureCsrf(): Promise<void> {
  if (!readCookie("csrftoken")) await fetch("/api/auth/csrf/", { credentials: "same-origin" })
}

export type ApiProblem = {
  status: number
  /** Domain error code (out_of_stock, …) or "validation" / "unauthenticated" / "network" */
  code: string
  message: string
  fieldErrors: Record<string, string[]>
  lines?: DomainError["lines"]
}

/** Turn an error response body into something a form or toast can show. */
export function toProblem(status: number, body: unknown): ApiProblem {
  const data = (body ?? {}) as Record<string, unknown>
  if (status === 401) {
    return { status, code: "unauthenticated", message: "Please log in to continue.", fieldErrors: {} }
  }
  if (typeof data.code === "string" && typeof data.detail === "string") {
    return {
      status,
      code: data.code,
      message: data.detail,
      fieldErrors: {},
      lines: data.lines as ApiProblem["lines"],
    }
  }
  const fieldErrors: Record<string, string[]> = {}
  for (const [field, value] of Object.entries(data)) {
    if (Array.isArray(value)) fieldErrors[field] = value.map(String)
    else if (value && typeof value === "object") {
      // nested serializer errors, e.g. {shipping: {zip_code: [...]}}
      for (const [inner, messages] of Object.entries(value as Record<string, unknown>)) {
        if (Array.isArray(messages)) fieldErrors[inner] = messages.map(String)
      }
    } else if (typeof value === "string") fieldErrors[field] = [value]
  }
  const first = fieldErrors.detail?.[0] ?? fieldErrors.non_field_errors?.[0] ?? Object.values(fieldErrors)[0]?.[0]
  return {
    status,
    code: status === 403 ? "forbidden" : "validation",
    message: first ?? `Something went wrong (${status}).`,
    fieldErrors,
  }
}

export const NETWORK_PROBLEM: ApiProblem = {
  status: 0,
  code: "network",
  message: "Couldn't reach the server. Check your connection and try again.",
  fieldErrors: {},
}
