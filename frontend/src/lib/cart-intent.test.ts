import { describe, expect, it } from "vitest"

import { claimIntent, newNonce, parseIntent, withIntent } from "./cart-intent"

describe("cart intent", () => {
  it("round-trips through the return URL", () => {
    const intent = { offerId: 42, quantity: 3, nonce: newNonce() }
    const url = new URL(withIntent("/shop/lamp-1a2b3c4d", intent), "http://x")
    expect(url.pathname).toBe("/shop/lamp-1a2b3c4d")
    expect(parseIntent(url.searchParams.get("add") ?? undefined)).toEqual(intent)
  })

  it("rejects malformed or out-of-range values", () => {
    expect(parseIntent(undefined)).toBeNull()
    expect(parseIntent("42.3")).toBeNull()
    expect(parseIntent("42.0.0123456789abcdef")).toBeNull()
    expect(parseIntent("42.11.0123456789abcdef")).toBeNull()
    expect(parseIntent("x.1.0123456789abcdef")).toBeNull()
  })

  it("claims a nonce only once per tab", () => {
    expect(claimIntent(window.sessionStorage, "0123456789abcdef")).toBe(true)
    expect(claimIntent(window.sessionStorage, "0123456789abcdef")).toBe(false)
    expect(claimIntent(window.sessionStorage, "fedcba9876543210")).toBe(true)
  })
})
