"use client"

import { useRouter } from "next/navigation"
import { useEffect } from "react"

export const REFRESH_MS = 10_000

/**
 * Re-renders the dashboard every 10 s while the tab is visible. A gentle poll rather than the
 * SSE stream service: during a replay the projections change hundreds of times a second, so a
 * per-change stream would need server-side coalescing anyway, and a dashboard isn't
 * latency-critical.
 */
export function AutoRefresh() {
  const router = useRouter()
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") router.refresh()
    }, REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [router])
  return null
}
