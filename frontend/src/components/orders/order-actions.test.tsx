import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { OrderActions } from "./order-actions"

const post = vi.fn()
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }))
vi.mock("@/lib/api/browser", () => ({
  browserApi: { POST: (...args: unknown[]) => post(...args) },
  ensureCsrf: async () => {},
  toProblem: () => ({ code: "x", message: "x" }),
  NETWORK_PROBLEM: { message: "network" },
}))

function renderActions() {
  render(<OrderActions orderId="abc" total="88.00" canPay={false} canCancel paymentsEnabled={false} />)
  fireEvent.click(screen.getByRole("button", { name: "Cancel order" }))
  return screen.getByRole("alertdialog", { name: "Cancel this order?" })
}

describe("OrderActions cancel", () => {
  beforeEach(() => post.mockReset().mockResolvedValue({ response: new Response(null, { status: 200 }) }))

  it("asks first and does nothing when you keep the order", () => {
    const dialog = renderActions()
    expect(dialog).toHaveTextContent("Stock will be released.")
    expect(post).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole("button", { name: "Keep order" }))
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    expect(post).not.toHaveBeenCalled()
  })

  it("cancels only on confirm", async () => {
    const dialog = renderActions()
    fireEvent.click(dialog.querySelector("[data-slot=alert-dialog-action]")!)

    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/orders/{order_id}/cancel/", expect.anything()))
  })
})

describe("OrderActions pay", () => {
  beforeEach(() => post.mockReset())

  it("starts the payment and goes to the provider's page", async () => {
    const assign = vi.fn()
    vi.stubGlobal("location", { ...window.location, assign })
    post.mockResolvedValue({
      data: { redirect_url: "/api/fake-provider/pay/pi_123/", status: "requires_payment" },
      response: new Response(null, { status: 200 }),
    })
    render(<OrderActions orderId="abc" total="88.00" canPay canCancel paymentsEnabled />)

    // Intl puts a non-breaking space after "R$"
    fireEvent.click(screen.getByRole("button", { name: /^Pay R\$\s88,00$/ }))

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/api/fake-provider/pay/pi_123/"))
    expect(post).toHaveBeenCalledWith("/api/orders/{order_id}/payment/", { params: { path: { order_id: "abc" } } })
    vi.unstubAllGlobals()
  })

  it("shows a disabled 'Payment in progress' instead of Pay while the provider confirms", () => {
    render(<OrderActions orderId="abc" total="88.00" canPay canCancel paymentsEnabled paymentInProgress />)

    expect(screen.queryByRole("button", { name: /^Pay R\$/ })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Payment in progress" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Cancel order" })).toBeEnabled() // cancel stays
    expect(post).not.toHaveBeenCalled()
  })

  it("shows 'Payment in progress' even though Pay isn't allowed during the confirmation window", () => {
    // the server says can_pay=false while processing; the button must still explain why
    render(<OrderActions orderId="abc" total="88.00" canPay={false} canCancel paymentsEnabled paymentInProgress />)
    expect(screen.getByRole("button", { name: "Payment in progress" })).toBeDisabled()
  })

  it("hides Pay when payments are disabled", () => {
    render(<OrderActions orderId="abc" total="88.00" canPay canCancel paymentsEnabled={false} />)
    expect(screen.queryByRole("button", { name: /^Pay/ })).not.toBeInTheDocument()
  })
})
