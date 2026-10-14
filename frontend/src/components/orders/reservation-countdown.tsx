"use client"

import { Clock } from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

function remaining(expiresAt: string): number {
  return Math.max(0, new Date(expiresAt).getTime() - Date.now())
}

export function formatRemaining(ms: number): string {
  const total = Math.ceil(ms / 1000)
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${String(seconds).padStart(2, "0")}`
}

/** Counts down to the stock hold's expiry, then refreshes so the page shows the new state. */
export function ReservationCountdown({ expiresAt }: { expiresAt: string }) {
  const router = useRouter()
  const [ms, setMs] = useState<number | null>(null) // null until mounted: avoids a hydration mismatch

  useEffect(() => {
    const tick = () => {
      const left = remaining(expiresAt)
      setMs(left)
      return left
    }
    tick()
    const id = setInterval(() => {
      if (tick() === 0) {
        clearInterval(id)
        router.refresh()
      }
    }, 1000)
    return () => clearInterval(id)
  }, [expiresAt, router])

  if (ms === null) return null
  return (
    <p className="flex items-center gap-2 text-sm" role="timer" aria-live="off">
      <Clock className="size-4 text-muted-foreground" aria-hidden />
      {ms > 0 ? (
        <span>
          Stock held for <span className="font-semibold tabular-nums">{formatRemaining(ms)}</span>. Pay before it
          runs out.
        </span>
      ) : (
        <span className="text-destructive">The hold has expired; this order will be canceled.</span>
      )}
    </p>
  )
}
