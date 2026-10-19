"use client"

import { SlidersHorizontal } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import type { Category } from "@/lib/api/client"
import { formatInteger } from "@/lib/format"

import { FiltersPanel } from "./filters-panel"
import { useShopNavigation } from "./shop-navigation"

/** `resultCount`: results for the current URL's filters (updates as filters apply). */
export function MobileFilters({ categories, resultCount }: { categories: Category[]; resultCount: number }) {
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
          <FiltersPanel categories={categories} scrollCategories={false} />
        </div>
        <SheetFooter className="sticky bottom-0 border-t bg-background">
          <SheetClose asChild>
            <Button>
              Show {formatInteger(resultCount)} {resultCount === 1 ? "result" : "results"}
            </Button>
          </SheetClose>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
