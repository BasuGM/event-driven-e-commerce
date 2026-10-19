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

const MESSAGES: Record<string, string> = {
  reservation_expired: "Too late: the stock hold expired, so the order was canceled and the items released.",
  invalid_transition: "This order can no longer be changed. It may have been paid, canceled or expired.",
}

export function OrderActions({
  orderId,
  canPay,
  canCancel,
  paymentsEnabled,
}: {
  orderId: string
  canPay: boolean
  canCancel: boolean
  paymentsEnabled: boolean
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
  const pay = (outcome: "success" | "fail") =>
    act(outcome, () => browserApi.POST("/api/orders/{order_id}/pay/", { ...path, body: { outcome } }))
  const cancel = () => act("cancel", () => browserApi.POST("/api/orders/{order_id}/cancel/", path))

  if (!canPay && !canCancel) return null
  return (
    <div className="space-y-3">
      {paymentsEnabled && canPay && (
        <div className="space-y-2 rounded-lg border border-dashed p-3">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Dev only: simulate payment</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => pay("success")} disabled={pending}>
              {busy === "success" ? <Loader2 className="animate-spin" /> : <CreditCard />}
              Simulate payment success
            </Button>
            <Button size="sm" variant="outline" onClick={() => pay("fail")} disabled={pending}>
              {busy === "fail" && <Loader2 className="animate-spin" />}
              Simulate payment failure
            </Button>
          </div>
        </div>
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
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
