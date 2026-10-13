"use client"

import Link from "next/link"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import type { Category } from "@/lib/api/client"
import { formatInteger } from "@/lib/format"
import { hasActiveFilters, shopHref, updateFilters } from "@/lib/shop-params"
import { cn } from "@/lib/utils"

import { useShopNavigation } from "./shop-navigation"

const RATING_OPTIONS = [
  { value: "any", label: "Any rating" },
  { value: "4", label: "4 stars & up" },
  { value: "3", label: "3 stars & up" },
  { value: "2", label: "2 stars & up" },
]

export function FiltersPanel({ categories }: { categories: Category[] }) {
  const { filters, apply, clear } = useShopNavigation()

  return (
    <div className="space-y-6">
      <section aria-labelledby="filter-category" className="space-y-2">
        <h2 id="filter-category" className="text-sm font-medium">
          Category
        </h2>
        <ul className="-mx-2 max-h-80 space-y-0.5 overflow-y-auto pr-1">
          <li>
            <CategoryLink href={shopHref(updateFilters(filters, { category: undefined }))} active={!filters.category}>
              All categories
            </CategoryLink>
          </li>
          {categories.map((category) => (
            <li key={category.slug}>
              <CategoryLink
                href={shopHref(updateFilters(filters, { category: category.slug }))}
                active={filters.category === category.slug}
                count={category.product_count}
              >
                {category.label}
              </CategoryLink>
            </li>
          ))}
        </ul>
      </section>

      <Separator />

      {/* Remount when the URL values change (e.g. Clear) so the inputs show the URL's state */}
      <PriceRange key={`${filters.minPrice ?? ""}-${filters.maxPrice ?? ""}`} />

      <Separator />

      <section className="space-y-2">
        <Label htmlFor="filter-rating">Minimum rating</Label>
        <Select
          value={filters.minRating ? String(filters.minRating) : "any"}
          onValueChange={(value) => apply({ minRating: value === "any" ? undefined : Number(value) })}
        >
          <SelectTrigger id="filter-rating" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RATING_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </section>

      <div className="flex items-center justify-between gap-4">
        <Label htmlFor="filter-in-stock">In stock only</Label>
        <Switch
          id="filter-in-stock"
          checked={Boolean(filters.inStock)}
          onCheckedChange={(checked) => apply({ inStock: checked || undefined })}
        />
      </div>

      {hasActiveFilters(filters) && (
        <Button variant="outline" className="w-full" onClick={clear}>
          Clear filters
        </Button>
      )}
    </div>
  )
}

function CategoryLink({
  href,
  active,
  count,
  children,
}: {
  href: string
  active: boolean
  count?: number
  children: React.ReactNode
}) {
  return (
    <Link
      href={href}
      scroll={false}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
        active ? "bg-accent font-medium text-foreground" : "text-muted-foreground",
      )}
    >
      <span className="truncate">{children}</span>
      {count !== undefined && <span className="text-xs tabular-nums">{formatInteger(count)}</span>}
    </Link>
  )
}

function PriceRange() {
  const { filters, apply } = useShopNavigation()
  const [min, setMin] = useState(filters.minPrice ?? "")
  const [max, setMax] = useState(filters.maxPrice ?? "")
  const invalid = min !== "" && max !== "" && Number(min) > Number(max)

  const commit = () => {
    if (invalid) return
    const minPrice = min.trim() || undefined
    const maxPrice = max.trim() || undefined
    if (minPrice !== filters.minPrice || maxPrice !== filters.maxPrice) apply({ minPrice, maxPrice })
  }

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">Price (R$)</legend>
      <form
        className="flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          commit()
        }}
      >
        <Label htmlFor="filter-min-price" className="sr-only">
          Minimum price
        </Label>
        <Input
          id="filter-min-price"
          inputMode="decimal"
          placeholder="Min"
          value={min}
          onChange={(e) => setMin(e.target.value.replace(/[^\d.]/g, ""))}
          onBlur={commit}
          aria-invalid={invalid || undefined}
        />
        <span className="text-muted-foreground" aria-hidden>
          –
        </span>
        <Label htmlFor="filter-max-price" className="sr-only">
          Maximum price
        </Label>
        <Input
          id="filter-max-price"
          inputMode="decimal"
          placeholder="Max"
          value={max}
          onChange={(e) => setMax(e.target.value.replace(/[^\d.]/g, ""))}
          onBlur={commit}
          aria-invalid={invalid || undefined}
        />
        <button type="submit" className="sr-only">
          Apply price
        </button>
      </form>
      {invalid && <p className="text-xs text-destructive">Minimum must not exceed maximum.</p>}
    </fieldset>
  )
}
