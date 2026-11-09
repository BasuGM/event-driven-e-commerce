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
  invoiced: "Invoice issued",
  shipped: "Handed to the carrier",
  delivered: "Delivered to you",
  unavailable: "The seller couldn't fulfil it",
  canceled_after_payment: "Canceled after payment",
  // historical replay (apps/replay)
  replay_placed: "Order placed (replay)",
  canceled_before_payment: "Canceled before payment",
}

// Rendered on the server: pin the zone (the store is Brazilian) instead of the server's UTC.
const TIME_OPTIONS: Intl.DateTimeFormatOptions = {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Sao_Paulo",
  timeZoneName: "short",
}
const timeFormatter = new Intl.DateTimeFormat("en-GB", TIME_OPTIONS)
const historicalFormatter = new Intl.DateTimeFormat("en-GB", { ...TIME_OPTIONS, year: "numeric" })

/**
 * Vertical timeline built from the order's status history (the audit trail). ``historical``
 * (replay copies) shows each step's domain time (``occurred_at``: the Olist time, years ago),
 * with the year, so it matches "Placed …"; other orders show when it was recorded, as before.
 */
export function OrderTimeline({ history, historical = false }: { history: OrderDetail["status_history"]; historical?: boolean }) {
  const format = historical ? historicalFormatter : timeFormatter
  return (
    <ol className="relative space-y-6 border-l pl-6">
      {history.map((entry, i) => {
        const canceled = entry.to_status === "canceled" || entry.to_status === "unavailable"
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
              <time dateTime={historical ? entry.occurred_at : entry.created_at}>
                {format.format(new Date(historical ? entry.occurred_at : entry.created_at))}
              </time>
            </p>
          </li>
        )
      })}
    </ol>
  )
}
