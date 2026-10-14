import { CheckCircle2, Circle, XCircle } from "lucide-react"

import type { OrderDetail } from "@/lib/api/client"
import { cn } from "@/lib/utils"

import { STATUS_LABELS } from "./order-status-badge"

const REASONS: Record<string, string> = {
  checkout: "Order placed, stock held",
  payment_succeeded: "Payment received",
  payment_failed: "Payment failed, stock released",
  reservation_expired: "Not paid in time, stock released",
  customer_canceled: "Canceled by you, stock released",
}

// Rendered on the server: pin the zone (the store is Brazilian) instead of the server's UTC.
const timeFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Sao_Paulo",
  timeZoneName: "short",
})

/** Vertical timeline built from the order's status history (the audit trail). */
export function OrderTimeline({ history }: { history: OrderDetail["status_history"] }) {
  return (
    <ol className="relative space-y-6 border-l pl-6">
      {history.map((entry, i) => {
        const canceled = entry.to_status === "canceled"
        const Icon = canceled ? XCircle : i === history.length - 1 ? CheckCircle2 : Circle
        return (
          <li key={`${entry.to_status}-${entry.created_at}`} className="relative">
            <Icon
              aria-hidden
              className={cn(
                "absolute top-0.5 -left-[2.0625rem] size-4 bg-card",
                canceled ? "text-destructive" : i === history.length - 1 ? "text-success" : "text-muted-foreground",
              )}
            />
            <p className="text-sm font-medium">{STATUS_LABELS[entry.to_status as keyof typeof STATUS_LABELS]}</p>
            <p className="text-xs text-muted-foreground">
              {REASONS[entry.reason] ?? entry.reason.replace(/_/g, " ")} ·{" "}
              <time dateTime={entry.created_at}>{timeFormatter.format(new Date(entry.created_at))}</time>
            </p>
          </li>
        )
      })}
    </ol>
  )
}
