"use client"

import { useRouter } from "next/navigation"
import { useEffect, useRef, useState } from "react"

import type { components } from "@/lib/api/schema"

type OrderDetail = components["schemas"]["OrderDetail"]

/** What the stream sends (the same values as the order detail API), plus its version. */
export type OrderSnapshot = Pick<
  OrderDetail,
  "status" | "status_history" | "payment" | "can_pay" | "can_cancel" | "reservation_expires_at"
> & { version: string }

export type LiveConnection = "connecting" | "live" | "reconnecting" | "polling" | "ended"

export const FALLBACK_POLL_MS = 15_000

/**
 * Live order updates over Server-Sent Events (GET /api/orders/<id>/stream/).
 *
 * The server sends the order's current snapshot on connect and whenever it changes. The page
 * is a Server Component, so instead of patching it client-side we router.refresh() when a
 * snapshot's version differs from the version the page was rendered with: one render path,
 * and changes are rare (a few per order). EventSource reconnects by itself (with
 * Last-Event-ID, so the server skips a state we already have). Only if the source is closed
 * for good (e.g. the stream service is down: non-200) do we fall back to a slow refresh.
 */
export function useOrderLive(orderId: string, renderedVersion: string, enabled = true) {
  const router = useRouter()
  const [snapshot, setSnapshot] = useState<OrderSnapshot | null>(null)
  const [connection, setConnection] = useState<LiveConnection>(enabled ? "connecting" : "ended")
  const renderedRef = useRef(renderedVersion)
  renderedRef.current = renderedVersion

  useEffect(() => {
    if (!enabled) {
      setConnection("ended")
      return
    }
    let poll: number | undefined
    const startPolling = () => {
      setConnection("polling")
      poll ??= window.setInterval(() => router.refresh(), FALLBACK_POLL_MS)
    }
    if (typeof EventSource === "undefined") {
      startPolling()
      return () => window.clearInterval(poll)
    }

    const source = new EventSource(`/api/orders/${orderId}/stream/`)
    source.onopen = () => setConnection("live")
    source.addEventListener("snapshot", (event) => {
      const next = JSON.parse((event as MessageEvent<string>).data) as OrderSnapshot
      setSnapshot(next)
      if (next.version !== renderedRef.current) router.refresh()
    })
    source.addEventListener("end", () => {
      source.close()
      setConnection("ended")
    })
    source.onerror = () => {
      // CONNECTING = EventSource is retrying by itself; CLOSED = it gave up (non-200 response)
      if (source.readyState === EventSource.CLOSED) startPolling()
      else setConnection("reconnecting")
    }
    return () => {
      source.close()
      window.clearInterval(poll)
    }
  }, [orderId, enabled, router])

  return { snapshot, connection }
}
