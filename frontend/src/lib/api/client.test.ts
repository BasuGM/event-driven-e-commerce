// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/** A fetch that never answers, but rejects like the real one when its request is aborted. */
function hangingFetch(input: Request | string | URL, init?: RequestInit) {
  const signal = input instanceof Request ? input.signal : init?.signal
  return new Promise<Response>((_, reject) => {
    signal?.addEventListener("abort", () => reject(signal.reason))
  })
}

describe("API client timeout", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // Fake timers don't drive AbortSignal.timeout, so back it with a (faked) setTimeout.
    vi.spyOn(AbortSignal, "timeout").mockImplementation((ms: number) => {
      const controller = new AbortController()
      setTimeout(() => controller.abort(new DOMException("timed out", "TimeoutError")), ms)
      return controller.signal
    })
    vi.stubGlobal("fetch", vi.fn(hangingFetch))
    // The client captures fetch at module load, so import it fresh after stubbing.
    vi.resetModules()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it.each(["getStats", "getHealth"] as const)("%s rejects once the timeout elapses", async (fn) => {
    const client = await import("./client")
    let settled = false
    const result = client[fn]().finally(() => {
      settled = true
    })
    const assertion = expect(result).rejects.toMatchObject({ name: "TimeoutError" })

    await vi.advanceTimersByTimeAsync(client.TIMEOUT_MS - 1)
    expect(settled).toBe(false)

    await vi.advanceTimersByTimeAsync(1)
    await assertion
    expect(fetch).toHaveBeenCalledOnce()
  })
})
