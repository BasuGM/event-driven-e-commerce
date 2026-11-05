import { CheckCircle2, Clock } from "lucide-react"
import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"
import { Suspense } from "react"

import { EventPayload } from "@/components/staff/event-payload"
import { StaffHeader } from "@/components/staff/staff-header"
import { StaffSkeleton } from "@/components/staff/staff-skeleton"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { getStaffOrderTimeline, orLogin } from "@/lib/api/server"
import { formatDateTime } from "@/lib/format"

export const metadata: Metadata = { title: "Order events · Staff" }

export default function StaffOrderEventsPage({ params }: PageProps<"/staff/orders/[id]">) {
  return (
    <Suspense fallback={<StaffSkeleton />}>
      <StaffOrderEvents params={params} />
    </Suspense>
  )
}

async function StaffOrderEvents({ params }: { params: PageProps<"/staff/orders/[id]">["params"] }) {
  const { id } = await params
  const events = await orLogin(() => getStaffOrderTimeline(id), `/staff/orders/${id}`)
  if (events === null) notFound()

  return (
    <div className="space-y-6">
      <StaffHeader
        active={null}
        title={`Order ${id.slice(0, 8)}`}
        description="Every event for this order, oldest first, and which consumers have processed it."
      />
      <p className="font-mono text-xs text-muted-foreground">{id}</p>
      {events.length === 0 ? (
        <div className="rounded-lg border border-dashed py-12 text-center text-sm text-muted-foreground">
          No events logged for this order (unknown id, or older than 90 days).{" "}
          <Link href="/staff/events" className="underline underline-offset-4">
            All events
          </Link>
        </div>
      ) : (
        <ol className="space-y-4" aria-label="Order events">
          {events.map((event) => (
            <li key={event.event_id}>
              <Card>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Badge variant="secondary">{event.type}</Badge>
                    <time dateTime={event.occurred_at} className="text-xs tabular-nums text-muted-foreground">
                      {formatDateTime(event.occurred_at)}
                    </time>
                  </div>
                  <ul className="flex flex-wrap gap-2" aria-label="Consumers">
                    {event.consumers.map((consumer) => (
                      <li key={consumer.name}>
                        <Badge
                          variant={consumer.processed_at ? "success" : "outline"}
                          title={consumer.processed_at ? `Processed ${formatDateTime(consumer.processed_at)}` : "Not processed yet"}
                        >
                          {consumer.processed_at ? <CheckCircle2 aria-hidden /> : <Clock aria-hidden />}
                          {consumer.name}
                          <span className="sr-only">{consumer.processed_at ? " processed" : " pending"}</span>
                        </Badge>
                      </li>
                    ))}
                  </ul>
                  <p className="font-mono text-xs text-muted-foreground">{event.event_id}</p>
                  <EventPayload payload={event.payload} />
                </CardContent>
              </Card>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
