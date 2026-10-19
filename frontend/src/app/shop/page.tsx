import type { Metadata } from "next"

import { PageHeader } from "@/components/layout/page-header"
import { FiltersPanel } from "@/components/shop/filters-panel"
import { MobileFilters } from "@/components/shop/mobile-filters"
import { PageLinks } from "@/components/shop/page-links"
import { ProductGrid } from "@/components/shop/product-grid"
import { SearchBox } from "@/components/shop/search-box"
import { ShopEmptyState } from "@/components/shop/shop-empty-state"
import { PendingResults, ShopNavigationProvider } from "@/components/shop/shop-navigation"
import { SortSelect } from "@/components/shop/sort-select"
import { getCategories, getProducts } from "@/lib/api/catalog"
import { formatInteger } from "@/lib/format"
import { parseShopParams, shopHref, updateFilters } from "@/lib/shop-params"

export const metadata: Metadata = { title: "Shop" }

const PAGE_SIZE = 24

export default async function ShopPage({ searchParams }: PageProps<"/shop">) {
  // Reading searchParams makes this route dynamic: the listing is rendered per request.
  const filters = parseShopParams(await searchParams)
  const [result, categories] = await Promise.all([getProducts(filters), getCategories()])
  const page = filters.page ?? 1
  const activeCategory = categories.find((c) => c.slug === filters.category)

  return (
    <ShopNavigationProvider filters={filters}>
      <div className="space-y-6">
        <PageHeader
          title={activeCategory?.label ?? "Shop"}
          description="Real products from the Olist marketplace, sold by Brazilian sellers."
        />

        <div className="grid gap-8 lg:grid-cols-[15rem_1fr]">
          <aside className="hidden lg:block" aria-label="Filters">
            <FiltersPanel categories={categories} />
          </aside>

          <div id="results" className="min-w-0 scroll-mt-20 space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <SearchBox />
              <div className="flex items-center justify-between gap-2 sm:justify-end">
                <MobileFilters
                  categories={categories}
                  resultCount={result.status === "ok" ? result.page.count : 0}
                />
                <SortSelect />
              </div>
            </div>

            {result.status === "invalid" ? (
              <ShopEmptyState
                title="These filters aren't valid"
                description={Object.values(result.errors).flat().join(" ") || "Please adjust the filters."}
              />
            ) : (
              <PendingResults>
                {result.page.results.length === 0 ? (
                  <ShopEmptyState />
                ) : (
                  <div className="space-y-6">
                    <p className="text-sm text-muted-foreground" aria-live="polite">
                      {formatInteger(result.page.count)} {result.page.count === 1 ? "product" : "products"}
                      {filters.q && (
                        <>
                          {" "}for <span className="font-medium text-foreground">“{filters.q}”</span>
                        </>
                      )}
                    </p>
                    <ProductGrid products={result.page.results} />
                    <PageLinks
                      anchor="results"
                      page={page}
                      totalPages={Math.ceil(result.page.count / PAGE_SIZE)}
                      hrefFor={(n) => shopHref(updateFilters(filters, { page: n }))}
                    />
                  </div>
                )}
              </PendingResults>
            )}
          </div>
        </div>
      </div>
    </ShopNavigationProvider>
  )
}
