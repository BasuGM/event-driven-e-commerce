import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { OrderDetail } from "@/lib/api/client"

import { OrderTimeline } from "./order-timeline"

const at = (minute: number) => `2026-11-09T10:${String(minute).padStart(2, "0")}:00Z`

describe("OrderTimeline", () => {
  it("labels the fulfilment and replay steps", () => {
    render(
      <OrderTimeline
        history={[
          { from_status: "", to_status: "created", reason: "replay_placed", created_at: at(0), occurred_at: at(0) },
          { from_status: "created", to_status: "approved", reason: "payment_succeeded", created_at: at(1), occurred_at: at(1) },
          { from_status: "approved", to_status: "invoiced", reason: "invoiced", created_at: at(2), occurred_at: at(2) },
          { from_status: "invoiced", to_status: "shipped", reason: "shipped", created_at: at(3), occurred_at: at(3) },
          { from_status: "shipped", to_status: "delivered", reason: "delivered", created_at: at(4), occurred_at: at(4) },
        ]}
      />,
    )
    for (const text of ["Order placed (replay)", "Payment received", "Invoice issued", "Handed to the carrier", "Delivered to you"]) {
      expect(screen.getByText(new RegExp(`^${text.replace(/[()]/g, "\\$&")}`))).toBeInTheDocument()
    }
  })

  it("marks an unavailable order like a canceled one", () => {
    const { container } = render(
      <OrderTimeline
        history={[
          { from_status: "", to_status: "created", reason: "replay_placed", created_at: at(0), occurred_at: at(0) },
          { from_status: "created", to_status: "approved", reason: "payment_succeeded", created_at: at(1), occurred_at: at(1) },
          { from_status: "approved", to_status: "unavailable", reason: "unavailable", created_at: at(2), occurred_at: at(2) },
        ]}
      />,
    )
    expect(screen.getByText(/^The seller couldn't fulfil it/)).toBeInTheDocument()
    expect(container.querySelectorAll("svg.text-destructive")).toHaveLength(1)
  })

  it("shows a replayed order's historical time, with the year; app orders keep the recorded time", () => {
    const history: OrderDetail["status_history"] = [
      // recorded today, happened on Black Friday 2017 (12:03 UTC = 10:03 in Sao Paulo, BRST)
      { from_status: "", to_status: "created", reason: "replay_placed", created_at: "2026-11-09T12:03:00Z", occurred_at: "2017-11-24T12:03:00Z" },
    ]
    const { unmount } = render(<OrderTimeline history={history} historical />)
    const time = screen.getByText(/24 Nov 2017/)
    expect(time).toHaveAttribute("dateTime", "2017-11-24T12:03:00Z")
    expect(screen.queryByText(/9 Nov/)).toBeNull()
    unmount()

    render(<OrderTimeline history={history} />)
    expect(screen.getByText(/9 Nov, 09:03/)).toHaveAttribute("dateTime", "2026-11-09T12:03:00Z")
    expect(screen.queryByText(/2017/)).toBeNull()
  })
})
