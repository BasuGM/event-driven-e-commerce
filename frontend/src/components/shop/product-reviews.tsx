import { MessageSquareText } from "lucide-react"

import { Skeleton } from "@/components/ui/skeleton"
import { getProductReviews } from "@/lib/api/catalog"
import { formatDate } from "@/lib/format"

import { PageLinks } from "./page-links"
import { StarRating } from "./star-rating"

const REVIEWS_PAGE_SIZE = 5

/** Not cached: reads the reviews page from the URL and always shows current reviews. */
export async function ProductReviews({
  slug,
  searchParams,
}: {
  slug: string
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const raw = (await searchParams).reviews_page
  const parsed = Number(Array.isArray(raw) ? raw[0] : raw)
  const page = Number.isInteger(parsed) && parsed > 1 ? parsed : 1
  const data = await getProductReviews(slug, page)
  const totalPages = Math.ceil(data.count / REVIEWS_PAGE_SIZE)

  if (data.count === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-10 text-center">
        <MessageSquareText className="size-6 text-muted-foreground" aria-hidden />
        <p className="text-sm text-muted-foreground">No reviews yet.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <ul className="divide-y">
        {data.results.map((review) => (
          <li key={review.id} className="space-y-1.5 py-4 first:pt-0">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <StarRating rating={review.score} />
              <time dateTime={review.created_date} className="text-xs text-muted-foreground">
                {formatDate(review.created_date)}
              </time>
            </div>
            {review.title && <p className="text-sm font-medium">{review.title}</p>}
            <p className="text-sm text-muted-foreground">
              {review.message || <span className="italic">No written comment.</span>}
            </p>
          </li>
        ))}
      </ul>
      <PageLinks
        label="Review pages"
        page={page}
        totalPages={totalPages}
        hrefFor={(n) => (n === 1 ? `/shop/${slug}` : `/shop/${slug}?reviews_page=${n}`)}
      />
    </div>
  )
}

export function ProductReviewsSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading reviews">
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ))}
    </div>
  )
}
