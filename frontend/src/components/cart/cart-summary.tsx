import { Separator } from "@/components/ui/separator"
import { formatBRL } from "@/lib/format"

export type CartTotals = {
  item_count: number
  subtotal: string
  freight_total: string
  total: string
}

/** Subtotal / freight / total in BRL. Totals come from the API (Decimal strings), never summed in JS. */
export function CartSummary({ totals, children }: { totals: CartTotals; children?: React.ReactNode }) {
  return (
    <div className="space-y-4">
      <dl className="space-y-2 text-sm">
        <div className="flex justify-between">
          <dt className="text-muted-foreground">
            Items ({totals.item_count} {totals.item_count === 1 ? "unit" : "units"})
          </dt>
          <dd className="tabular-nums">{formatBRL(totals.subtotal)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Shipping</dt>
          <dd className="tabular-nums">{formatBRL(totals.freight_total)}</dd>
        </div>
        <Separator />
        <div className="flex justify-between text-base font-semibold">
          <dt>Total</dt>
          <dd className="tabular-nums" data-testid="cart-total">
            {formatBRL(totals.total)}
          </dd>
        </div>
      </dl>
      {children}
    </div>
  )
}
