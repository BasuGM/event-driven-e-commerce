/** The analytics dashboard's URL search params <-> filters (the only translation layer). */

export const SOURCES = ["all", "olist", "app", "replay"] as const
export type AnalyticsSource = (typeof SOURCES)[number]
export type AnalyticsFilters = { source: AnalyticsSource; date_from?: string; date_to?: string }

/** The first view: the imported history (one day of app test orders would flatten "all"). */
export const DEFAULT_SOURCE: AnalyticsSource = "olist"

export const SOURCE_LABELS: Record<AnalyticsSource, string> = {
  all: "All sources",
  olist: "Imported (Olist)",
  app: "Placed in the app",
  replay: "Replayed",
}

const DATE = /^\d{4}-\d{2}-\d{2}$/

export function parseAnalyticsParams(params: Record<string, string | string[] | undefined>): AnalyticsFilters {
  const one = (key: string) => {
    const value = params[key]
    return (Array.isArray(value) ? value[0] : value)?.trim() || undefined
  }
  const source = one("source")
  const filters: AnalyticsFilters = {
    source: (SOURCES as readonly string[]).includes(source ?? "") ? (source as AnalyticsSource) : DEFAULT_SOURCE,
  }
  const from = one("from")
  const to = one("to")
  if (from && DATE.test(from)) filters.date_from = from
  if (to && DATE.test(to)) filters.date_to = to
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
    delete filters.date_to
  }
  return filters
}

export function analyticsHref(filters: AnalyticsFilters): string {
  const params = new URLSearchParams()
  if (filters.source !== DEFAULT_SOURCE) params.set("source", filters.source)
  if (filters.date_from) params.set("from", filters.date_from)
  if (filters.date_to) params.set("to", filters.date_to)
  const query = params.toString()
  return query ? `/staff/analytics?${query}` : "/staff/analytics"
}

/** "2018-09-26" minus n days, as an ISO date (calendar arithmetic in UTC: no DST shifts). */
export function shiftDate(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

/** Ranges relative to the newest data (Olist data ends in 2018, app orders are recent). */
export function presets(lastDay: string | null) {
  if (!lastDay) return [{ label: "All data", from: undefined, to: undefined }]
  return [
    { label: "All data", from: undefined, to: undefined },
    { label: "Last 90 days of data", from: shiftDate(lastDay, -89), to: lastDay },
    { label: "Last 30 days of data", from: shiftDate(lastDay, -29), to: lastDay },
  ]
}

export function formatPercent(rate: number | null): string {
  return rate === null ? "–" : `${(rate * 100).toFixed(1)}%`
}

export function formatDays(days: number | null): string {
  return days === null ? "–" : `${days.toFixed(1)} days`
}
