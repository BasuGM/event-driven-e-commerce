import { notFound, redirect } from "next/navigation"
import { Suspense } from "react"

import { PageLinks } from "@/components/shop/page-links"
import { EventFilters } from "@/components/staff/event-filters"
import { EventsTable } from "@/components/staff/events-table"
import { StaffHeader } from "@/components/staff/staff-header"
import { StaffSkeleton } from "@/components/staff/staff-skeleton"
import { getStaffEvents, getStaffEventTypes, orLogin } from "@/lib/api/server"
import { hasEmptyParams, parseEventFilters, staffEventsHref } from "@/lib/staff-params"
import { formatInteger } from "@/lib/format"


/** Static shell; the request-time part (and the staff header) renders inside Suspense. */
export default function StaffEventsPage({ searchParams }: PageProps<"/staff/events">) {
  return (
    <Suspense fallback={<StaffSkeleton />}>
      <StaffEvents searchParams={searchParams} />
    </Suspense>
  )
}

const PAGE_SIZE = 50
async function StaffEvents({ searchParams }: { searchParams: PageProps<"/staff/events">["searchParams"] }) {
  const raw = await searchParams
  const filters = parseEventFilters(raw)
  // An empty filter form field still submits (`aggregate_id=&date_from=`): keep URLs clean
  if (hasEmptyParams(raw)) redirect(staffEventsHref(filters, filters.page))
  const [types, events] = await orLogin(
    () => Promise.all([getStaffEventTypes(), getStaffEvents(filters)]),
    "/staff/events",
  )
  if (types === null || events === null) notFound()

  return (
    <div className="space-y-6">
      <StaffHeader active="/staff/events" title="Events" description="Every domain event, newest first (kept 90 days)." />
      <EventFilters types={types} filters={filters} />
      <p className="text-sm text-muted-foreground" aria-live="polite">
        {formatInteger(events.count)} {events.count === 1 ? "event" : "events"}
      </p>
      {events.results.length === 0 ? (
        <div className="rounded-lg border border-dashed py-12 text-center text-sm text-muted-foreground">
          No events match these filters.
        </div>
      ) : (
        <div className="rounded-xl border">
          <EventsTable events={events.results} />
        </div>
      )}
      <PageLinks
        label="Event pages"
        page={filters.page ?? 1}
        totalPages={Math.ceil(events.count / PAGE_SIZE)}
        hrefFor={(n) => staffEventsHref(filters, n)}
      />
    </div>
  )
}
