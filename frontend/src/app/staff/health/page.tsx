import { notFound } from "next/navigation"
import { Suspense } from "react"

import { AggregateLink } from "@/components/staff/events-table"
import { RetryDeadLetter } from "@/components/staff/retry-dead-letter"
import { StaffHeader } from "@/components/staff/staff-header"
import { StaffSkeleton } from "@/components/staff/staff-skeleton"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { getStaffHealth, orLogin } from "@/lib/api/server"
import { formatDateTime, formatInteger } from "@/lib/format"


export default function StaffHealthPage() {
  return (
    <Suspense fallback={<StaffSkeleton />}>
      <StaffHealth />
    </Suspense>
  )
}

/** A Redis stream entry id starts with its creation time in ms. */
function entryTime(entryId: string): string {
  return formatDateTime(new Date(Number(entryId.split("-")[0])).toISOString())
}

async function StaffHealth() {
  const health = await orLogin(() => getStaffHealth(), "/staff/health")
  if (health === null) notFound()
  const { groups, outbox, dead_letters: deadLetters } = health

  return (
    <div className="space-y-6">
      <StaffHeader active="/staff/health" title="Event health" description="Consumer groups, the outbox backlog and dead letters." />

      <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <Card>
          <CardHeader>
            <CardTitle>Consumer groups</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Group</TableHead>
                  <TableHead>Stream</TableHead>
                  <TableHead className="text-right">Consumers</TableHead>
                  <TableHead className="text-right">Pending</TableHead>
                  <TableHead className="text-right">Lag</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {groups.map((g) => (
                  <TableRow key={`${g.stream}/${g.group}`}>
                    <TableCell className="font-medium">
                      {g.group}
                      {!g.exists && (
                        <Badge variant="outline" className="ml-2">
                          not started
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{g.stream}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {g.consumers}
                      {g.inactive_consumers > 0 && (
                        <span className="ml-1 text-xs text-muted-foreground" title="Names left from restarts">
                          (+{g.inactive_consumers} inactive)
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatInteger(g.pending)}</TableCell>
                    <TableCell className="text-right tabular-nums">{g.lag === null ? "–" : formatInteger(g.lag)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Outbox</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <p className="text-2xl font-semibold tabular-nums">{formatInteger(outbox.unpublished)}</p>
            <p className="text-sm text-muted-foreground">
              unpublished
              {outbox.oldest_unpublished_age_seconds !== null && ` · oldest ${outbox.oldest_unpublished_age_seconds}s`}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            Dead letters <span className="font-normal text-muted-foreground">({deadLetters.length})</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {deadLetters.length === 0 ? (
            <p className="text-sm text-muted-foreground">No dead letters. Every event was processed.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dead-lettered</TableHead>
                  <TableHead>Event</TableHead>
                  <TableHead>Consumer</TableHead>
                  <TableHead className="text-right">Deliveries</TableHead>
                  <TableHead>Error</TableHead>
                  <TableHead>
                    <span className="sr-only">Retry</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deadLetters.map((d) => (
                  <TableRow key={d.entry_id} className="align-top">
                    <TableCell className="whitespace-nowrap text-xs tabular-nums">{entryTime(d.entry_id)}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{d.type ?? "?"}</Badge>
                      {d.aggregate_id && (
                        <div className="mt-1">
                          <AggregateLink type={d.stream?.endsWith(":order") ? "order" : "other"} id={d.aggregate_id} />
                        </div>
                      )}
                    </TableCell>
                    <TableCell>{d.consumer}</TableCell>
                    <TableCell className="text-right tabular-nums">{d.deliveries ?? "–"}</TableCell>
                    <TableCell className="max-w-xs whitespace-normal font-mono text-xs text-destructive">{d.error}</TableCell>
                    <TableCell>
                      <RetryDeadLetter entryId={d.entry_id} retriedAt={d.retried_at} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
