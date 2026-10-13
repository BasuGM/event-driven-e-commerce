import { Star, StarHalf } from "lucide-react"

import { cn } from "@/lib/utils"

/** Five stars rounded to the nearest half, plus an optional review count. */
export function StarRating({
  rating,
  count,
  className,
  size = "sm",
}: {
  rating: string | number | null
  count?: number
  className?: string
  size?: "sm" | "lg"
}) {
  const value = rating === null ? null : Number(rating)
  const rounded = value === null ? 0 : Math.round(value * 2) / 2
  const iconSize = size === "lg" ? "size-5" : "size-3.5"
  const label =
    value === null ? "No ratings yet" : `Rated ${value.toFixed(1)} out of 5${count ? ` from ${count} reviews` : ""}`

  return (
    <div className={cn("flex items-center gap-1.5", className)} aria-label={label} role="img">
      <div className="flex items-center" aria-hidden>
        {Array.from({ length: 5 }, (_, i) => {
          const position = i + 1
          if (rounded >= position) {
            return <Star key={i} className={cn(iconSize, "fill-rating text-rating")} />
          }
          if (rounded === position - 0.5) {
            return (
              <span key={i} className="relative">
                <Star className={cn(iconSize, "text-muted-foreground/30")} />
                <StarHalf className={cn(iconSize, "absolute inset-0 fill-rating text-rating")} />
              </span>
            )
          }
          return <Star key={i} className={cn(iconSize, "text-muted-foreground/30")} />
        })}
      </div>
      {count !== undefined && (
        <span className="text-xs text-muted-foreground tabular-nums" aria-hidden>
          {value === null ? "No reviews" : `(${count})`}
        </span>
      )}
    </div>
  )
}
