import { describe, expect, it } from "vitest"

import { analyticsHref, formatDays, formatPercent, parseAnalyticsParams, presets, shiftDate } from "./analytics-params"

describe("analytics params", () => {
  it("parses the URL, dropping invalid values", () => {
    expect(parseAnalyticsParams({ source: "olist", from: "2017-11-01", to: "2017-11-30" })).toEqual({
      source: "olist", date_from: "2017-11-01", date_to: "2017-11-30",
    })
    expect(parseAnalyticsParams({ source: "nope", from: "yesterday" })).toEqual({ source: "olist" })
    expect(parseAnalyticsParams({ from: "2018-01-02", to: "2018-01-01" })).toEqual({ source: "olist", date_from: "2018-01-02" })
  })

  it("round-trips through the URL and omits defaults", () => {
    const filters = { source: "replay" as const, date_from: "2017-11-20", date_to: "2017-11-30" }
    expect(analyticsHref(filters)).toBe("/staff/analytics?source=replay&from=2017-11-20&to=2017-11-30")
    expect(parseAnalyticsParams(Object.fromEntries(new URL(`http://x${analyticsHref(filters)}`).searchParams))).toEqual(filters)
    expect(analyticsHref({ source: "olist" })).toBe("/staff/analytics")  // the default
    expect(analyticsHref({ source: "all" })).toBe("/staff/analytics?source=all")
  })

  it("builds presets relative to the newest data", () => {
    expect(shiftDate("2018-03-01", -1)).toBe("2018-02-28")
    expect(presets("2018-09-26").map((p) => [p.from, p.to])).toEqual([
      [undefined, undefined], ["2018-06-29", "2018-09-26"], ["2018-08-28", "2018-09-26"],
    ])
    expect(presets(null)).toHaveLength(1)
  })

  it("formats rates and durations", () => {
    expect(formatPercent(0.0712)).toBe("7.1%")
    expect(formatPercent(null)).toBe("–")
    expect(formatDays(12.6)).toBe("12.6 days")
  })
})
