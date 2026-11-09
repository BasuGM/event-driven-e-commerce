import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { AnalyticsDashboard } from "@/lib/api/client"
import { formatDays, formatPercent } from "@/lib/analytics-params"
import { formatBRL, formatInteger } from "@/lib/format"

export function KpiCards({ kpis }: { kpis: AnalyticsDashboard["kpis"] }) {
  const cards = [
    { label: "Orders", value: formatInteger(kpis.orders), note: `${formatInteger(kpis.paid_orders)} paid` },
    { label: "GMV", value: formatBRL(kpis.gmv), note: "Items + freight, paid orders" },
    { label: "Average order", value: kpis.aov === null ? "–" : formatBRL(kpis.aov), note: "GMV / paid orders" },
    { label: "Canceled", value: formatPercent(kpis.cancel_rate), note: `${formatInteger(kpis.canceled_orders)} canceled or unavailable` },
    { label: "Delivery time", value: formatDays(kpis.avg_delivery_days), note: `${formatInteger(kpis.delivered)} delivered` },
    { label: "Delivered late", value: formatPercent(kpis.late_share), note: "After the estimated date" },
  ]
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((card) => (
        <Card key={card.label} className="gap-2">
          <CardHeader>
            <CardDescription>{card.label}</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{card.value}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">{card.note}</CardContent>
        </Card>
      ))}
    </div>
  )
}
