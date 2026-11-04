import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { GIVE_UP_MS, PaymentConfirmation, POLL_MS } from "./payment-confirmation"

const refresh = vi.fn()
const replace = vi.fn()
const router = { refresh, replace } // stable, like Next's useRouter()
vi.mock("next/navigation", () => ({ useRouter: () => router }))

describe("PaymentConfirmation", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    refresh.mockReset()
    replace.mockReset()
  })
  afterEach(() => vi.useRealTimers())

  it("polls while the order is unpaid, then gives up after a minute", () => {
    render(<PaymentConfirmation orderId="abc" status="created" />)
    expect(screen.getByRole("status")).toHaveTextContent("Confirming your payment…")

    act(() => vi.advanceTimersByTime(POLL_MS * 3))
    expect(refresh).toHaveBeenCalledTimes(3)

    act(() => vi.advanceTimersByTime(GIVE_UP_MS))
    const calls = refresh.mock.calls.length
    expect(screen.getByRole("status")).toHaveTextContent("Still waiting for the payment provider")
    act(() => vi.advanceTimersByTime(POLL_MS * 5))
    expect(refresh).toHaveBeenCalledTimes(calls) // stopped polling
  })

  it("stops and drops the ?payment param once the order is paid", () => {
    const { rerender } = render(<PaymentConfirmation orderId="abc" status="created" />)
    rerender(<PaymentConfirmation orderId="abc" status="approved" />)

    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    expect(replace).toHaveBeenCalledWith("/orders/abc", { scroll: false })
    act(() => vi.advanceTimersByTime(POLL_MS * 3))
    expect(refresh).not.toHaveBeenCalled()
  })
})
