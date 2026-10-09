import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"

import { StatsCards } from "./stats-cards"

describe("StatsCards", () => {
  it("renders a labelled, formatted count for each stat", () => {
    render(<StatsCards stats={{ products: 1234, orders: 2000, customers: 1987, sellers: 45 }} />)

    expect(screen.getByText("Products")).toBeInTheDocument()
    expect(screen.getByText("1,234")).toBeInTheDocument()
    expect(screen.getByText("Orders")).toBeInTheDocument()
    expect(screen.getByText("2,000")).toBeInTheDocument()
    expect(screen.getByText("Customers")).toBeInTheDocument()
    expect(screen.getByText("1,987")).toBeInTheDocument()
    expect(screen.getByText("Sellers")).toBeInTheDocument()
    expect(screen.getByText("45")).toBeInTheDocument()
    expect(screen.queryByText("No data yet")).not.toBeInTheDocument()
  })

  it("shows the empty state when every count is zero", () => {
    render(<StatsCards stats={{ products: 0, orders: 0, customers: 0, sellers: 0 }} />)

    expect(screen.getByText("No data yet")).toBeInTheDocument()
    expect(screen.queryByText("Orders")).not.toBeInTheDocument()
  })
})
