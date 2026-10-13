import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import type { ProductListItem } from "@/lib/api/client"
import { formatBRL } from "@/lib/format"

import { CategoryPlaceholder } from "./category-placeholder"
import { StarRating } from "./star-rating"

export function ProductCard({ product }: { product: ProductListItem }) {
  return (
    <Card className="group relative h-full gap-0 overflow-hidden py-0 transition-shadow focus-within:ring-[3px] focus-within:ring-ring/50 hover:shadow-md">
      <div className="relative p-3 pb-0">
        <CategoryPlaceholder category={product.category} className="transition-transform group-hover:scale-[1.02]" />
        {!product.in_stock && (
          <Badge variant="secondary" className="absolute top-5 left-5">
            Out of stock
          </Badge>
        )}
      </div>
      <CardContent className="flex flex-1 flex-col gap-2 p-4">
        <p className="text-xs text-muted-foreground">{product.category?.label ?? "Uncategorised"}</p>
        <h3 className="line-clamp-2 min-h-10 text-sm leading-5 font-medium">
          {/* Stretched link: the whole card is clickable, but only one link is announced */}
          <Link href={`/shop/${product.slug}`} className="after:absolute after:inset-0 focus-visible:outline-none">
            {product.name}
          </Link>
        </h3>
        <StarRating rating={product.rating_avg} count={product.rating_count} />
        <p className="mt-auto pt-1 text-base font-semibold tabular-nums">
          {product.min_price ? (
            formatBRL(product.min_price)
          ) : (
            <span className="text-sm font-normal text-muted-foreground">Unavailable</span>
          )}
        </p>
      </CardContent>
    </Card>
  )
}
