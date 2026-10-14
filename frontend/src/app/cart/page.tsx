import { ShoppingBag } from "lucide-react"
import type { Metadata } from "next"
import Link from "next/link"

import { CartLines } from "@/components/cart/cart-lines"
import { CartSummary } from "@/components/cart/cart-summary"
import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { getCart, orLogin } from "@/lib/api/server"

export const metadata: Metadata = { title: "Cart" }

export default async function CartPage() {
  const cart = await orLogin(getCart, "/cart")

  if (cart.lines.length === 0) {
    return (
      <div className="space-y-8">
        <PageHeader title="Cart" />
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-muted">
              <ShoppingBag className="size-6 text-muted-foreground" aria-hidden />
            </span>
            <div className="space-y-1">
              <p className="font-medium">Your cart is empty</p>
              <p className="text-sm text-muted-foreground">Browse the shop and add something you like.</p>
            </div>
            <Button asChild>
              <Link href="/shop">Go to the shop</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Cart" description="Prices and availability are live; stock is held only when you place the order." />
      <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        <Card>
          <CardContent>
            <CartLines lines={cart.lines} />
          </CardContent>
        </Card>
        <Card className="h-fit lg:sticky lg:top-20">
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <CartSummary totals={cart}>
              {cart.can_checkout ? (
                <Button asChild className="w-full">
                  <Link href="/checkout">Checkout</Link>
                </Button>
              ) : (
                <>
                  <Button className="w-full" disabled>
                    Checkout
                  </Button>
                  <p className="text-xs text-destructive">Fix the highlighted items to check out.</p>
                </>
              )}
            </CartSummary>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
