/**
 * Idempotency keys for checkout, from the browser's side.
 *
 * One "attempt" = one key, bound to a fingerprint of what's being bought (cart lines + address).
 * - Retrying after a network error / timeout / 5xx reuses the key: if the first request did
 *   reach the server, the retry replays that order instead of creating a second one.
 * - A definitive answer (2xx, or a 4xx like out-of-stock or invalid address) ends the attempt.
 * - Changing the cart or the address starts a new attempt (the server would 409 a reused key
 *   with a different body).
 * The attempt survives a reload via sessionStorage (per tab).
 */

export type Attempt = { key: string; fingerprint: string }

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">

const STORAGE_KEY = "checkout-attempt"

/**
 * 32 random hex chars. Not crypto.randomUUID(): that only exists in secure contexts (HTTPS or
 * localhost), so it throws for anyone on plain HTTP via another host name (LAN IP, e2e browser).
 */
export function newIdempotencyKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")
}

/** Stable JSON: object keys sorted, so equal content gives an equal string. */
export function fingerprint(value: unknown): string {
  return JSON.stringify(value, (_key, v) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)))
      : v,
  )
}

export function currentAttempt(
  store: Store,
  print: string,
  newKey: () => string = newIdempotencyKey,
): Attempt {
  const saved = store.getItem(STORAGE_KEY)
  if (saved) {
    try {
      const attempt = JSON.parse(saved) as Attempt
      if (attempt.fingerprint === print && attempt.key) return attempt
    } catch {
      // corrupted entry: start a new attempt
    }
  }
  const attempt = { key: newKey(), fingerprint: print }
  store.setItem(STORAGE_KEY, JSON.stringify(attempt))
  return attempt
}

/** status 0 = the request never got an answer (network error, timeout). */
export function isRetryable(status: number): boolean {
  return status === 0 || status >= 500
}

/** Call after every response: ends the attempt unless the outcome is unknown. */
export function settleAttempt(store: Store, status: number): void {
  if (!isRetryable(status)) store.removeItem(STORAGE_KEY)
}
