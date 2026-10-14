"use client"

import { Loader2, Trash2 } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState, useTransition } from "react"

import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { CategoryPlaceholder } from "@/components/shop/category-placeholder"
import { browserApi, ensureCsrf, NETWORK_PROBLEM, toProblem } from "@/lib/api/browser"
import type { CartLine } from "@/lib/api/client"
import { formatBRL } from "@/lib/format"

import { LineWarning } from "./line-warning"

const QUANTITIES = Array.from({ length: 10 }, (_, i) => String(i + 1))

export function CartLines({ lines }: { lines: CartLine[] }) {
  return (
    <ul className="divide-y">
      {lines.map((line) => (
        <CartLineRow key={line.id} line={line} />
      ))}
    </ul>
  )
}

function CartLineRow({ line }: { line: CartLine }) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  // Every edit returns the new cart; refreshing re-renders the server page (totals, header badge)
  const run = (request: () => Promise<{ response: Response; error?: unknown }>) =>
    startTransition(async () => {
      setError(null)
      try {
        await ensureCsrf()
        const { response, error } = await request()
        if (!response.ok) setError(toProblem(response.status, error).message)
        router.refresh()
      } catch {
        setError(NETWORK_PROBLEM.message)
      }
    })

  const setQuantity = (value: string) =>
    run(() =>
      browserApi.PATCH("/api/cart/items/{item_id}/", {
        params: { path: { item_id: line.id } },
        body: { quantity: Number(value) },
      }),
    )
  const remove = () =>
    run(() => browserApi.DELETE("/api/cart/items/{item_id}/", { params: { path: { item_id: line.id } } }))

  return (
    <li className="flex gap-4 py-4 first:pt-0" aria-busy={pending}>
      <Link href={`/shop/${line.product.slug}`} className="w-20 shrink-0 sm:w-24" tabIndex={-1} aria-hidden>
        <CategoryPlaceholder category={line.product.category} iconClassName="size-8" />
      </Link>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-col gap-1 sm:flex-row sm:justify-between sm:gap-4">
          <div className="min-w-0">
            <Link href={`/shop/${line.product.slug}`} className="line-clamp-2 font-medium hover:underline">
              {line.product.name}
            </Link>
            <p className="text-xs text-muted-foreground">
              Seller {line.seller.id} · {line.seller.city.replace(/\b\p{L}/gu, (c) => c.toUpperCase())}, {line.seller.state}
            </p>
          </div>
          <div className="text-sm sm:text-right">
            <p className="font-semibold tabular-nums">{formatBRL(line.line_total)}</p>
            <p className="text-xs text-muted-foreground tabular-nums">
              {formatBRL(line.unit_price)} each · shipping {formatBRL(line.line_freight)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={String(line.quantity)} onValueChange={setQuantity} disabled={pending}>
            <SelectTrigger size="sm" className="w-16" aria-label={`Quantity of ${line.product.name}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {QUANTITIES.map((q) => (
                <SelectItem key={q} value={q}>
                  {q}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="ghost" size="sm" onClick={remove} disabled={pending} aria-label={`Remove ${line.product.name}`}>
            {pending ? <Loader2 className="animate-spin" /> : <Trash2 />}
            <span className="hidden sm:inline">Remove</span>
          </Button>
        </div>
        <LineWarning line={line} />
        {error && (
          <p role="alert" className="text-xs text-destructive">
            {error}
          </p>
        )}
      </div>
    </li>
  )
}
