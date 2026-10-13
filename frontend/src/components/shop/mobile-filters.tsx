"use client"

import { SlidersHorizontal } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import type { Category } from "@/lib/api/client"

import { FiltersPanel } from "./filters-panel"
import { useShopNavigation } from "./shop-navigation"

export function MobileFilters({ categories }: { categories: Category[] }) {
  const { filters } = useShopNavigation()
  const active = [filters.category, filters.minPrice || filters.maxPrice, filters.minRating, filters.inStock].filter(Boolean).length

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" className="lg:hidden">
          <SlidersHorizontal /> Filters{active > 0 && ` (${active})`}
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-80 overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Filters</SheetTitle>
          <SheetDescription>Results update as you change filters.</SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6">
          <FiltersPanel categories={categories} />
        </div>
      </SheetContent>
    </Sheet>
  )
}
