"use client"

import { useEffect } from "react"

/** Sets the tab title once the staff content has rendered (never in the server HTML). */
export function DocumentTitle({ title }: { title: string }) {
  useEffect(() => {
    document.title = `${title} · Staff · Olist Commerce`
  }, [title])
  return null
}
