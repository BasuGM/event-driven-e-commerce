import { describe, expect, it } from "vitest"

import { GAP_DAYS, revenueSeries, stateSeries, TOP_STATES } from "./charts"

const day = (d: string, gmv = "10.00") => ({ day: d, orders: 1, paid_orders: 1, gmv })

describe("revenueSeries", () => {
  it("is time-proportional and breaks the area across long gaps", () => {
    const points = revenueSeries([day("2018-08-28"), day("2018-08-29", "5.50"), day("2026-11-04")])
    expect(points.map((p) => p.gmv)).toEqual([10, 5.5, null, 10]) // a null breaks the area
    expect(new Date(points[2].ts).toISOString().slice(0, 10)).toBe("2018-08-30")
    expect(points[3].ts - points[1].ts).toBeGreaterThan(GAP_DAYS * 86_400_000)
  })

  it("keeps short gaps continuous", () => {
    expect(revenueSeries([day("2017-11-20"), day("2017-11-25")]).map((p) => p.gmv)).toEqual([10, 10])
  })
})

describe("stateSeries", () => {
  it("labels the top states and folds the rest into one Other bar", () => {
    const rows = Array.from({ length: 13 }, (_, i) => ({ state: `S${i}`, orders: 1, gmv: `${100 - i}.00` }))
    const series = stateSeries(rows)
    expect(series).toHaveLength(TOP_STATES + 1)
    expect(series[0]).toEqual({ state: "S0", gmv: 100 })
    expect(series.at(-1)).toEqual({ state: "Other (3)", gmv: 90 + 89 + 88 })
  })

  it("has no Other bar when there are few states", () => {
    expect(stateSeries([{ state: "SP", orders: 1, gmv: "1.00" }])).toEqual([{ state: "SP", gmv: 1 }])
  })
})
