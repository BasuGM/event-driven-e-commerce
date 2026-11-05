import type { StaffEventFilters } from "@/lib/api/server"

/** The staff event list's URL search params <-> API filters (the only translation layer). */

export const ALL_TYPES = "all"
const DATE = /^\d{4}-\d{2}-\d{2}$/

/** URL search params -> API filters (invalid values are dropped). */
export function parseEventFilters(params: Record<string, string | string[] | undefined>): StaffEventFilters {
  const one = (key: string) => {
    const value = params[key]
    return (Array.isArray(value) ? value[0] : value)?.trim() || undefined
  }
  const filters: StaffEventFilters = {}
  const type = one("type")
  if (type && type !== ALL_TYPES) filters.type = type
  const aggregate = one("aggregate_id")
  if (aggregate) filters.aggregate_id = aggregate
  for (const key of ["date_from", "date_to"] as const) {
    const value = one(key)
    if (value && DATE.test(value)) filters[key] = value
  }
  const page = Number(one("page"))
  if (Number.isInteger(page) && page > 1) filters.page = page
  return filters
}

export function staffEventsHref(filters: StaffEventFilters, page = 1): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries({ ...filters, page: page > 1 ? page : undefined })) {
    if (value !== undefined) params.set(key, String(value))
  }
  const query = params.toString()
  return query ? `/staff/events?${query}` : "/staff/events"
}

/** True if the URL carries empty or default-valued params (e.g. from submitting the filter
 * form with blank fields): the page redirects to the clean URL. */
export function hasEmptyParams(params: Record<string, string | string[] | undefined>): boolean {
  return Object.entries(params).some(([key, value]) => {
    const first = Array.isArray(value) ? value[0] : value
    return first === undefined || first.trim() === "" || (key === "type" && first === ALL_TYPES)
  })
}
