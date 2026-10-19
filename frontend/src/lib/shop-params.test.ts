import { describe, expect, it } from "vitest"

import { parseShopParams, priceRangeError, shopHref, toApiQuery, toSearchParams, updateFilters } from "./shop-params"

describe("shop params", () => {
  it("round-trips every filter through the URL", () => {
    const filters = {
      q: "duvet cover",
      category: "bed-bath-table",
      minPrice: "10",
      maxPrice: "99.90",
      minRating: 4,
      inStock: true,
      ordering: "price" as const,
      page: 3,
    }
    expect(parseShopParams(toSearchParams(filters))).toEqual(filters)
    expect(shopHref(filters)).toBe(
      "/shop?q=duvet+cover&category=bed-bath-table&min_price=10&max_price=99.90&min_rating=4&in_stock=true&ordering=price&page=3",
    )
  })

  it("drops invalid values instead of failing", () => {
    expect(
      parseShopParams(
        new URLSearchParams(
          "category=Bad Slug!&min_price=abc&max_price=-5&min_rating=9&in_stock=yes&ordering=cheapest&page=0",
        ),
      ),
    ).toEqual({})
  })

  it("keeps an inverted price range and flags it like the price form does", () => {
    const filters = parseShopParams(new URLSearchParams("min_price=50&max_price=10"))
    expect(filters).toEqual({ minPrice: "50", maxPrice: "10" })
    expect(priceRangeError(filters)).toBe("Minimum must not exceed maximum.")
    expect(priceRangeError({ minPrice: "10", maxPrice: "50" })).toBeNull()
    expect(priceRangeError({ minPrice: "50" })).toBeNull()
  })

  it("accepts Next's searchParams object shape", () => {
    expect(parseShopParams({ category: ["toys", "auto"], q: "  ball  " })).toEqual({ category: "toys", q: "ball" })
  })

  it("omits defaults so URLs stay short", () => {
    expect(shopHref({})).toBe("/shop")
    expect(shopHref({ ordering: "popular", page: 1 })).toBe("/shop")
    // ...but keeps an explicit "popular" while searching (searching defaults to relevance)
    expect(shopHref({ q: "lamp", ordering: "popular" })).toBe("/shop?q=lamp&ordering=popular")
  })

  it("resets the page when any filter changes, but not when paging", () => {
    const current = { category: "toys", page: 4 }
    expect(updateFilters(current, { inStock: true })).toEqual({ category: "toys", inStock: true })
    expect(updateFilters(current, { page: 5 })).toEqual({ category: "toys", page: 5 })
    expect(updateFilters(current, { category: undefined })).toEqual({})
  })

  it("maps filters to the API's snake_case query", () => {
    expect(toApiQuery({ minRating: 3, inStock: true, page: 2 })).toMatchObject({
      min_rating: "3",
      in_stock: true,
      page: 2,
      page_size: 24,
    })
  })
})
