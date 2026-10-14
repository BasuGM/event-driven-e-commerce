import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { CartSummary } from "./cart-summary"
import { lineWarningText } from "./line-warning"

describe("CartSummary", () => {
  it("shows API totals in BRL without re-adding them in JS", () => {
    render(<CartSummary totals={{ item_count: 3, subtotal: "1234.50", freight_total: "22.50", total: "1257.00" }} />)

    expect(screen.getByText("Items (3 units)")).toBeInTheDocument()
    expect(screen.getByText("R$ 1.234,50")).toBeInTheDocument()
    expect(screen.getByText("R$ 22,50")).toBeInTheDocument()
    expect(screen.getByTestId("cart-total")).toHaveTextContent("R$ 1.257,00")
  })

  it("uses the singular for one unit", () => {
    render(<CartSummary totals={{ item_count: 1, subtotal: "10.00", freight_total: "0.00", total: "10.00" }} />)
    expect(screen.getByText("Items (1 unit)")).toBeInTheDocument()
  })
})

describe("line warnings", () => {
  it("explains what blocks checkout", () => {
    expect(lineWarningText({ warning: "out_of_stock", available: 0 })).toMatch(/Out of stock/)
    expect(lineWarningText({ warning: "insufficient_stock", available: 2 })).toBe(
      "Only 2 left. Lower the quantity to check out.",
    )
    expect(lineWarningText({ warning: null, available: 5 })).toBeNull()
  })
})
