import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MobileNav } from "./mobile-nav"

vi.mock("next/navigation", () => ({ usePathname: () => "/shop" }))

describe("MobileNav", () => {
  it("closes the sheet when a nav link is clicked, even the current page's", () => {
    render(<MobileNav />)

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }))
    const link = screen.getByRole("link", { name: "Shop" })
    link.addEventListener("click", (event) => event.preventDefault()) // jsdom can't navigate
    fireEvent.click(link)

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
