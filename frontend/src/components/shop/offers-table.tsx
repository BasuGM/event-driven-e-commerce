import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Offer } from "@/lib/api/client"
import { formatBRL } from "@/lib/format"
import { cn } from "@/lib/utils"

import { AddToCart } from "./add-to-cart"

function titleCase(value: string): string {
  return value.replace(/\b\p{L}/gu, (c) => c.toUpperCase())
}

export function OffersTable({ offers, productSlug }: { offers: Offer[]; productSlug: string }) {
  // Offers arrive cheapest first; the best price is the cheapest one you can actually buy.
  const best = offers.find((offer) => offer.in_stock)

  return (
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
                <span className="font-mono text-xs">Seller {offer.seller_id.slice(0, 8)}</span>
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
                {offer.in_stock ? (
                  <Badge variant="success">In stock</Badge>
                ) : (
                  <Badge variant="secondary">Out of stock</Badge>
                )}
              </TableCell>
              <TableCell className="text-right">
                {offer.in_stock && (
                  <AddToCart
                    offerId={offer.id}
                    label={`seller ${offer.seller_id.slice(0, 8)}, ${formatBRL(offer.price)}`}
                    returnTo={`/shop/${productSlug}`}
                  />
                )}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
