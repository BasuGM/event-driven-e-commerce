import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { ProductListItem } from "@/lib/api/client"

import { ProductCard } from "./product-card"

const base: ProductListItem = {
  slug: "soft-percale-duvet-cover-set-1e9e8ef0",
  name: "Soft Percale Duvet Cover Set",
  category: { slug: "bed-bath-table", label: "Bed Bath Table", group: "textiles" },
  image_url: null,
  min_price: "1234.5",
  in_stock: true,
  rating_avg: "4.50",
  rating_count: 12,
}

describe("ProductCard", () => {
  it("shows name, category, BRL price and links to the product", () => {
    render(<ProductCard product={base} />)

    expect(screen.getByRole("link", { name: base.name })).toHaveAttribute("href", `/shop/${base.slug}`)
    expect(screen.getByText("Bed Bath Table")).toBeInTheDocument()
    // pt-BR currency: thousands ".", decimals ",". Intl puts a non-breaking space after R$,
    // which Testing Library's default normaliser turns into a plain space before matching.
    expect(screen.getByText("R$ 1.234,50")).toBeInTheDocument()
    expect(screen.queryByText("Out of stock")).not.toBeInTheDocument()
  })

  it("shows the star rating with its review count", () => {
    render(<ProductCard product={base} />)

    expect(screen.getByRole("img", { name: "Rated 4.5 out of 5 from 12 reviews" })).toBeInTheDocument()
    expect(screen.getByText("(12)")).toBeInTheDocument()
  })

  it("marks out-of-stock products and shows them as unavailable", () => {
    render(<ProductCard product={{ ...base, in_stock: false, min_price: null }} />)

    expect(screen.getByText("Out of stock")).toBeInTheDocument()
    expect(screen.getByText("Unavailable")).toBeInTheDocument()
  })

  it("handles products with no category and no reviews", () => {
    render(<ProductCard product={{ ...base, category: null, rating_avg: null, rating_count: 0 }} />)

    expect(screen.getByText("Uncategorised")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "No ratings yet" })).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "Product image placeholder" })).toBeInTheDocument()
  })
})
