import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"
import { Suspense } from "react"

import { Badge } from "@/components/ui/badge"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { CategoryPlaceholder } from "@/components/shop/category-placeholder"
import { OffersTable } from "@/components/shop/offers-table"
import { ProductReviews, ProductReviewsSkeleton } from "@/components/shop/product-reviews"
import { StarRating } from "@/components/shop/star-rating"
import { getProduct } from "@/lib/api/catalog"
import type { ProductDetail } from "@/lib/api/client"
import { formatBRL, formatInteger } from "@/lib/format"

export async function generateMetadata({ params }: PageProps<"/shop/[slug]">): Promise<Metadata> {
  const product = await getProduct((await params).slug)
  return { title: product?.name ?? "Product not found" }
}

export default async function ProductPage({ params, searchParams }: PageProps<"/shop/[slug]">) {
  const { slug } = await params
  // Cached for a few minutes (see getProduct); reviews below stay dynamic.
  const product = await getProduct(slug)
  if (!product) notFound()

  return (
    <div className="space-y-8">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/shop">Shop</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          {product.category && (
            <>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link href={`/shop?category=${product.category.slug}`}>{product.category.label}</Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
            </>
          )}
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage className="line-clamp-1">{product.name}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="grid gap-8 md:grid-cols-2 lg:gap-12">
        <CategoryPlaceholder category={product.category} className="rounded-xl" iconClassName="size-24" />

        <div className="space-y-6">
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{product.category?.label ?? "Uncategorised"}</p>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{product.name}</h1>
            <a href="#reviews" className="inline-flex rounded-sm focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none">
              <StarRating rating={product.rating_avg} count={product.rating_count} />
            </a>
          </div>

          <PriceSummary product={product} />

          <Separator />

          <div className="space-y-2">
            <h2 className="text-sm font-medium">Description</h2>
            <p className="leading-relaxed text-muted-foreground">{product.description}</p>
          </div>

          <Dimensions product={product} />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            Sellers <span className="font-normal text-muted-foreground">({product.offers.length})</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {product.offers.length > 0 ? (
            <OffersTable offers={product.offers} productSlug={product.slug} />
          ) : (
            <p className="text-sm text-muted-foreground">No sellers offer this product right now.</p>
          )}
        </CardContent>
      </Card>

      <Card id="reviews" className="scroll-mt-20">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Reviews</CardTitle>
          {product.rating_avg && (
            <div className="flex items-center gap-2">
              <span className="text-2xl font-semibold tabular-nums">{Number(product.rating_avg).toFixed(1)}</span>
              <StarRating rating={product.rating_avg} count={product.rating_count} size="lg" />
            </div>
          )}
        </CardHeader>
        <CardContent>
          <Suspense fallback={<ProductReviewsSkeleton />}>
            <ProductReviews slug={slug} searchParams={searchParams} />
          </Suspense>
        </CardContent>
      </Card>
    </div>
  )
}

function PriceSummary({ product }: { product: ProductDetail }) {
  const sellers = product.offers.filter((offer) => offer.in_stock).length
  if (!product.min_price) {
    return (
      <div className="space-y-1">
        <Badge variant="secondary">Out of stock</Badge>
        <p className="text-sm text-muted-foreground">No seller has this in stock right now.</p>
      </div>
    )
  }
  return (
    <div className="space-y-1">
      <p className="text-3xl font-semibold tabular-nums">{formatBRL(product.min_price)}</p>
      <p className="text-sm text-muted-foreground">
        {sellers > 1 ? `Lowest of ${sellers} sellers in stock` : "From 1 seller"} ·{" "}
        {formatInteger(product.sales_count)} sold
      </p>
    </div>
  )
}

function Dimensions({ product }: { product: ProductDetail }) {
  const { weight_g, length_cm, width_cm, height_cm } = product.dimensions
  const rows = [
    ["Weight", weight_g === null ? null : weight_g >= 1000 ? `${(weight_g / 1000).toFixed(1)} kg` : `${weight_g} g`],
    ["Length", length_cm === null ? null : `${length_cm} cm`],
    ["Width", width_cm === null ? null : `${width_cm} cm`],
    ["Height", height_cm === null ? null : `${height_cm} cm`],
  ].filter((row): row is [string, string] => row[1] !== null)
  if (rows.length === 0) return null

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-medium">Dimensions</h2>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
