import { ChevronLeft, ChevronRight } from "lucide-react"
import Link from "next/link"

import { Button } from "@/components/ui/button"
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem } from "@/components/ui/pagination"

/** Pages to show around the current one: 1 … 4 5 6 … 20 */
export function pageWindow(current: number, total: number): (number | "gap")[] {
  const pages = new Set([1, total, current - 1, current, current + 1])
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b)
  const out: (number | "gap")[] = []
  sorted.forEach((page, i) => {
    if (i > 0 && page - sorted[i - 1] > 1) out.push("gap")
    out.push(page)
  })
  return out
}

/** Link-based pagination (real hrefs: works without JS, back button, shareable). */
export function PageLinks({
  page,
  totalPages,
  hrefFor,
  label = "Pagination",
}: {
  page: number
  totalPages: number
  hrefFor: (page: number) => string
  label?: string
}) {
  if (totalPages <= 1) return null
  return (
    <Pagination aria-label={label}>
      <PaginationContent>
        <PaginationItem>
          <PageButton href={page > 1 ? hrefFor(page - 1) : undefined} aria-label="Previous page">
            <ChevronLeft /> <span className="hidden sm:inline">Previous</span>
          </PageButton>
        </PaginationItem>
        {pageWindow(page, totalPages).map((item, i) =>
          item === "gap" ? (
            <PaginationItem key={`gap-${i}`} className="hidden sm:block">
              <PaginationEllipsis />
            </PaginationItem>
          ) : (
            <PaginationItem key={item} className={item === page ? "" : "hidden sm:block"}>
              <Button asChild variant={item === page ? "outline" : "ghost"} size="icon">
                <Link href={hrefFor(item)} scroll={false} aria-current={item === page ? "page" : undefined}>
                  {item}
                </Link>
              </Button>
            </PaginationItem>
          ),
        )}
        <PaginationItem>
          <PageButton href={page < totalPages ? hrefFor(page + 1) : undefined} aria-label="Next page">
            <span className="hidden sm:inline">Next</span> <ChevronRight />
          </PageButton>
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  )
}

function PageButton({
  href,
  children,
  ...props
}: { href?: string; children: React.ReactNode; "aria-label": string }) {
  if (!href) {
    return (
      <Button variant="ghost" disabled {...props}>
        {children}
      </Button>
    )
  }
  return (
    <Button asChild variant="ghost" {...props}>
      <Link href={href}>{children}</Link>
    </Button>
  )
}
