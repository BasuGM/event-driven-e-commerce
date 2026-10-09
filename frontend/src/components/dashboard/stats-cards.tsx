import { Database, Package, ShoppingCart, Store, Users, type LucideIcon } from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { formatInteger } from "@/lib/format"

export type StatsCardsData = {
  products: number
  orders: number
  customers: number
  sellers: number
}

const ITEMS: { key: keyof StatsCardsData; label: string; icon: LucideIcon }[] = [
  { key: "orders", label: "Orders", icon: ShoppingCart },
  { key: "customers", label: "Customers", icon: Users },
  { key: "products", label: "Products", icon: Package },
  { key: "sellers", label: "Sellers", icon: Store },
]

export function StatsCards({ stats }: { stats: StatsCardsData }) {
  const isEmpty = ITEMS.every(({ key }) => stats[key] === 0)

  if (isEmpty) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-muted">
            <Database className="size-5 text-muted-foreground" />
          </span>
          <div className="space-y-1">
            <p className="font-medium">No data yet</p>
            <p className="text-sm text-muted-foreground">
              Load the Olist sample with <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">make seed</code>.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {ITEMS.map(({ key, label, icon: Icon }) => (
        <Card key={key}>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardDescription>{label}</CardDescription>
            <Icon className="size-4 text-muted-foreground" aria-hidden />
          </CardHeader>
          <CardContent>
            <CardTitle className="text-3xl font-semibold tabular-nums tracking-tight">
              {formatInteger(stats[key])}
            </CardTitle>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
