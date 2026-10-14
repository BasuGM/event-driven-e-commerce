"use client"

import { Check, Loader2, ShoppingBag } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState, useTransition } from "react"

import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { browserApi, ensureCsrf, NETWORK_PROBLEM, toProblem } from "@/lib/api/browser"
import { loginHref } from "@/lib/urls"

const QUANTITIES = Array.from({ length: 10 }, (_, i) => String(i + 1))

/** Quantity + "Add to cart" for one offer. Logged-out visitors are sent to log in first. */
// returnTo comes from the page (not usePathname): reading the URL in a client component would
// block the product page's prerendered shell.
export function AddToCart({ offerId, label, returnTo }: { offerId: number; label: string; returnTo: string }) {
  const router = useRouter()
  const [quantity, setQuantity] = useState("1")
  const [status, setStatus] = useState<{ kind: "added" | "error"; message: string } | null>(null)
  const [pending, startTransition] = useTransition()

  const add = () =>
    startTransition(async () => {
      setStatus(null)
      try {
        await ensureCsrf()
        const { error, response } = await browserApi.POST("/api/cart/items/", {
          body: { offer_id: offerId, quantity: Number(quantity) },
        })
        if (response.status === 401) {
          router.push(loginHref(returnTo))
          return
        }
        if (!response.ok) {
          setStatus({ kind: "error", message: toProblem(response.status, error).message })
          return
        }
        setStatus({ kind: "added", message: "Added to cart" })
        router.refresh() // header cart count
      } catch {
        setStatus({ kind: "error", message: NETWORK_PROBLEM.message })
      }
    })

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center justify-end gap-2">
        <Select value={quantity} onValueChange={setQuantity}>
          <SelectTrigger size="sm" className="w-16" aria-label={`Quantity for ${label}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {QUANTITIES.map((q) => (
              <SelectItem key={q} value={q}>
                {q}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" onClick={add} disabled={pending} aria-label={`Add to cart: ${label}`}>
          {pending ? <Loader2 className="animate-spin" /> : <ShoppingBag />}
          <span className="hidden sm:inline">Add to cart</span>
        </Button>
      </div>
      {status && (
        <p
          role="status"
          className={status.kind === "error" ? "text-xs text-destructive" : "flex items-center gap-1 text-xs text-success"}
        >
          {status.kind === "added" && <Check className="size-3" aria-hidden />}
          {status.message}
          {status.kind === "added" && (
            <Link href="/cart" className="ml-1 underline underline-offset-2">
              View cart
            </Link>
          )}
        </p>
      )}
    </div>
  )
}
