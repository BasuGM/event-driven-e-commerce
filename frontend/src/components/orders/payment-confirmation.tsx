"use client"

import { Loader2 } from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

export const POLL_MS = 2_000
export const GIVE_UP_MS = 60_000

/**
 * Back from the payment provider (?payment=processing): the webhook confirms asynchronously, so
 * re-render the server page every POLL_MS until the order leaves "created", then drop the
 * param. Polling (not SSE) is enough for now; live order tracking is a later step.
 */
export function PaymentConfirmation({ orderId, status }: { orderId: string; status: string }) {
  const router = useRouter()
  const [gaveUp, setGaveUp] = useState(false)
  const waiting = status === "created"

  useEffect(() => {
    if (!waiting) {
      router.replace(`/orders/${orderId}`, { scroll: false })
      return
    }
    const poll = window.setInterval(() => router.refresh(), POLL_MS)
    const stop = window.setTimeout(() => {
      window.clearInterval(poll)
      setGaveUp(true)
    }, GIVE_UP_MS)
    return () => {
      window.clearInterval(poll)
      window.clearTimeout(stop)
    }
  }, [waiting, orderId, router])

  if (!waiting) return null
  return (
    <Alert role="status">
      {!gaveUp && <Loader2 className="animate-spin" aria-hidden />}
      <AlertTitle>{gaveUp ? "Still waiting for the payment provider" : "Confirming your payment…"}</AlertTitle>
      <AlertDescription>
        {gaveUp
          ? "We haven't heard back yet. This page updates when the provider confirms; you can also reload it."
          : "This usually takes a few seconds."}
      </AlertDescription>
    </Alert>
  )
}
