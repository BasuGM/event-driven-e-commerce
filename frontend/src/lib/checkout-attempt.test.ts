import { beforeEach, describe, expect, it } from "vitest"

import { currentAttempt, fingerprint, isRetryable, newIdempotencyKey, settleAttempt } from "./checkout-attempt"

function memoryStore() {
  const data = new Map<string, string>()
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  }
}

describe("checkout attempts", () => {
  let store: ReturnType<typeof memoryStore>
  let n: number
  const newKey = () => `key-${++n}`
  const body = fingerprint({ cart: [[1, 2]], shipping: { city: "São Paulo", zip_code: "01310-100" } })

  beforeEach(() => {
    store = memoryStore()
    n = 0
  })

  it("reuses the key while the outcome is unknown (network error, timeout, 5xx)", () => {
    const first = currentAttempt(store, body, newKey)
    for (const status of [0, 500, 502]) {
      settleAttempt(store, status)
      expect(currentAttempt(store, body, newKey).key).toBe(first.key)
    }
  })

  it("starts a new attempt after a definitive answer", () => {
    for (const status of [201, 400, 409]) {
      const before = currentAttempt(store, body, newKey).key
      settleAttempt(store, status)
      expect(currentAttempt(store, body, newKey).key).not.toBe(before)
    }
  })

  it("starts a new attempt when the cart or address changes", () => {
    const first = currentAttempt(store, body, newKey)
    const changed = fingerprint({ cart: [[1, 3]], shipping: { city: "São Paulo", zip_code: "01310-100" } })
    expect(currentAttempt(store, changed, newKey).key).not.toBe(first.key)
  })

  it("fingerprints ignore key order", () => {
    expect(fingerprint({ a: 1, b: { c: 2, d: 3 } })).toBe(fingerprint({ b: { d: 3, c: 2 }, a: 1 }))
  })

  it("survives a corrupted stored value", () => {
    store.setItem("checkout-attempt", "{not json")
    expect(currentAttempt(store, body, newKey).key).toBe("key-1")
  })

  it("classifies statuses", () => {
    expect([0, 500, 503].map(isRetryable)).toEqual([true, true, true])
    expect([200, 201, 400, 401, 409].map(isRetryable)).toEqual([false, false, false, false, false])
  })

  it("generates 32-hex keys without crypto.randomUUID (insecure contexts)", () => {
    const keys = new Set(Array.from({ length: 50 }, newIdempotencyKey))
    expect(keys.size).toBe(50)
    for (const key of keys) expect(key).toMatch(/^[0-9a-f]{32}$/)
  })
})
