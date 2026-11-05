import { describe, expect, it } from "vitest"

import { hasEmptyParams, parseEventFilters, staffEventsHref } from "./staff-params"

describe("staff event filters", () => {
  it("keeps valid filters and drops the rest", () => {
    expect(
      parseEventFilters({ type: "OrderPaid", aggregate_id: " abc ", date_from: "2026-11-01", date_to: "nope", page: "3" }),
    ).toEqual({ type: "OrderPaid", aggregate_id: "abc", date_from: "2026-11-01", page: 3 })
    expect(parseEventFilters({ type: "all", page: "1", date_to: "" })).toEqual({})
  })

  it("round-trips through the URL", () => {
    const filters = { type: "OrderPaid", date_from: "2026-11-01" }
    expect(staffEventsHref(filters, 2)).toBe("/staff/events?type=OrderPaid&date_from=2026-11-01&page=2")
    expect(parseEventFilters(Object.fromEntries(new URL(`http://x${staffEventsHref(filters, 2)}`).searchParams))).toEqual({
      ...filters,
      page: 2,
    })
    expect(staffEventsHref({})).toBe("/staff/events")
  })
})

describe("empty params", () => {
  it("flags blank fields and the default type so the page can redirect to the clean URL", () => {
    expect(hasEmptyParams({ type: "all", aggregate_id: "", date_from: "", date_to: "" })).toBe(true)
    expect(hasEmptyParams({ type: "OrderPaid", aggregate_id: "  " })).toBe(true)
    expect(hasEmptyParams({ type: "OrderPaid", date_from: "2026-11-01" })).toBe(false)
    expect(hasEmptyParams({})).toBe(false)
  })
})
