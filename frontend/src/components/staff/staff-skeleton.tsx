import { Skeleton } from "@/components/ui/skeleton"

/** Neutral placeholder for staff pages: no staff navigation until the access check passed. */
export function StaffSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-24 w-full rounded-lg" />
      <div className="space-y-3 rounded-xl border p-4">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-5 w-full" />
        ))}
      </div>
    </div>
  )
}
