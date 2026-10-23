import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const revalidateTag = vi.fn()
vi.mock("next/cache", () => ({ revalidateTag: (...args: unknown[]) => revalidateTag(...args) }))

import { POST } from "./route"

function post(body: unknown, secret?: string) {
  return POST(
    new Request("http://frontend/internal/revalidate", {
      method: "POST",
      headers: { "content-type": "application/json", ...(secret ? { "x-revalidate-secret": secret } : {}) },
      body: JSON.stringify(body),
    }),
  )
}

describe("POST /internal/revalidate", () => {
  beforeEach(() => {
    vi.stubEnv("REVALIDATE_SECRET", "s3cret")
    revalidateTag.mockReset()
  })
  afterEach(() => vi.unstubAllEnvs())

  it("rejects a missing or wrong secret", async () => {
    expect((await post({ tags: ["products"] })).status).toBe(401)
    expect((await post({ tags: ["products"] }, "nope")).status).toBe(401)
    expect(revalidateTag).not.toHaveBeenCalled()
  })

  it("is closed when no secret is configured", async () => {
    vi.stubEnv("REVALIDATE_SECRET", "")
    expect((await post({ tags: ["products"] }, "")).status).toBe(401)
  })

  it("rejects tags it doesn't know", async () => {
    expect((await post({ tags: ["user:1"] }, "s3cret")).status).toBe(400)
    expect((await post({ tags: [] }, "s3cret")).status).toBe(400)
    expect(revalidateTag).not.toHaveBeenCalled()
  })

  it("revalidates each product tag once, expiring it immediately", async () => {
    const response = await post({ tags: ["product:lamp-1a2b3c4d", "product:lamp-1a2b3c4d", "products"] }, "s3cret")

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ revalidated: 2 })
    expect(revalidateTag.mock.calls).toEqual([
      ["product:lamp-1a2b3c4d", { expire: 0 }],
      ["products", { expire: 0 }],
    ])
  })
})
