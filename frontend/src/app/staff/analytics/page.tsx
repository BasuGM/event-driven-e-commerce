import { notFound } from "next/navigation"
import { Suspense } from "react"

import { AnalyticsFilters } from "@/components/analytics/analytics-filters"
import { AutoRefresh } from "@/components/analytics/auto-refresh"
import { CategoryChart, DeliveryChart, RevenueChart, StateChart } from "@/components/analytics/charts"
import { KpiCards } from "@/components/analytics/kpi-cards"
import { StaffHeader } from "@/components/staff/staff-header"
import { StaffSkeleton } from "@/components/staff/staff-skeleton"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { parseAnalyticsParams, SOURCE_LABELS } from "@/lib/analytics-params"
import { getStaffAnalytics, orLogin } from "@/lib/api/server"


/** Static shell; the data (and the staff header) render inside Suspense after the staff check. */
export default function StaffAnalyticsPage({ searchParams }: PageProps<"/staff/analytics">) {
  return (
    <Suspense fallback={<StaffSkeleton />}>
      <StaffAnalytics searchParams={searchParams} />
    </Suspense>
  )
}

async function StaffAnalytics({ searchParams }: { searchParams: PageProps<"/staff/analytics">["searchParams"] }) {
  const filters = parseAnalyticsParams(await searchParams)
  const data = await orLogin(() => getStaffAnalytics(filters), "/staff/analytics")
  if (data === null) notFound()

  return (
    <div className="space-y-6">
      <StaffHeader
        active="/staff/analytics"
        title="Analytics"
        description={`${SOURCE_LABELS[data.source]}, by purchase day. Updates every 10 s while open.`}
      />
      <AutoRefresh />
      <AnalyticsFilters
        key={`${data.source}-${data.date_from}-${data.date_to}`}
        filters={filters}
        shown={{ from: data.date_from, to: data.date_to }}
        lastDay={data.last_day}
      />
      {data.kpis.orders === 0 ? (
        <div className="rounded-lg border border-dashed py-16 text-center text-sm text-muted-foreground">
          No orders in this range for this source.
        </div>
      ) : (
        <>
          <KpiCards kpis={data.kpis} />
          <Card>
            <CardHeader>
              <CardTitle>Revenue over time</CardTitle>
              <CardDescription>GMV per purchase day (paid orders)</CardDescription>
            </CardHeader>
            <CardContent>
              <RevenueChart daily={data.daily} />
            </CardContent>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Revenue by category</CardTitle>
                <CardDescription>Item prices, top 10</CardDescription>
              </CardHeader>
              <CardContent>
                <CategoryChart rows={data.by_category} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>GMV by customer state</CardTitle>
                <CardDescription>Where the orders ship</CardDescription>
              </CardHeader>
              <CardContent>
                <StateChart rows={data.by_state} />
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Delivery performance</CardTitle>
              <CardDescription>Average days from purchase to delivery, and the share delivered late, per week</CardDescription>
            </CardHeader>
            <CardContent>
              {data.delivery_by_week.length === 0 ? (
                <p className="text-sm text-muted-foreground">No delivered orders in this range.</p>
              ) : (
                <DeliveryChart weeks={data.delivery_by_week} />
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
