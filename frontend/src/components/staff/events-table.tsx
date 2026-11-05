import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { StaffEvent } from "@/lib/api/client"
import { formatDateTime } from "@/lib/format"

import { EventPayload } from "./event-payload"

export function AggregateLink({ type, id }: { type: string; id: string }) {
  if (type !== "order") return <span className="font-mono text-xs break-all">{id}</span>
  return (
    <Link href={`/staff/orders/${id}`} className="font-mono text-xs underline-offset-4 hover:underline">
      {id.slice(0, 8)}…
    </Link>
  )
}

export function EventsTable({ events }: { events: StaffEvent[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Occurred</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Aggregate</TableHead>
          <TableHead className="w-full">Details</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((event) => (
          <TableRow key={event.event_id} className="align-top">
            <TableCell className="whitespace-nowrap text-xs tabular-nums">{formatDateTime(event.occurred_at)}</TableCell>
            <TableCell>
              <Badge variant="secondary">{event.type}</Badge>
            </TableCell>
            <TableCell>
              <span className="text-xs text-muted-foreground">{event.aggregate_type} </span>
              <AggregateLink type={event.aggregate_type} id={event.aggregate_id} />
            </TableCell>
            <TableCell className="whitespace-normal">
              <p className="font-mono text-xs text-muted-foreground">{event.event_id}</p>
              <EventPayload payload={event.payload} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
