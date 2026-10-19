import { INTENT_PARAM, parseIntent } from "@/lib/cart-intent"

import { CartIntentReplay } from "./cart-intent-replay"

/** Reads `?add=` (an Add to cart started while logged out). Render under <Suspense>. */
export async function PendingCartIntent({
  productPath,
  searchParams,
}: {
  productPath: string
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const intent = parseIntent((await searchParams)[INTENT_PARAM])
  return intent ? <CartIntentReplay intent={intent} productPath={productPath} /> : null
}
