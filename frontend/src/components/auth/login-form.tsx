"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Loader2 } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Controller, useForm } from "react-hook-form"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { browserApi, ensureCsrf, NETWORK_PROBLEM, toProblem } from "@/lib/api/browser"
import { safeNext } from "@/lib/urls"

// Mirrors LoginRequest in the API schema
export const loginSchema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
})
type LoginValues = z.infer<typeof loginSchema>

export function LoginForm({ next }: { next?: string }) {
  const router = useRouter()
  const [formError, setFormError] = useState<string | null>(null)
  const form = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } })

  async function onSubmit(values: LoginValues) {
    setFormError(null)
    try {
      await ensureCsrf()
      const { error, response } = await browserApi.POST("/api/auth/login/", { body: values })
      if (!response.ok) {
        setFormError(toProblem(response.status, error).message)
        return
      }
      router.replace(safeNext(next))
      router.refresh() // re-render server components (header) with the new session
    } catch {
      setFormError(NETWORK_PROBLEM.message)
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-6">
      <FieldGroup>
        <Controller
          name="email"
          control={form.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="login-email">Email</FieldLabel>
              <Input {...field} id="login-email" type="email" autoComplete="email" aria-invalid={fieldState.invalid} />
              {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
            </Field>
          )}
        />
        <Controller
          name="password"
          control={form.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="login-password">Password</FieldLabel>
              <Input
                {...field}
                id="login-password"
                type="password"
                autoComplete="current-password"
                aria-invalid={fieldState.invalid}
              />
              {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
            </Field>
          )}
        />
      </FieldGroup>
      {formError && (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting && <Loader2 className="animate-spin" />}
        Log in
      </Button>
      <p className="text-center text-sm text-muted-foreground">
        New here?{" "}
        <Link
          href={next ? `/register?next=${encodeURIComponent(next)}` : "/register"}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          Create an account
        </Link>
      </p>
    </form>
  )
}
