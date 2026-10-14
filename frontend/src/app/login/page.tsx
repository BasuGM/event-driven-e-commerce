import type { Metadata } from "next"
import { redirect } from "next/navigation"
import { Suspense } from "react"

import { AuthCard } from "@/components/auth/auth-card"
import { LoginForm } from "@/components/auth/login-form"
import { Skeleton } from "@/components/ui/skeleton"
import { safeNext } from "@/lib/urls"
import { getMe } from "@/lib/api/server"

export const metadata: Metadata = { title: "Log in" }

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <AuthCard title="Log in" description="Use your email and password to continue.">
      <Suspense fallback={<FormSkeleton />}>
        <Login searchParams={searchParams} />
      </Suspense>
    </AuthCard>
  )
}

async function Login({ searchParams }: { searchParams: PageProps<"/login">["searchParams"] }) {
  const raw = (await searchParams).next
  const next = safeNext(Array.isArray(raw) ? raw[0] : raw)
  if ((await getMe()).user) redirect(next) // already logged in
  return <LoginForm next={next} />
}

function FormSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
    </div>
  )
}
