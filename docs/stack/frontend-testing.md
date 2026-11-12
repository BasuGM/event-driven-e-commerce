# Frontend testing: Vitest, Testing Library, Playwright

Vitest runs fast unit and component tests in a simulated browser (jsdom); Testing Library renders
components and queries them the way a user would; Playwright drives a real browser against the
whole stack. Vitest 5.0.3, `@testing-library/react` 16.3.3 (+ `jest-dom` 7.0.1, jsdom 30.1.2),
Playwright 1.63.0. Official docs: [vitest.dev](https://vitest.dev/),
[testing-library.com](https://testing-library.com/docs/react-testing-library/intro/),
[playwright.dev](https://playwright.dev/docs/intro).

## Vitest config: jsdom and the `@` alias

Tests run in jsdom (a DOM without a browser). The `@/` import alias is repeated here because
Vitest doesn't read `tsconfig` paths. `make test-frontend` runs it.

```ts
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
})
```

Source: [vitest.config.mts](../../frontend/vitest.config.mts).

## Setup file: matchers and cleanup

`jest-dom` adds DOM matchers (`toBeInTheDocument`). Without Vitest globals Testing Library can't
register its own cleanup, so the setup does it.

```ts
import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

afterEach(cleanup)
```

Source: [vitest.setup.ts](../../frontend/vitest.setup.ts).

## `describe` / `it` / `expect`

Plain tests of pure functions are the cheapest and cover the translation layers: URL params to
filters and back, redirect safety, form schemas.

```ts
it("round-trips every filter through the URL", () => {
  …
  expect(parseShopParams(toSearchParams(filters))).toEqual(filters)
```

Source: [lib/shop-params.test.ts](../../frontend/src/lib/shop-params.test.ts).

## Rendering and querying components

`render` mounts a component; `screen` queries by what a user perceives: label, role, text.
`findBy*` waits for async changes (form validation is async). `getByRole` is preferred, which
also proves the markup is accessible.

```tsx
render(<LoginForm />)

fireEvent.change(screen.getByLabelText("Email"), { target: { value: "not-an-email" } })
fireEvent.click(screen.getByRole("button", { name: "Log in" }))

expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument()
```

Source: [components/auth/login-form.test.tsx](../../frontend/src/components/auth/login-form.test.tsx).

## Mocks and spies: `vi.mock`, `vi.fn`, `vi.spyOn`

`vi.mock` replaces a module for the file (here Next's router hooks, which need a Next runtime).
`vi.spyOn(globalThis, "fetch")` watches calls so a test can assert that validation stopped the
request.

```tsx
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }) }))
…
const fetchSpy = vi.spyOn(globalThis, "fetch")
…
await waitFor(() => expect(fetchSpy).not.toHaveBeenCalled())
```

Source: [components/auth/login-form.test.tsx](../../frontend/src/components/auth/login-form.test.tsx).

## Testing locale-sensitive output

Money is formatted with `Intl.NumberFormat("pt-BR")`; the test pins the real output
(`R$ 1.234,50`). Testing Library's normaliser turns the non-breaking space after `R$` into a
plain one before matching.

```tsx
expect(screen.getByRole("link", { name: base.name })).toHaveAttribute("href", `/shop/${base.slug}`)
expect(screen.getByText("R$ 1.234,50")).toBeInTheDocument()
```

Source: [components/shop/product-card.test.tsx](../../frontend/src/components/shop/product-card.test.tsx).

## Testing hooks with a fake browser API

`renderHook` runs a hook outside a component. jsdom has no `EventSource`, so the test supplies a
fake that it can push snapshots and errors into by hand.

```tsx
/** A controllable EventSource: tests push snapshots and errors by hand. */
class FakeEventSource {
  static instances: FakeEventSource[] = []
  …
  emit(type: string, data: unknown) {
    for (const listener of this.listeners[type] ?? []) listener(new MessageEvent(type, { data: JSON.stringify(data) }))
  }
```

Source: [lib/use-order-live.test.tsx](../../frontend/src/lib/use-order-live.test.tsx),
`FakeEventSource`.

## Testing a route handler directly

A Next route handler is just a function from `Request` to `Response`. The test mocks
`next/cache`, stubs the secret with `vi.stubEnv`, and calls `POST` without any server.

```ts
const revalidateTag = vi.fn()
vi.mock("next/cache", () => ({ revalidateTag: (...args: unknown[]) => revalidateTag(...args) }))

beforeEach(() => {
  vi.stubEnv("REVALIDATE_SECRET", "s3cret")
```

Source: [app/internal/revalidate/route.test.ts](../../frontend/src/app/internal/revalidate/route.test.ts).

## Playwright config

One worker (specs share a customer account and its cart), long timeouts (the Next dev server
compiles each route on first visit), and traces and video kept only for failures.

```ts
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  retries: 0,
  workers: 1,
  …
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
```

Source: [playwright.config.ts](../../frontend/playwright.config.ts).

## Locators by role and label

`getByRole`, `getByLabel` and `getByText` find elements like a user would; Playwright auto-waits
for them to be visible and enabled before acting. Because buttons render disabled until hydrated,
"click when enabled" is exactly the right wait.

```ts
const submit = page.getByRole("button", { name: "Log in" })
await expect(submit).toBeEnabled({ timeout: 60_000 })
await page.getByLabel("Email").fill(email)
await submit.click()
```

Source: [e2e/helpers.ts](../../frontend/e2e/helpers.ts), `logIn`.

## Web-first assertions

`expect(page).toHaveURL(...)` and `expect(locator).toBeVisible()` retry until they pass or time
out. URL checks use a predicate on the parsed URL, never a regex over the whole string, which
could also match a login redirect carrying the target in `?next=`.

```ts
await expect(page).toHaveURL((url) => url.pathname === "/shop", { timeout: 60_000 })
```

Source: [e2e/helpers.ts](../../frontend/e2e/helpers.ts), `logIn`.

## Shared helpers

Flows that several specs need (log in, empty the cart, place an order) live in one helper file
and return what the next step needs, such as the new order's id.

```ts
export async function placeOrder(page: Page): Promise<string> {
  await page.goto("/shop?in_stock=true")
  …
  return new URL(page.url()).pathname.split("/").at(-1)!
}
```

Source: [e2e/helpers.ts](../../frontend/e2e/helpers.ts), `placeOrder`.

## Listening to the page: errors and requests

`page.on("pageerror")` fails the smoke test on any uncaught error (such as a hydration
mismatch) even if the UI looks fine; `page.on("request")` counts the dashboard's background
refreshes so an assertion is known to run after one.

```ts
const pageErrors: string[] = []
page.on("pageerror", (error) => pageErrors.push(error.message))
```

Source: [e2e/shop.spec.ts](../../frontend/e2e/shop.spec.ts), the browse test.

## Polling and retrying assertions

`expect.poll` re-evaluates a plain value until it matches; `expect(async () => …).toPass()`
retries a block of actions. Both absorb the dev server's first-visit compile delay.

```ts
await expect.poll(() => refreshes, { timeout: 30_000 }).toBeGreaterThanOrEqual(1)
```

Source: [e2e/staff-title.spec.ts](../../frontend/e2e/staff-title.spec.ts).

## Requests from the test itself

`page.request` sends HTTP with the page's cookies: the test fetches a staff URL as a non-staff
user and asserts the raw HTML never contains a staff title.

```ts
const response = await page.request.get("/staff/analytics")
const html = await response.text()
expect(html).not.toContain("· Staff ·")
```

Source: [e2e/staff-title.spec.ts](../../frontend/e2e/staff-title.spec.ts).

## Running e2e in an isolated Docker stack

`make e2e` starts a second compose project (own database on tmpfs, Redis, Mailpit), seeds it,
verifies it is not the dev database, then runs Playwright in its official image with traces and
logs written to `e2e-results/`. The container's entry point installs dependencies only when the
lockfile changed.

```sh
exec npx playwright test "$@"
```

Source: [e2e/run.sh](../../frontend/e2e/run.sh); the orchestration is
[scripts/e2e.sh](../../scripts/e2e.sh). More: [docker-and-make.md](docker-and-make.md),
[testing](../testing.md), [lab](../concepts/lab.md).

## Not used here

- Vitest globals and snapshot tests; `@testing-library/user-event` (tests use `fireEvent`).
- Mock Service Worker: API calls are spied on or kept out of the unit under test.
- Playwright fixtures (`test.extend`), `page.route` network mocking, visual-comparison
  screenshots, multiple browsers (Chromium only) and retries.
- Component-level browser tests (Storybook, Playwright component testing).
