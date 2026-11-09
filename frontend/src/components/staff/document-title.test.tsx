import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { DocumentTitle } from "./document-title"

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

describe("DocumentTitle", () => {
  it("restores the staff title when the page metadata overwrites it (router.refresh)", async () => {
    document.head.innerHTML = "<title>Olist Commerce</title>"
    const { unmount } = render(<DocumentTitle title="Analytics" />)
    expect(document.title).toBe("Analytics · Staff · Olist Commerce")

    // What Next does on a refresh: its metadata <title> is written again
    document.head.querySelector("title")!.textContent = "Olist Commerce"
    await tick()
    expect(document.title).toBe("Analytics · Staff · Olist Commerce")

    // ... or replaced by a new element
    document.head.innerHTML = "<title>Olist Commerce</title>"
    await tick()
    expect(document.title).toBe("Analytics · Staff · Olist Commerce")

    // Once unmounted (navigated away) the next page's title stands
    unmount()
    document.title = "Shop · Olist Commerce"
    await tick()
    expect(document.title).toBe("Shop · Olist Commerce")
  })
})
