"use client"

import { useLayoutEffect } from "react"

/**
 * Sets the tab title once the staff content has rendered (never in the server HTML), and keeps
 * it: Next re-applies the page metadata's neutral <title> whenever a metadata tree commits (each
 * router.refresh(), and on navigation the streamed metadata can land after this mounts), so a
 * one-off assignment gets overwritten. A MutationObserver on <head> restores it while mounted.
 * Layout effect: the observer disconnects synchronously in the commit that unmounts us, before
 * it could re-apply a staff title over the next page's metadata.
 */
export function DocumentTitle({ title }: { title: string }) {
  useLayoutEffect(() => {
    const full = `${title} · Staff · Olist Commerce`
    const apply = () => {
      if (document.title !== full) document.title = full
    }
    apply()
    const observer = new MutationObserver(apply)
    observer.observe(document.head, { childList: true, subtree: true, characterData: true })
    return () => observer.disconnect()
  }, [title])
  return null
}
