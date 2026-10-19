import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Offer } from "@/lib/api/client"
import { formatBRL } from "@/lib/format"
import { cn } from "@/lib/utils"

import { AddToCart } from "./add-to-cart"

function titleCase(value: string): string {
  return value.replace(/\b\p{L}/gu, (c) => c.toUpperCase())
}

function sellerLabel(offer: Offer): string {
  return `Seller ${offer.seller_id.slice(0, 8)}`
}

function Availability({ offer }: { offer: Offer }) {
  return offer.in_stock ? <Badge variant="success">In stock</Badge> : <Badge variant="secondary">Out of stock</Badge>
}

function BuyOffer({ offer, productSlug }: { offer: Offer; productSlug: string }) {
  if (!offer.in_stock) return null
  return (
    <AddToCart
      offerId={offer.id}
      label={`seller ${offer.seller_id.slice(0, 8)}, ${formatBRL(offer.price)}`}
      returnTo={`/shop/${productSlug}`}
    />
  )
}

/** A table from md up; stacked cards below, so price, availability and Add to cart fit at 375px. */
export function OffersTable({ offers, productSlug }: { offers: Offer[]; productSlug: string }) {
  // Offers arrive cheapest first; the best price is the cheapest one you can actually buy.
  const best = offers.find((offer) => offer.in_stock)

  return (
    <>
      <ul className="space-y-3 md:hidden" aria-label="Sellers">
        {offers.map((offer) => {
          const isBest = offer.id === best?.id
          return (
            <li key={offer.id} className={cn("space-y-3 rounded-lg border p-3", isBest && "bg-success/5")}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 space-y-0.5">
                  <p className="font-mono text-xs font-medium">{sellerLabel(offer)}</p>
                  <p className="text-sm text-muted-foreground">
                    {titleCase(offer.seller_city)}, {offer.seller_state}
                  </p>
                </div>
                {isBest && <Badge variant="success">Best price</Badge>}
              </div>
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold tabular-nums">{formatBRL(offer.price)}</p>
                <Availability offer={offer} />
              </div>
              <BuyOffer offer={offer} productSlug={productSlug} />
            </li>
          )
        })}
      </ul>

      <div className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Seller</TableHead>
              <TableHead>Location</TableHead>
              <TableHead className="text-right">Price</TableHead>
              <TableHead className="text-right">Availability</TableHead>
              <TableHead className="text-right">
                <span className="sr-only">Buy</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {offers.map((offer) => {
              const isBest = offer.id === best?.id
              return (
                <TableRow key={offer.id} className={cn(isBest && "bg-success/5 hover:bg-success/10")}>
                  <TableCell className="font-medium">
                    <span className="font-mono text-xs">{sellerLabel(offer)}</span>
                    {isBest && (
                      <Badge variant="success" className="ml-2">
                        Best price
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {titleCase(offer.seller_city)}, {offer.seller_state}
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">{formatBRL(offer.price)}</TableCell>
                  <TableCell className="text-right">
                    <Availability offer={offer} />
                  </TableCell>
                  <TableCell className="text-right">
                    <BuyOffer offer={offer} productSlug={productSlug} />
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </>
  )
}
