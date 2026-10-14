import { Badge } from "@/components/ui/badge"
import type { OrderStatus } from "@/lib/api/client"

export const STATUS_LABELS: Record<OrderStatus, string> = {
  created: "Awaiting payment",
  approved: "Approved",
  invoiced: "Invoiced",
  processing: "Processing",
  shipped: "Shipped",
  delivered: "Delivered",
  canceled: "Canceled",
  unavailable: "Unavailable",
}

const VARIANTS: Partial<Record<OrderStatus, "success" | "destructive" | "secondary" | "outline">> = {
  created: "outline",
  approved: "success",
  delivered: "success",
  canceled: "destructive",
  unavailable: "destructive",
}

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return <Badge variant={VARIANTS[status] ?? "secondary"}>{STATUS_LABELS[status]}</Badge>
}
