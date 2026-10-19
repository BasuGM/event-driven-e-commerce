"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { AlertTriangle, Loader2, RotateCw } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Controller, useForm, type Path } from "react-hook-form"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { browserApi, ensureCsrf, NETWORK_PROBLEM, toProblem, type ApiProblem } from "@/lib/api/browser"
import type { Cart, CartLine, Shipping } from "@/lib/api/client"
import { currentAttempt, fingerprint, settleAttempt } from "@/lib/checkout-attempt"
import { formatBRL } from "@/lib/format"

export const BR_STATES = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR",
  "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
] as const

// Mirrors ShippingAddressRequest in the API schema
export const shippingSchema = z.object({
  full_name: z.string().trim().min(1, "Enter the recipient's name.").max(120),
  street: z.string().trim().min(3, "Enter the street and number.").max(200),
  city: z.string().trim().min(2, "Enter the city.").max(100),
  state: z.enum(BR_STATES, { message: "Choose a state." }),
  zip_code: z.string().regex(/^\d{5}-\d{3}$/, "Use the format 01310-100."),
})
export type ShippingValues = z.infer<typeof shippingSchema>

/** 01310100 -> 01310-100 as you type */
export function maskCep(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 8)
  return digits.length > 5 ? `${digits.slice(0, 5)}-${digits.slice(5)}` : digits
}

const TEXT_FIELDS: { name: Path<ShippingValues>; label: string; autoComplete: string; placeholder?: string }[] = [
  { name: "full_name", label: "Full name", autoComplete: "name" },
  { name: "street", label: "Street and number", autoComplete: "street-address", placeholder: "Av. Paulista, 1000, apto 12" },
  { name: "city", label: "City", autoComplete: "address-level2" },
]

const CHECKOUT_TIMEOUT_MS = 15_000

/** Form defaults: the account's name, plus the address of the last order (if any) to edit. */
export function shippingDefaults(defaultName: string, last: Shipping | null): ShippingValues {
  const state = BR_STATES.find((uf) => uf === last?.state) // unknown values stay unselected
  return {
    full_name: defaultName,
    street: last?.street ?? "",
    city: last?.city ?? "",
    // undefined = "Choose…" placeholder; zod still requires a state on submit
    state: state as ShippingValues["state"],
    zip_code: last ? maskCep(last.zip_code) : "",
  }
}

export function CheckoutForm({
  lines,
  totals,
  defaultName,
  lastShipping = null,
}: {
  lines: CartLine[]
  totals: Pick<Cart, "total" | "item_count">
  defaultName: string
  lastShipping?: Shipping | null
}) {
  const router = useRouter()
  const [problem, setProblem] = useState<ApiProblem | null>(null)
  const form = useForm<ShippingValues>({
    resolver: zodResolver(shippingSchema),
    defaultValues: shippingDefaults(defaultName, lastShipping),
  })

  async function placeOrder(shipping: ShippingValues) {
    setProblem(null)
    // Same cart + same address = same attempt = same Idempotency-Key, even across a reload
    const attempt = currentAttempt(
      window.sessionStorage,
      fingerprint({ cart: lines.map((l) => [l.offer_id, l.quantity]), shipping }),
    )
    let status = 0
    try {
      await ensureCsrf()
      const { data, error, response } = await browserApi.POST("/api/checkout/", {
        params: { header: { "Idempotency-Key": attempt.key } },
        body: { shipping },
        signal: AbortSignal.timeout(CHECKOUT_TIMEOUT_MS),
      })
      status = response.status
      if (data) {
        settleAttempt(window.sessionStorage, status)
        router.push(`/orders/${data.id}`)
        router.refresh()
        return
      }
      const result = toProblem(status, error)
      if (status >= 500) {
        setProblem({ ...NETWORK_PROBLEM, status, message: "The server had a problem confirming your order." })
      } else {
        for (const [field, messages] of Object.entries(result.fieldErrors)) {
          if (field in shipping) form.setError(field as Path<ShippingValues>, { message: messages.join(" ") })
        }
        setProblem(result)
      }
    } catch {
      setProblem(NETWORK_PROBLEM) // timeout or no connection: outcome unknown
    } finally {
      // Unknown outcomes keep the key so "Retry" can't create a second order
      settleAttempt(window.sessionStorage, status)
    }
  }

  const retryable = problem !== null && (problem.status === 0 || problem.status >= 500)

  return (
    <form onSubmit={form.handleSubmit(placeOrder)} noValidate className="space-y-6">
      <FieldGroup>
        {TEXT_FIELDS.map(({ name, label, autoComplete, placeholder }) => (
          <Controller
            key={name}
            name={name}
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor={`ship-${name}`}>{label}</FieldLabel>
                <Input
                  {...field}
                  id={`ship-${name}`}
                  autoComplete={autoComplete}
                  placeholder={placeholder}
                  aria-invalid={fieldState.invalid}
                />
                {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
              </Field>
            )}
          />
        ))}
        <div className="grid gap-4 sm:grid-cols-2">
          <Controller
            name="state"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="ship-state">State</FieldLabel>
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger id="ship-state" className="w-full" aria-invalid={fieldState.invalid} onBlur={field.onBlur}>
                    <SelectValue placeholder="Choose…" />
                  </SelectTrigger>
                  <SelectContent>
                    {BR_STATES.map((uf) => (
                      <SelectItem key={uf} value={uf}>
                        {uf}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
              </Field>
            )}
          />
          <Controller
            name="zip_code"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="ship-zip">CEP</FieldLabel>
                <Input
                  {...field}
                  id="ship-zip"
                  inputMode="numeric"
                  autoComplete="postal-code"
                  placeholder="01310-100"
                  onChange={(e) => field.onChange(maskCep(e.target.value))}
                  aria-invalid={fieldState.invalid}
                />
                {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
              </Field>
            )}
          />
        </div>
      </FieldGroup>

      {problem && <CheckoutProblem problem={problem} />}

      {/* Phones: the order summary card sits below the form, so show the total before you commit */}
      <p className="flex items-baseline justify-between gap-4 text-sm md:hidden" data-testid="checkout-mobile-total">
        <span className="text-muted-foreground">
          Total ({totals.item_count} {totals.item_count === 1 ? "item" : "items"})
        </span>
        <span className="text-base font-semibold tabular-nums">{formatBRL(totals.total)}</span>
      </p>
      <Button type="submit" size="lg" className="w-full" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? <Loader2 className="animate-spin" /> : retryable ? <RotateCw /> : null}
        {retryable ? "Retry placing order" : "Place order"}
      </Button>
      <p className="text-center text-xs text-muted-foreground">
        Stock is held for 15 minutes after you place the order while you pay.
      </p>
    </form>
  )
}

function CheckoutProblem({ problem }: { problem: ApiProblem }) {
  const retryable = problem.status === 0 || problem.status >= 500
  return (
    <div role="alert" className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm">
      <p className="flex items-center gap-2 font-medium text-destructive">
        <AlertTriangle className="size-4 shrink-0" aria-hidden />
        {problem.code === "out_of_stock" ? "Some items just sold out" : problem.message}
      </p>
      {problem.code === "out_of_stock" && problem.lines && (
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          {problem.lines.map((line) => (
            <li key={line.offer_id}>
              {line.product}: you asked for {line.requested}, {line.available === 0 ? "none are" : `only ${line.available} ${line.available === 1 ? "is" : "are"}`} left.
            </li>
          ))}
        </ul>
      )}
      {retryable && (
        <p className="text-muted-foreground">
          Your order may or may not have gone through. Retrying is safe: it won&apos;t create a second order.
        </p>
      )}
      {(problem.code === "out_of_stock" || problem.code === "empty_cart") && (
        <Link href="/cart" className="font-medium underline underline-offset-4">
          Review your cart
        </Link>
      )}
    </div>
  )
}
