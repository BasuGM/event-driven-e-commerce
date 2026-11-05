import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { RetryDeadLetter } from "./retry-dead-letter"

const post = vi.fn()
const refresh = vi.fn()
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }))
vi.mock("@/lib/api/browser", () => ({
  browserApi: { POST: (...args: unknown[]) => post(...args) },
  ensureCsrf: async () => {},
  toProblem: () => ({ message: "Not found." }),
  NETWORK_PROBLEM: { message: "network" },
}))

describe("RetryDeadLetter", () => {
  beforeEach(() => {
    post.mockReset()
    refresh.mockReset()
  })

  it("re-delivers the entry, then refreshes the health page", async () => {
    post.mockResolvedValue({ response: new Response(null, { status: 200 }) })
    render(<RetryDeadLetter entryId="1730000000000-0" retriedAt={null} />)

    fireEvent.click(screen.getByRole("button", { name: "Retry dead letter 1730000000000-0" }))

    await waitFor(() => expect(refresh).toHaveBeenCalled())
    expect(post).toHaveBeenCalledWith("/api/staff/dead-letters/{entry_id}/retry/", {
      params: { path: { entry_id: "1730000000000-0" } },
    })
  })

  it("shows the error when the retry fails", async () => {
    post.mockResolvedValue({ response: new Response(null, { status: 404 }), error: {} })
    render(<RetryDeadLetter entryId="1-0" retriedAt={null} />)
    fireEvent.click(screen.getByRole("button", { name: /Retry/ }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.")
  })

  it("has no button once retried", () => {
    render(<RetryDeadLetter entryId="1-0" retriedAt="2026-11-04T10:00:00Z" />)
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    expect(screen.getByText("Retried")).toBeInTheDocument()
  })
})
