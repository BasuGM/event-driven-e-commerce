import { Package } from "lucide-react"
import type { Metadata } from "next"
import Link from "next/link"
import { Suspense } from "react"

import { PageHeader } from "@/components/layout/page-header"
import { OrderStatusBadge } from "@/components/orders/order-status-badge"
import { PageLinks } from "@/components/shop/page-links"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { getOrders, orLogin } from "@/lib/api/server"
import { formatBRL, formatDate } from "@/lib/format"

import OrdersLoading from "./loading"

export const metadata: Metadata = { title: "Orders" }

const PAGE_SIZE = 10

export default function OrdersPage({ searchParams }: PageProps<"/orders">) {
  return (
    <div className="space-y-8">
      <PageHeader title="Orders" description="Everything you've ordered, newest first." />
      <Suspense fallback={<OrdersLoading table />}>
        <OrdersList searchParams={searchParams} />
      </Suspense>
    </div>
  )
}

async function OrdersList({ searchParams }: { searchParams: PageProps<"/orders">["searchParams"] }) {
  const raw = Number((await searchParams).page)
  const page = Number.isInteger(raw) && raw > 1 ? raw : 1
  const data = await orLogin(() => getOrders(page), page > 1 ? `/orders?page=${page}` : "/orders")

  if (data.count === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-muted">
            <Package className="size-6 text-muted-foreground" aria-hidden />
          </span>
          <div className="space-y-1">
            <p className="font-medium">No orders yet</p>
            <p className="text-sm text-muted-foreground">When you place an order it shows up here.</p>
          </div>
          <Button asChild>
            <Link href="/shop">Start shopping</Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Order</TableHead>
              <TableHead>Placed</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden text-right sm:table-cell">Items</TableHead>
              <TableHead className="pr-4 text-right">Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.results.map((order) => (
              <TableRow key={order.id} className="relative">
                <TableCell className="pl-4 font-mono text-xs">
                  <Link href={`/orders/${order.id}`} className="after:absolute after:inset-0 hover:underline">
                    #{order.id.slice(0, 8)}
                  </Link>
                </TableCell>
                <TableCell>{formatDate(order.purchased_at)}</TableCell>
                <TableCell>
                  <OrderStatusBadge status={order.status} />
                </TableCell>
                <TableCell className="hidden text-right tabular-nums sm:table-cell">{order.item_count}</TableCell>
                <TableCell className="pr-4 text-right font-medium tabular-nums">{formatBRL(order.total)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <PageLinks
        label="Order pages"
        page={page}
        totalPages={Math.ceil(data.count / PAGE_SIZE)}
        hrefFor={(n) => (n === 1 ? "/orders" : `/orders?page=${n}`)}
      />
    </div>
  )
}
