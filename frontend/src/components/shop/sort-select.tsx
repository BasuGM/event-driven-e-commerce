"use client"

import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ORDERING_LABELS, ORDERINGS, type ShopOrdering } from "@/lib/shop-params"

import { useShopNavigation } from "./shop-navigation"

const RELEVANCE = "relevance"

export function SortSelect() {
  const { filters, apply } = useShopNavigation()
  // Searching without an explicit sort ranks by relevance (the API's default for q).
  const value = filters.ordering ?? (filters.q ? RELEVANCE : "popular")
  const label = value === RELEVANCE ? "Best match" : ORDERING_LABELS[value]

  return (
    <div className="flex items-center gap-2">
      <Label htmlFor="shop-sort" className="shrink-0 text-sm text-muted-foreground">
        Sort by
      </Label>
      <Select
        value={value}
        onValueChange={(next) => apply({ ordering: next === RELEVANCE ? undefined : (next as ShopOrdering) })}
      >
        <SelectTrigger id="shop-sort" className="w-44">
          {/* Explicit label: Radix only knows item text once the (client) content mounts, so the
              server-rendered trigger would otherwise be blank until hydration */}
          <SelectValue>{label}</SelectValue>
        </SelectTrigger>
        <SelectContent align="end">
          {filters.q && <SelectItem value={RELEVANCE}>Best match</SelectItem>}
          {ORDERINGS.map((ordering) => (
            <SelectItem key={ordering} value={ordering}>
              {ORDERING_LABELS[ordering]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
