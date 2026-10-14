"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Loader2 } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Controller, useForm, type Path } from "react-hook-form"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { browserApi, ensureCsrf, NETWORK_PROBLEM, toProblem } from "@/lib/api/browser"
import { safeNext } from "@/lib/urls"

// Mirrors RegisterRequest; Django's password validators still run on the server.
export const registerSchema = z.object({
  name: z.string().trim().min(1, "Enter your name.").max(150),
  email: z.email("Enter a valid email address."),
  password: z.string().min(8, "Use at least 8 characters."),
})
type RegisterValues = z.infer<typeof registerSchema>

const FIELDS: { name: Path<RegisterValues>; label: string; type: string; autoComplete: string }[] = [
  { name: "name", label: "Full name", type: "text", autoComplete: "name" },
  { name: "email", label: "Email", type: "email", autoComplete: "email" },
  { name: "password", label: "Password", type: "password", autoComplete: "new-password" },
]

export function RegisterForm({ next }: { next?: string }) {
  const router = useRouter()
  const [formError, setFormError] = useState<string | null>(null)
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { name: "", email: "", password: "" },
  })

  async function onSubmit(values: RegisterValues) {
    setFormError(null)
    try {
      await ensureCsrf()
      const { error, response } = await browserApi.POST("/api/auth/register/", { body: values })
      if (!response.ok) {
        const problem = toProblem(response.status, error)
        // Map server field errors (duplicate email, weak password) onto the form
        for (const [field, messages] of Object.entries(problem.fieldErrors)) {
          const target = field === "non_field_errors" ? "password" : field
          if (FIELDS.some((f) => f.name === target)) {
            form.setError(target as Path<RegisterValues>, { message: messages.join(" ") })
          }
        }
        if (!Object.keys(problem.fieldErrors).length) setFormError(problem.message)
        return
      }
      router.replace(safeNext(next))
      router.refresh()
    } catch {
      setFormError(NETWORK_PROBLEM.message)
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-6">
      <FieldGroup>
        {FIELDS.map(({ name, label, type, autoComplete }) => (
          <Controller
            key={name}
            name={name}
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor={`register-${name}`}>{label}</FieldLabel>
                <Input
                  {...field}
                  id={`register-${name}`}
                  type={type}
                  autoComplete={autoComplete}
                  aria-invalid={fieldState.invalid}
                />
                {name === "password" && !fieldState.invalid && (
                  <FieldDescription>At least 8 characters; avoid common passwords.</FieldDescription>
                )}
                {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
              </Field>
            )}
          />
        ))}
      </FieldGroup>
      {formError && (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting && <Loader2 className="animate-spin" />}
        Create account
      </Button>
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link
          href={next ? `/login?next=${encodeURIComponent(next)}` : "/login"}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          Log in
        </Link>
      </p>
    </form>
  )
}
