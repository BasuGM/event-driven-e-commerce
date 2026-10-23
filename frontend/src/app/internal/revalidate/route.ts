import { timingSafeEqual } from "node:crypto"

import { revalidateTag } from "next/cache"
import { z } from "zod"

import { REVALIDATABLE_TAG } from "@/lib/cache-tags"

/**
 * Cache invalidation for the backend's event consumers (not for browsers): they POST the tags
 * of products whose stock or sales changed. Protected by a shared secret (REVALIDATE_SECRET).
 * Deliberately outside /api, which next.config rewrites to Django.
 */

const bodySchema = z.object({
  tags: z.array(z.string().regex(REVALIDATABLE_TAG)).min(1).max(100),
})

function authorized(provided: string | null): boolean {
  const secret = process.env.REVALIDATE_SECRET
  if (!secret || !provided) return false
  const a = Buffer.from(provided)
  const b = Buffer.from(secret)
  return a.length === b.length && timingSafeEqual(a, b)
}

export async function POST(request: Request) {
  if (!authorized(request.headers.get("x-revalidate-secret"))) {
    return Response.json({ detail: "Unauthorized" }, { status: 401 })
  }
  const parsed = bodySchema.safeParse(await request.json().catch(() => null))
  if (!parsed.success) {
    return Response.json({ detail: "Invalid tags", issues: parsed.error.issues }, { status: 400 })
  }
  const tags = [...new Set(parsed.data.tags)]
  // expire: 0 = never serve the stale entry again: the next visit re-fetches (stock must be fresh)
  for (const tag of tags) revalidateTag(tag, { expire: 0 })
  return Response.json({ revalidated: tags.length })
}
