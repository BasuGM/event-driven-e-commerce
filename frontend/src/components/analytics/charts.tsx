"use client"

import { Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts"

import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import type { AnalyticsDashboard } from "@/lib/api/client"
import { formatBRL, formatDate } from "@/lib/format"

// No animation: the dashboard re-renders every 10 s (AutoRefresh), and charts would redraw
// themselves each time.
// Money arrives as decimal strings: numbers only for drawing, BRL strings for display
const brl = (value: unknown) => formatBRL(Number(value))
const compactBrl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", notation: "compact" })

const revenueConfig = { gmv: { label: "GMV", color: "var(--chart-1)" } } satisfies ChartConfig

const DAY_MS = 86_400_000
export const GAP_DAYS = 31

/**
 * Daily points on a time-proportional axis. Wherever consecutive days are more than GAP_DAYS
 * apart (e.g. Olist history ends in 2018, app orders start in 2026) a null point breaks the
 * area, so the gap shows as a gap instead of a line drawn across it.
 */
export function revenueSeries(daily: AnalyticsDashboard["daily"]) {
  const points: { ts: number; gmv: number | null }[] = []
  for (const d of daily) {
    const ts = Date.parse(`${d.day}T00:00:00Z`)
    const previous = points.at(-1)
    if (previous && ts - previous.ts > GAP_DAYS * DAY_MS) points.push({ ts: previous.ts + DAY_MS, gmv: null })
    points.push({ ts, gmv: Number(d.gmv) })
  }
  return points
}

const isoDay = (ts: number) => new Date(ts).toISOString().slice(0, 10)

export function RevenueChart({ daily }: { daily: AnalyticsDashboard["daily"] }) {
  const data = revenueSeries(daily)
  return (
    <ChartContainer config={revenueConfig} className="h-64 w-full">
      <AreaChart data={data} margin={{ left: 8, right: 16 }}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="ts" type="number" scale="time" domain={["dataMin", "dataMax"]}
          tickLine={false} axisLine={false} minTickGap={48} tickFormatter={(ts) => formatDate(isoDay(ts))}
        />
        <YAxis tickLine={false} axisLine={false} width={64} tickFormatter={(v) => compactBrl.format(v)} />
        <ChartTooltip
          content={<ChartTooltipContent labelFormatter={(_, p) => formatDate(isoDay(p?.[0]?.payload.ts))} formatter={(v) => brl(v)} />}
        />
        <Area isAnimationActive={false} dataKey="gmv" type="monotone" fill="var(--color-gmv)" fillOpacity={0.25} stroke="var(--color-gmv)" />
      </AreaChart>
    </ChartContainer>
  )
}

const categoryConfig = { revenue: { label: "Revenue", color: "var(--chart-2)" } } satisfies ChartConfig

/** The top categories as bars; the API's "other" bucket becomes a note, not a giant bar. */
export function CategoryChart({ rows }: { rows: AnalyticsDashboard["by_category"] }) {
  const data = rows.filter((r) => r.slug !== "other").map((r) => ({ label: r.label, revenue: Number(r.revenue) }))
  const other = rows.find((r) => r.slug === "other")
  return (
    <div className="space-y-2">
      <ChartContainer config={categoryConfig} className="h-80 w-full">
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
          <CartesianGrid horizontal={false} />
          <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(v) => compactBrl.format(v)} />
          <YAxis type="category" dataKey="label" tickLine={false} axisLine={false} width={150} />
          <ChartTooltip content={<ChartTooltipContent formatter={(v) => brl(v)} />} />
          <Bar isAnimationActive={false} dataKey="revenue" fill="var(--color-revenue)" radius={4} />
        </BarChart>
      </ChartContainer>
      {other && (
        <p className="text-xs text-muted-foreground">
          +{other.label.replace(/^Other \((\d+) categories\)$/, "$1 categories")}, {brl(other.revenue)}
        </p>
      )}
    </div>
  )
}

const stateConfig = { gmv: { label: "GMV", color: "var(--chart-3)" } } satisfies ChartConfig
export const TOP_STATES = 10

/** Top states by GMV plus one "Other" bar (rows arrive sorted by GMV, descending). */
export function stateSeries(rows: AnalyticsDashboard["by_state"]) {
  const top = rows.slice(0, TOP_STATES).map((r) => ({ state: r.state, gmv: Number(r.gmv) }))
  const rest = rows.slice(TOP_STATES)
  if (rest.length) {
    top.push({ state: `Other (${rest.length})`, gmv: rest.reduce((sum, r) => sum + Number(r.gmv), 0) })
  }
  return top
}

export function StateChart({ rows }: { rows: AnalyticsDashboard["by_state"] }) {
  const data = stateSeries(rows)
  return (
    <ChartContainer config={stateConfig} className="h-80 w-full">
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(v) => compactBrl.format(v)} />
        <YAxis type="category" dataKey="state" tickLine={false} axisLine={false} width={72} interval={0} />
        <ChartTooltip content={<ChartTooltipContent formatter={(v) => brl(v)} />} />
        <Bar isAnimationActive={false} dataKey="gmv" fill="var(--color-gmv)" radius={4} />
      </BarChart>
    </ChartContainer>
  )
}

// Distinct hues for the two series: a blue line (days) over translucent orange bars (late %)
const deliveryConfig = {
  avg_days: { label: "Avg days", color: "var(--chart-1)" },
  late_pct: { label: "Late %", color: "var(--chart-4)" },
} satisfies ChartConfig

export function DeliveryChart({ weeks }: { weeks: AnalyticsDashboard["delivery_by_week"] }) {
  const data = weeks.map((w) => ({
    week: w.week,
    avg_days: w.avg_days,
    late_pct: w.late_share === null ? null : Math.round(w.late_share * 1000) / 10,
  }))
  return (
    <ChartContainer config={deliveryConfig} className="h-64 w-full">
      <ComposedChart data={data} margin={{ left: 8, right: 8 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="week" tickLine={false} axisLine={false} minTickGap={40} tickFormatter={(d) => formatDate(d)} />
        <YAxis yAxisId="days" tickLine={false} axisLine={false} width={40} />
        <YAxis yAxisId="pct" orientation="right" tickLine={false} axisLine={false} width={40} unit="%" />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => `Week of ${formatDate(p?.[0]?.payload.week)}`} />} />
        <Bar isAnimationActive={false} yAxisId="pct" dataKey="late_pct" fill="var(--color-late_pct)" fillOpacity={0.45} radius={3} />
        <Line isAnimationActive={false} yAxisId="days" dataKey="avg_days" type="monotone" stroke="var(--color-avg_days)" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ChartContainer>
  )
}
