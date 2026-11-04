import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { FALLBACK_POLL_MS, useOrderLive } from "./use-order-live"

const refresh = vi.fn()
const router = { refresh } // stable, like Next's useRouter()
vi.mock("next/navigation", () => ({ useRouter: () => router }))

/** A controllable EventSource: tests push snapshots and errors by hand. */
class FakeEventSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2
  static instances: FakeEventSource[] = []
  readyState = FakeEventSource.CONNECTING
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {}
  closed = false

  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    ;(this.listeners[type] ??= []).push(listener)
  }
  close() {
    this.closed = true
    this.readyState = FakeEventSource.CLOSED
  }
  open() {
    this.readyState = FakeEventSource.OPEN
    this.onopen?.()
  }
  emit(type: string, data: unknown) {
    for (const listener of this.listeners[type] ?? []) listener(new MessageEvent(type, { data: JSON.stringify(data) }))
  }
  fail(readyState: number) {
    this.readyState = readyState
    this.onerror?.()
  }
}

const snapshot = (version: string, status = "created") => ({
  status, status_history: [], payment: null, can_pay: true, can_cancel: true, reservation_expires_at: null, version,
})

describe("useOrderLive", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeEventSource.instances = []
    vi.stubGlobal("EventSource", FakeEventSource)
    refresh.mockReset()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it("connects to the order's stream and refreshes only when the version changes", () => {
    const { result } = renderHook(() => useOrderLive("abc", "v1"))
    const source = FakeEventSource.instances[0]
    expect(source.url).toBe("/api/orders/abc/stream/")

    act(() => source.open())
    expect(result.current.connection).toBe("live")

    act(() => source.emit("snapshot", snapshot("v1")))  // what the page already shows
    expect(refresh).not.toHaveBeenCalled()
    expect(result.current.snapshot?.version).toBe("v1")

    act(() => source.emit("snapshot", snapshot("v2", "approved")))  // something happened
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(result.current.snapshot?.status).toBe("approved")
  })

  it("does not refresh again once the page has re-rendered with that version", () => {
    const { rerender } = renderHook(({ version }) => useOrderLive("abc", version), { initialProps: { version: "v1" } })
    const source = FakeEventSource.instances[0]
    act(() => source.emit("snapshot", snapshot("v2")))
    rerender({ version: "v2" })  // router.refresh() delivered the new server render
    act(() => source.emit("snapshot", snapshot("v2")))
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it("stops on `end`", () => {
    const { result } = renderHook(() => useOrderLive("abc", "v1"))
    const source = FakeEventSource.instances[0]
    act(() => source.emit("end", {}))
    expect(source.closed).toBe(true)
    expect(result.current.connection).toBe("ended")
  })

  it("reports reconnecting while EventSource retries by itself (no polling)", () => {
    const { result } = renderHook(() => useOrderLive("abc", "v1"))
    act(() => FakeEventSource.instances[0].fail(FakeEventSource.CONNECTING))
    expect(result.current.connection).toBe("reconnecting")
    act(() => vi.advanceTimersByTime(FALLBACK_POLL_MS * 2))
    expect(refresh).not.toHaveBeenCalled()
  })

  it("falls back to a slow refresh when EventSource gives up", () => {
    const { result } = renderHook(() => useOrderLive("abc", "v1"))
    act(() => FakeEventSource.instances[0].fail(FakeEventSource.CLOSED))
    expect(result.current.connection).toBe("polling")

    act(() => vi.advanceTimersByTime(FALLBACK_POLL_MS - 1))
    expect(refresh).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(refresh).toHaveBeenCalledTimes(1)
    act(() => vi.advanceTimersByTime(FALLBACK_POLL_MS * 2))
    expect(refresh).toHaveBeenCalledTimes(3)
  })

  it("does nothing for a final order, and closes the source on unmount", () => {
    renderHook(() => useOrderLive("abc", "v1", false))
    expect(FakeEventSource.instances).toHaveLength(0)

    const { unmount } = renderHook(() => useOrderLive("abc", "v1"))
    unmount()
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })
})
