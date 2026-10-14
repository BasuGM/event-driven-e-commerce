import type { Metadata } from "next"
import { redirect } from "next/navigation"
import { Suspense } from "react"

import { AuthCard } from "@/components/auth/auth-card"
import { RegisterForm } from "@/components/auth/register-form"
import { Skeleton } from "@/components/ui/skeleton"
import { safeNext } from "@/lib/urls"
import { getMe } from "@/lib/api/server"

export const metadata: Metadata = { title: "Create an account" }

export default function RegisterPage({ searchParams }: PageProps<"/register">) {
  return (
    <AuthCard title="Create an account" description="Shop the Olist catalog and track your orders.">
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <Register searchParams={searchParams} />
      </Suspense>
    </AuthCard>
  )
}

async function Register({ searchParams }: { searchParams: PageProps<"/register">["searchParams"] }) {
  const raw = (await searchParams).next
  const next = safeNext(Array.isArray(raw) ? raw[0] : raw)
  if ((await getMe()).user) redirect(next)
  return <RegisterForm next={next} />
}
