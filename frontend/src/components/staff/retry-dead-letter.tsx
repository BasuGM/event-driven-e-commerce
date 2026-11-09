"use client"

import { Loader2, RotateCw } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState, useTransition } from "react"

import { Button } from "@/components/ui/button"
import { browserApi, ensureCsrf, NETWORK_PROBLEM, toProblem } from "@/lib/api/browser"
import { useHydrated } from "@/lib/use-hydrated"

/** Re-delivers a dead-lettered event to its stream (idempotent on the server). */
export function RetryDeadLetter({ entryId, retriedAt }: { entryId: string; retriedAt: string | null }) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const hydrated = useHydrated()
  const [error, setError] = useState<string | null>(null)

  if (retriedAt) return <span className="text-xs text-muted-foreground">Retried</span>

  const retry = () =>
    startTransition(async () => {
      setError(null)
      try {
        await ensureCsrf()
        const { response, error } = await browserApi.POST("/api/staff/dead-letters/{entry_id}/retry/", {
          params: { path: { entry_id: entryId } },
        })
        if (!response.ok) setError(toProblem(response.status, error).message)
        router.refresh()
      } catch {
        setError(NETWORK_PROBLEM.message)
      }
    })

  return (
    <div className="space-y-1">
      <Button size="sm" variant="outline" onClick={retry} disabled={!hydrated || pending} aria-label={`Retry dead letter ${entryId}`}>
        {pending ? <Loader2 className="animate-spin" /> : <RotateCw />}
        Retry
      </Button>
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
