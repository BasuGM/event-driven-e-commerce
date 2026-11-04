import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { PaymentConfirmation } from "./payment-confirmation"

const processing = { status: "processing" as const, needs_refund: false, confirmation_overdue: false, overdue_at: "2026-11-04T10:03:00Z" }

describe("PaymentConfirmation (driven by the server-side payment status)", () => {
  it("shows 'Confirming your payment…' while the webhook is pending", () => {
    render(<PaymentConfirmation payment={processing} />)
    expect(screen.getByRole("status")).toHaveTextContent("Confirming your payment…")
  })

  it("says it's still waiting once the confirmation window has passed", () => {
    render(<PaymentConfirmation payment={{ ...processing, confirmation_overdue: true }} />)
    expect(screen.getByRole("status")).toHaveTextContent("Still waiting for the payment provider")
  })

  it("shows nothing otherwise", () => {
    const { container } = render(<PaymentConfirmation payment={{ ...processing, status: "succeeded" }} />)
    expect(container).toBeEmptyDOMElement()
    render(<PaymentConfirmation payment={null} />)
  })
})
