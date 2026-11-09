import { render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AutoRefresh, REFRESH_MS } from "./auto-refresh"

const refresh = vi.fn()
const router = { refresh }
vi.mock("next/navigation", () => ({ useRouter: () => router }))

describe("AutoRefresh", () => {
  let visibility: DocumentVisibilityState = "visible"
  beforeEach(() => {
    vi.useFakeTimers()
    refresh.mockReset()
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it("refreshes every 10 s while the tab is visible, not while hidden, and stops on unmount", () => {
    const { unmount } = render(<AutoRefresh />)
    vi.advanceTimersByTime(REFRESH_MS * 2)
    expect(refresh).toHaveBeenCalledTimes(2)

    visibility = "hidden"
    vi.advanceTimersByTime(REFRESH_MS * 3)
    expect(refresh).toHaveBeenCalledTimes(2)

    visibility = "visible"
    unmount()
    vi.advanceTimersByTime(REFRESH_MS * 3)
    expect(refresh).toHaveBeenCalledTimes(2)
  })
})
