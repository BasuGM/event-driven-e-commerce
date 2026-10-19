import { describe, expect, it } from "vitest"

import { quantityOptions } from "./cart-lines"

describe("quantityOptions", () => {
  it("offers 1..available", () => {
    expect(quantityOptions(1, 3)).toEqual(["1", "2", "3"])
  })

  it("never offers more than the per-line maximum", () => {
    expect(quantityOptions(2, 250)).toHaveLength(10)
  })

  it("keeps the current quantity when stock dropped below it", () => {
    expect(quantityOptions(5, 2)).toEqual(["1", "2", "5"])
    expect(quantityOptions(2, 0)).toEqual(["2"])
  })
})
