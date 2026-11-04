"use client"

import { WifiOff } from "lucide-react"
import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { useOrderLive } from "@/lib/use-order-live"

export const SHOW_DISCONNECTED_AFTER_MS = 5_000

/**
 * Keeps the order page live (see useOrderLive). Renders nothing while connected; a small badge
 * only when the connection has been down for a while, or when we fell back to slow polling.
 */
export function OrderLive({ orderId, version, enabled }: { orderId: string; version: string; enabled: boolean }) {
  const { connection } = useOrderLive(orderId, version, enabled)
  const [showReconnecting, setShowReconnecting] = useState(false)

  useEffect(() => {
    if (connection !== "reconnecting") {
      setShowReconnecting(false)
      return
    }
    const timer = window.setTimeout(() => setShowReconnecting(true), SHOW_DISCONNECTED_AFTER_MS)
    return () => window.clearTimeout(timer)
  }, [connection])

  if (connection === "polling") {
    return (
      <Badge variant="secondary" role="status">
        <WifiOff aria-hidden /> Live updates paused; refreshing every 15 s
      </Badge>
    )
  }
  if (showReconnecting) {
    return (
      <Badge variant="secondary" role="status">
        <WifiOff aria-hidden /> Reconnecting…
      </Badge>
    )
  }
  return null
}
