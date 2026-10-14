import { Skeleton } from "@/components/ui/skeleton"

export default function CheckoutLoading() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-40" />
      <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-4">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="flex gap-4">
              <Skeleton className="size-20 rounded-lg" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-1/3" />
                <Skeleton className="h-7 w-24" />
              </div>
            </div>
          ))}
        </div>
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    </div>
  )
}
