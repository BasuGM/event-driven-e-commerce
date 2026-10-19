"use client"

import { useRouter } from "next/navigation"
import { useEffect, useRef, useState } from "react"

import { browserApi, ensureCsrf, NETWORK_PROBLEM, toProblem } from "@/lib/api/browser"
import { claimIntent, type CartIntent } from "@/lib/cart-intent"

import { CartStatusMessage, type CartStatus } from "./add-to-cart"

/**
 * Adds the item a logged-out visitor tried to add, once they're back from login/registration.
 * Order matters: claim the nonce (no second add on reload/back), add, refresh the header badge
 * while `?add=` is still in the URL (so this component stays mounted to show the result), then
 * drop the param with history.replaceState, which doesn't re-render server components.
 */
export function CartIntentReplay({ intent, productPath }: { intent: CartIntent; productPath: string }) {
  const router = useRouter()
  const [status, setStatus] = useState<CartStatus | null>(null)
  const started = useRef(false) // StrictMode runs effects twice in dev

  useEffect(() => {
    if (started.current) return
    started.current = true
    const stripParam = () => window.history.replaceState(null, "", productPath)
    if (!claimIntent(window.sessionStorage, intent.nonce)) {
      stripParam()
      return
    }
    void (async () => {
      try {
        await ensureCsrf()
        const { error, response } = await browserApi.POST("/api/cart/items/", {
          body: { offer_id: intent.offerId, quantity: intent.quantity },
        })
        if (response.ok) setStatus({ kind: "added", message: "Added to cart" })
        else setStatus({ kind: "error", message: toProblem(response.status, error).message })
      } catch {
        setStatus({ kind: "error", message: NETWORK_PROBLEM.message })
      }
      router.refresh()
      stripParam()
    })()
  }, [intent, productPath, router])

  return status ? <CartStatusMessage status={status} /> : null
}
