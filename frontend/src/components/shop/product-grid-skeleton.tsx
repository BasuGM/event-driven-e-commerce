import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export function ProductGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-4" aria-busy="true" aria-label="Loading products">
      {Array.from({ length: count }, (_, i) => (
        <li key={i}>
          <Card className="gap-0 py-0">
            <div className="p-3 pb-0">
              <Skeleton className="aspect-square w-full rounded-lg" />
            </div>
            <CardContent className="space-y-2 p-4">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3.5 w-24" />
              <Skeleton className="h-5 w-20" />
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  )
}
