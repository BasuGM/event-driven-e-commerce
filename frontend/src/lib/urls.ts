/** Login URL that brings you back to `next` afterwards. */
export function loginHref(next: string): string {
  return `/login?next=${encodeURIComponent(next)}`
}

/** Only same-site relative paths are allowed as a post-login redirect (no open redirects). */
export function safeNext(next: string | null | undefined, fallback = "/"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback
  return next
}
