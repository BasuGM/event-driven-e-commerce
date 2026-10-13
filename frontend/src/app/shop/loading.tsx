import { ProductGridSkeleton } from "@/components/shop/product-grid-skeleton"
import { Skeleton } from "@/components/ui/skeleton"

export default function ShopLoading() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <div className="grid gap-8 lg:grid-cols-[15rem_1fr]">
        <div className="hidden space-y-2 lg:block">
          {Array.from({ length: 10 }, (_, i) => (
            <Skeleton key={i} className="h-7 w-full" />
          ))}
        </div>
        <div className="space-y-4">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-4 w-28" />
          <ProductGridSkeleton />
        </div>
      </div>
    </div>
  )
}
