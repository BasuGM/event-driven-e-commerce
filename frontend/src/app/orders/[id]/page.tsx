import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"
import { Suspense } from "react"

import { CartSummary } from "@/components/cart/cart-summary"
import { OrderActions } from "@/components/orders/order-actions"
import { OrderStatusBadge } from "@/components/orders/order-status-badge"
import { OrderTimeline } from "@/components/orders/order-timeline"
import { ReservationCountdown } from "@/components/orders/reservation-countdown"
import { CategoryPlaceholder } from "@/components/shop/category-placeholder"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { getOrder, orLogin } from "@/lib/api/server"
import { formatBRL, formatDate } from "@/lib/format"

export const metadata: Metadata = { title: "Order" }

export default function OrderPage({ params }: PageProps<"/orders/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
      <Order params={params} />
    </Suspense>
  )
}

async function Order({ params }: { params: PageProps<"/orders/[id]">["params"] }) {
  const { id } = await params
  const order = await orLogin(() => getOrder(id), `/orders/${id}`)
  if (!order) notFound()

  return (
    <div className="space-y-8">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/orders">Orders</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage className="font-mono">#{order.id.slice(0, 8)}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            Order <span className="font-mono">#{order.id.slice(0, 8)}</span>
          </h1>
          <p className="text-muted-foreground">Placed {formatDate(order.purchased_at)}</p>
        </div>
        <div data-testid="order-status">
          <OrderStatusBadge status={order.status} />
        </div>
      </div>

      {(order.can_pay || order.can_cancel || order.reservation_expires_at) && (
        <Card>
          <CardContent className="space-y-4">
            {order.status === "created" && order.reservation_expires_at && (
              <ReservationCountdown expiresAt={order.reservation_expires_at} />
            )}
            <OrderActions
              orderId={order.id}
              canPay={order.can_pay}
              canCancel={order.can_cancel}
              paymentsEnabled={order.payments_enabled}
            />
          </CardContent>
        </Card>
      )}

      <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-8">
          <Card>
            <CardHeader>
              <CardTitle>Items</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y">
                {order.lines.map((line) => (
                  <li key={`${line.product_slug}-${line.seller_id}-${line.unit_price}`} className="flex gap-4 py-4 first:pt-0 last:pb-0">
                    <div className="w-16 shrink-0">
                      <CategoryPlaceholder category={line.category} iconClassName="size-6" />
                    </div>
                    <div className="flex min-w-0 flex-1 justify-between gap-4">
                      <div className="min-w-0">
                        <Link href={`/shop/${line.product_slug}`} className="line-clamp-2 font-medium hover:underline">
                          {line.product_name}
                        </Link>
                        <p className="text-xs text-muted-foreground">
                          Qty {line.quantity} · {formatBRL(line.unit_price)} each · Seller {line.seller_id}
                        </p>
                      </div>
                      <p className="shrink-0 font-medium tabular-nums">{formatBRL(line.line_total)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>History</CardTitle>
            </CardHeader>
            <CardContent>
              <OrderTimeline history={order.status_history} />
            </CardContent>
          </Card>
        </div>
        <div className="space-y-8">
          <Card>
            <CardHeader>
              <CardTitle>Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <CartSummary
                totals={{
                  item_count: order.item_count,
                  subtotal: order.items_total,
                  freight_total: order.freight_total,
                  total: order.total,
                }}
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Shipping to</CardTitle>
            </CardHeader>
            <CardContent>
              <address className="text-sm leading-relaxed not-italic text-muted-foreground">
                <span className="font-medium text-foreground">{order.shipping.full_name}</span>
                <br />
                {order.shipping.street}
                <br />
                {order.shipping.city}, {order.shipping.state} {order.shipping.zip_code}
              </address>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
