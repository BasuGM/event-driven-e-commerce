import type { ProductListItem } from "@/lib/api/client"

import { ProductCard } from "./product-card"

export function ProductGrid({ products }: { products: ProductListItem[] }) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-4">
      {products.map((product) => (
        <li key={product.slug}>
          <ProductCard product={product} />
        </li>
      ))}
    </ul>
  )
}
