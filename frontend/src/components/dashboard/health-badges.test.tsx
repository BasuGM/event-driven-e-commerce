import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { formatAge, HealthBadges, outboxLabel } from "./health-badges"

describe("outbox backlog", () => {
  it("formats the backlog and its oldest age", () => {
    expect(outboxLabel({ unpublished: 0, oldest_unpublished_age_seconds: null })).toBe("Outbox: 0 pending")
    expect(outboxLabel({ unpublished: 3, oldest_unpublished_age_seconds: 125 })).toBe("Outbox: 3 pending · oldest 2m")
    expect([formatAge(45), formatAge(7200)]).toEqual(["45s", "2h"])
  })

  it("shows the outbox badge next to the services, and hides it when the DB is down", () => {
    const { rerender } = render(
      <HealthBadges health={{ db: "ok", redis: "ok", outbox: { unpublished: 2, oldest_unpublished_age_seconds: 30 } }} />,
    )
    expect(screen.getByText("Outbox: 2 pending · oldest 30s")).toBeInTheDocument()

    rerender(<HealthBadges health={{ db: "error", redis: "ok", outbox: null }} />)
    expect(screen.queryByText(/Outbox/)).not.toBeInTheDocument()
    expect(screen.getByText("Database: down")).toBeInTheDocument()
  })
})
