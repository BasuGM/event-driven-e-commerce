"use client"

import { useRouter } from "next/navigation"
import { createContext, useContext, useTransition } from "react"

import { cn } from "@/lib/utils"
import { shopHref, updateFilters, type ShopFilters } from "@/lib/shop-params"

type ShopNavigation = {
  filters: ShopFilters
  isPending: boolean
  /** Push a new URL built from the current filters plus `patch` (page resets unless given). */
  apply: (patch: Partial<ShopFilters>) => void
  clear: () => void
}

const ShopNavigationContext = createContext<ShopNavigation | null>(null)

/**
 * Filters come from the URL (parsed on the server) and every change is a router.push of a new
 * URL, so the URL stays the single source of truth. The transition keeps the current results
 * on screen (dimmed) until the new ones arrive instead of flashing a skeleton.
 */
export function ShopNavigationProvider({
  filters,
  children,
}: {
  filters: ShopFilters
  children: React.ReactNode
}) {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()

  const navigate = (href: string) =>
    startTransition(() => router.push(href, { scroll: false }))

  const value: ShopNavigation = {
    filters,
    isPending,
    apply: (patch) => navigate(shopHref(updateFilters(filters, patch))),
    clear: () => navigate(shopHref({ ordering: filters.ordering })),
  }
  return <ShopNavigationContext.Provider value={value}>{children}</ShopNavigationContext.Provider>
}

export function useShopNavigation(): ShopNavigation {
  const value = useContext(ShopNavigationContext)
  if (!value) throw new Error("useShopNavigation must be used inside ShopNavigationProvider")
  return value
}

export function PendingResults({ children }: { children: React.ReactNode }) {
  const { isPending } = useShopNavigation()
  return (
    <div
      aria-busy={isPending}
      className={cn("transition-opacity", isPending && "pointer-events-none opacity-60")}
    >
      {children}
    </div>
  )
}
