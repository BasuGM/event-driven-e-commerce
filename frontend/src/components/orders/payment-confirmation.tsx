import { Loader2 } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { components } from "@/lib/api/schema"

type OrderPayment = components["schemas"]["OrderPayment"]

/**
 * Shown while the customer is back from the provider and its webhook hasn't arrived
 * (payment.status "processing", stored server-side, so it survives a reload). No timers: the
 * live stream refreshes the page when the order changes. Past the confirmation window the
 * message changes and Pay is offered again (same payment, no double charge).
 */
export function PaymentConfirmation({ payment }: { payment: OrderPayment | null }) {
  if (payment?.status !== "processing") return null
  if (payment.confirmation_overdue) {
    return (
      <Alert role="status">
        <AlertTitle>Still waiting for the payment provider</AlertTitle>
        <AlertDescription>
          This page updates as soon as the provider confirms. If you didn&apos;t complete the payment, you can try again.
        </AlertDescription>
      </Alert>
    )
  }
  return (
    <Alert role="status">
      <Loader2 className="animate-spin" aria-hidden />
      <AlertTitle>Confirming your payment…</AlertTitle>
      <AlertDescription>This usually takes a few seconds; the page updates by itself.</AlertDescription>
    </Alert>
  )
}
