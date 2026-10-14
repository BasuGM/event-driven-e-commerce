import { Skeleton } from "@/components/ui/skeleton"

export default function OrdersLoading({ table = false }: { table?: boolean }) {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="Loading orders">
      {!table && <Skeleton className="h-8 w-40" />}
      <div className="space-y-3 rounded-xl border p-4">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="flex items-center justify-between gap-4">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-5 w-28 rounded-full" />
            <Skeleton className="h-4 w-16" />
          </div>
        ))}
      </div>
    </div>
  )
}
