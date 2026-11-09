import { useSyncExternalStore } from "react"

const subscribe = () => () => {}

/**
 * False in the server render and during hydration, true once React has hydrated this component
 * (and on every later client render).
 *
 * Controls that act through JavaScript (Pay, Cancel, Place order, the auth forms' submit, Add to
 * cart, Retry) render disabled until then. Before hydration a server-rendered button looks ready
 * but its click does nothing (seen in e2e right after a full page load), and a form would fall
 * back to a native submit. Playwright already waits for a control to be enabled.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true, // client
    () => false, // server render and hydration
  )
}
