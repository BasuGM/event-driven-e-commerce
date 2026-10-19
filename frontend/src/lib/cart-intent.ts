/**
 * "Add to cart" while logged out: the intent (offer + quantity) rides through login/registration
 * in the `next` URL as `?add=<offer>.<quantity>.<nonce>` and is replayed once on the product page.
 * The nonce is claimed in sessionStorage before adding, so a reload or going back (which can
 * bring the same URL again) never adds it twice.
 */

export const INTENT_PARAM = "add"
const CLAIMED_KEY = "cart-intents-claimed"
const INTENT = /^(\d{1,10})\.(\d{1,2})\.([0-9a-f]{16})$/

export type CartIntent = { offerId: number; quantity: number; nonce: string }

/** crypto.getRandomValues, not randomUUID: the latter only exists in secure contexts. */
export function newNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8))
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")
}

export function withIntent(path: string, intent: CartIntent): string {
  const value = `${intent.offerId}.${intent.quantity}.${intent.nonce}`
  return `${path}${path.includes("?") ? "&" : "?"}${INTENT_PARAM}=${value}`
}

export function parseIntent(raw: string | string[] | undefined): CartIntent | null {
  const match = INTENT.exec(Array.isArray(raw) ? (raw[0] ?? "") : (raw ?? ""))
  if (!match) return null
  const quantity = Number(match[2])
  if (quantity < 1 || quantity > 10) return null
  return { offerId: Number(match[1]), quantity, nonce: match[3] }
}

/** True the first time a nonce is seen in this tab; false on every later call. */
export function claimIntent(storage: Storage, nonce: string): boolean {
  let claimed: string[] = []
  try {
    claimed = JSON.parse(storage.getItem(CLAIMED_KEY) ?? "[]")
  } catch {
    claimed = []
  }
  if (claimed.includes(nonce)) return false
  storage.setItem(CLAIMED_KEY, JSON.stringify([...claimed.slice(-19), nonce]))
  return true
}
