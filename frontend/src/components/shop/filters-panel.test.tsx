import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { Category } from "@/lib/api/client"
import type { ShopFilters } from "@/lib/shop-params"

import { FiltersPanel } from "./filters-panel"
import { ShopNavigationProvider } from "./shop-navigation"

const push = vi.fn()
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }))

const categories: Category[] = [
  { slug: "bed-bath-table", label: "Bed Bath Table", group: "textiles", product_count: 156 },
  { slug: "toys", label: "Toys", group: "toys", product_count: 61 },
]

function renderPanel(filters: ShopFilters) {
  return render(
    <ShopNavigationProvider filters={filters}>
      <FiltersPanel categories={categories} />
    </ShopNavigationProvider>,
  )
}

describe("FiltersPanel ↔ URL", () => {
  beforeEach(() => push.mockClear())

  it("builds category links from the current URL state, resetting the page", () => {
    renderPanel({ q: "lamp", page: 3 })

    expect(screen.getByRole("link", { name: /Toys/ })).toHaveAttribute("href", "/shop?q=lamp&category=toys")
    expect(screen.getByRole("link", { name: "All categories" })).toHaveAttribute("aria-current", "page")
  })

  it("marks the active category from the URL", () => {
    renderPanel({ category: "toys" })

    expect(screen.getByRole("link", { name: /Toys/ })).toHaveAttribute("aria-current", "page")
  })

  it("pushes in_stock to the URL when the switch is turned on", () => {
    renderPanel({ category: "toys", page: 2 })

    fireEvent.click(screen.getByRole("switch", { name: "In stock only" }))

    expect(push).toHaveBeenCalledWith("/shop?category=toys&in_stock=true", { scroll: false })
  })

  it("pushes the price range when the form is submitted", () => {
    renderPanel({})

    fireEvent.change(screen.getByLabelText("Minimum price"), { target: { value: "10" } })
    fireEvent.change(screen.getByLabelText("Maximum price"), { target: { value: "50.5" } })
    fireEvent.submit(screen.getByLabelText("Maximum price").closest("form")!)

    expect(push).toHaveBeenCalledWith("/shop?min_price=10&max_price=50.5", { scroll: false })
  })

  it("applies the price only on submit, not when moving between the inputs", () => {
    renderPanel({})
    const min = screen.getByLabelText("Minimum price")
    const max = screen.getByLabelText("Maximum price")

    fireEvent.change(min, { target: { value: "10" } })
    fireEvent.blur(min)
    fireEvent.change(max, { target: { value: "50" } })
    fireEvent.blur(max)
    expect(push).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole("button", { name: "Apply price" }))
    expect(push).toHaveBeenCalledWith("/shop?min_price=10&max_price=50", { scroll: false })
  })

  it("keeps a typed draft and the focused input when other filters change the URL", () => {
    const { rerender } = renderPanel({})
    const max = screen.getByLabelText("Maximum price")
    max.focus()
    fireEvent.change(max, { target: { value: "75" } })

    rerender(
      <ShopNavigationProvider filters={{ inStock: true }}>
        <FiltersPanel categories={categories} />
      </ShopNavigationProvider>,
    )

    expect(screen.getByLabelText("Maximum price")).toBe(max)
    expect(max).toHaveFocus()
    expect(max).toHaveValue("75")
  })

  it("re-syncs the inputs when the URL's price values change", () => {
    const { rerender } = renderPanel({ minPrice: "10", maxPrice: "50" })
    fireEvent.change(screen.getByLabelText("Minimum price"), { target: { value: "20" } })

    rerender(
      <ShopNavigationProvider filters={{}}>
        <FiltersPanel categories={categories} />
      </ShopNavigationProvider>,
    )

    expect(screen.getByLabelText("Minimum price")).toHaveValue("")
    expect(screen.getByLabelText("Maximum price")).toHaveValue("")
  })

  it("does not push an inverted price range", () => {
    renderPanel({})

    fireEvent.change(screen.getByLabelText("Minimum price"), { target: { value: "90" } })
    fireEvent.change(screen.getByLabelText("Maximum price"), { target: { value: "10" } })
    fireEvent.submit(screen.getByLabelText("Maximum price").closest("form")!)

    expect(push).not.toHaveBeenCalled()
    expect(screen.getByText("Minimum must not exceed maximum.")).toBeInTheDocument()
  })

  it("shows an inverted range from the URL with the form's error", () => {
    renderPanel({ minPrice: "50", maxPrice: "10" })

    expect(screen.getByLabelText("Minimum price")).toHaveValue("50")
    expect(screen.getByLabelText("Maximum price")).toHaveValue("10")
    expect(screen.getByText("Minimum must not exceed maximum.")).toBeInTheDocument()
  })

  it("clears filters but keeps the sort order", () => {
    renderPanel({ category: "toys", inStock: true, ordering: "price" })

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }))

    expect(push).toHaveBeenCalledWith("/shop?ordering=price", { scroll: false })
  })
})
