"use client"

import { CreditCard, Loader2, XCircle } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState, useTransition } from "react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { browserApi, ensureCsrf, NETWORK_PROBLEM, toProblem } from "@/lib/api/browser"
import { formatBRL } from "@/lib/format"

const MESSAGES: Record<string, string> = {
  reservation_expired: "Too late: the stock hold expired, so the order was canceled and the items released.",
  invalid_transition: "This order can no longer be changed. It may have been paid, canceled or expired.",
}

export function OrderActions({
  orderId,
  total,
  canPay,
  canCancel,
  paymentsEnabled,
  paymentInProgress = false,
}: {
  orderId: string
  total: string
  canPay: boolean
  canCancel: boolean
  paymentsEnabled: boolean
  /** Back from the provider, its webhook not here yet: paying again would only confuse things */
  paymentInProgress?: boolean
}) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const act = (name: string, request: () => Promise<{ response: Response; error?: unknown }>) =>
    startTransition(async () => {
      setBusy(name)
      setError(null)
      try {
        await ensureCsrf()
        const { response, error } = await request()
        if (!response.ok) {
          const problem = toProblem(response.status, error)
          setError(MESSAGES[problem.code] ?? problem.message)
        }
      } catch {
        setError(NETWORK_PROBLEM.message)
      } finally {
        setBusy(null)
        router.refresh() // even a 409 changed state (e.g. canceled on expiry)
      }
    })

  const path = { params: { path: { order_id: orderId } } }
  // Creates (or reuses) the payment, then leaves for the provider's hosted page. The provider
  // sends the customer back here (?payment=processing) and confirms by webhook.
  const pay = () =>
    startTransition(async () => {
      setBusy("pay")
      setError(null)
      try {
        await ensureCsrf()
        const { data, error, response } = await browserApi.POST("/api/orders/{order_id}/payment/", path)
        if (data) {
          window.location.assign(data.redirect_url)
          return // keep the spinner while the browser navigates away
        }
        const problem = toProblem(response.status, error)
        setError(MESSAGES[problem.code] ?? problem.message)
        router.refresh()
      } catch {
        setError(NETWORK_PROBLEM.message)
      }
      setBusy(null)
    })
  const cancel = () => act("cancel", () => browserApi.POST("/api/orders/{order_id}/cancel/", path))

  if (!canPay && !canCancel) return null
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {paymentsEnabled && canPay && paymentInProgress && (
          <Button disabled>
            <Loader2 className="animate-spin" aria-hidden />
            Payment in progress
          </Button>
        )}
        {paymentsEnabled && canPay && !paymentInProgress && (
          <Button onClick={pay} disabled={pending}>
            {busy === "pay" ? <Loader2 className="animate-spin" /> : <CreditCard />}
            Pay {formatBRL(total)}
          </Button>
        )}
        {canCancel && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button size="sm" variant="ghost" disabled={pending}>
                {busy === "cancel" ? <Loader2 className="animate-spin" /> : <XCircle />}
                Cancel order
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Cancel this order?</AlertDialogTitle>
                <AlertDialogDescription>Stock will be released.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep order</AlertDialogCancel>
                <AlertDialogAction variant="destructive" onClick={cancel}>
                  Cancel order
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
