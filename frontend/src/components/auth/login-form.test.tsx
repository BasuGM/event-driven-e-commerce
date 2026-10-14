import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { maskCep, shippingSchema } from "@/components/checkout/checkout-form"
import { safeNext } from "@/lib/urls"

import { LoginForm } from "./login-form"

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }) }))

describe("LoginForm", () => {
  it("validates before calling the API", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch")
    render(<LoginForm />)

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "not-an-email" } })
    fireEvent.click(screen.getByRole("button", { name: "Log in" }))

    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument()
    expect(screen.getByText("Enter your password.")).toBeInTheDocument()
    await waitFor(() => expect(fetchSpy).not.toHaveBeenCalled())
    fetchSpy.mockRestore()
  })
})

describe("checkout helpers", () => {
  it("masks a CEP as you type", () => {
    expect(maskCep("01310")).toBe("01310")
    expect(maskCep("01310100")).toBe("01310-100")
    expect(maskCep("01310-1009999")).toBe("01310-100")
  })

  it("validates the shipping address like the API", () => {
    const ok = { full_name: "Ana", street: "Rua A, 1", city: "Recife", state: "PE", zip_code: "50000-000" }
    expect(shippingSchema.safeParse(ok).success).toBe(true)
    expect(shippingSchema.safeParse({ ...ok, state: "XX" }).success).toBe(false)
    expect(shippingSchema.safeParse({ ...ok, zip_code: "50000000" }).success).toBe(false)
  })
})

describe("safeNext", () => {
  it("only allows same-site relative paths", () => {
    expect(safeNext("/orders/abc")).toBe("/orders/abc")
    expect(safeNext("//evil.example.com")).toBe("/")
    expect(safeNext("https://evil.example.com")).toBe("/")
    expect(safeNext("/\\evil.example.com")).toBe("/")
    expect(safeNext(undefined, "/shop")).toBe("/shop")
  })
})
