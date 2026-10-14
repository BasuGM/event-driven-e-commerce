import type { Metadata } from "next"
import Link from "next/link"
import { redirect } from "next/navigation"

import { CartSummary } from "@/components/cart/cart-summary"
import { CheckoutForm } from "@/components/checkout/checkout-form"
import { PageHeader } from "@/components/layout/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { getCart, getMe, orLogin } from "@/lib/api/server"
import { formatBRL } from "@/lib/format"

export const metadata: Metadata = { title: "Checkout" }

export default async function CheckoutPage() {
  const [cart, me] = await orLogin(() => Promise.all([getCart(), getMe()]), "/checkout")
  if (!cart.can_checkout) redirect("/cart") // empty, or something is out of stock

  return (
    <div className="space-y-8">
      <PageHeader title="Checkout" description="Where should we send it?" />
      <div className="grid gap-8 lg:grid-cols-[1fr_22rem]">
        <Card>
          <CardHeader>
            <CardTitle>Shipping address</CardTitle>
          </CardHeader>
          <CardContent>
            <CheckoutForm lines={cart.lines} defaultName={me.user?.name ?? ""} />
          </CardContent>
        </Card>
        <Card className="h-fit lg:sticky lg:top-20">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Your order</CardTitle>
            <Link href="/cart" className="text-sm text-muted-foreground underline-offset-4 hover:underline">
              Edit cart
            </Link>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="space-y-3 text-sm">
              {cart.lines.map((line) => (
                <li key={line.id} className="flex justify-between gap-4">
                  <span className="min-w-0">
                    <span className="line-clamp-1">{line.product.name}</span>
                    <span className="text-xs text-muted-foreground">Qty {line.quantity}</span>
                  </span>
                  <span className="shrink-0 tabular-nums">{formatBRL(line.line_total)}</span>
                </li>
              ))}
            </ul>
            <Separator />
            <CartSummary totals={cart} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
