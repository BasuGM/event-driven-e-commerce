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
  render(<OrderActions orderId="abc" canPay={false} canCancel paymentsEnabled={false} />)
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
