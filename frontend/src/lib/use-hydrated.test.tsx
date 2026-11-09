import { render, screen } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { LoginForm } from "@/components/auth/login-form"

import { useHydrated } from "./use-hydrated"

function Probe() {
  return <span>{useHydrated() ? "hydrated" : "server"}</span>
}

describe("useHydrated", () => {
  it("is false in the server render and true on the client", () => {
    expect(renderToString(<Probe />)).toContain("server")
    render(<Probe />)
    expect(screen.getByText("hydrated")).toBeInTheDocument()
  })
})

describe("LoginForm before hydration", () => {
  it("renders a disabled submit and a POST form, so an early submit can't leak credentials into the URL", () => {
    const html = renderToString(<LoginForm next="/shop" />)
    expect(html).toMatch(/<form[^>]*method="post"/)
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/)
  })

  it("enables the submit once hydrated", () => {
    render(<LoginForm next="/shop" />)
    expect(screen.getByRole("button", { name: "Log in" })).toBeEnabled()
  })
})
