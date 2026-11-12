import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test"

import { logIn } from "../e2e/helpers"

/**
 * Generates the README screenshots (docs/images/*.png) on the lab stack. Every wait is for real
 * content (an element, a status, a count), never a fixed sleep. Run by `make screenshots`
 * (scripts/screenshots.sh): the stack is up, and a short replay has already run.
 */
const OUT = process.env.SHOTS_DIR ?? "/shots"
const MAILPIT = process.env.MAILPIT_URL ?? "http://mailpit:8025"
const PASSWORD = process.env.E2E_USER_PASSWORD ?? "devpass123"
const ASYNC = 60_000

const DESKTOP = { width: 1280, height: 800 }
const MOBILE = { width: 390, height: 844 }

async function newContext(browser: Browser, theme: "light" | "dark", viewport = DESKTOP): Promise<BrowserContext> {
  const context = await browser.newContext({ viewport, colorScheme: theme, locale: "en-US", deviceScaleFactor: 1 })
  // next-themes reads this key before first paint
  await context.addInitScript((value) => window.localStorage.setItem("theme", value), theme)
  return context
}

/**
 * Fonts and images loaded, Next's dev badge hidden, then save the PNG. `height` crops the top of
 * the viewport: for pages whose content ends well above the fold (cart, orders, dashboard), so the
 * README gallery doesn't show half a screen of white.
 */
async function shot(page: Page, name: string, height?: number) {
  await page.addStyleTag({ content: "nextjs-portal, [data-nextjs-toast] { display: none !important }" })
  await page.evaluate(() => document.fonts.ready)
  await expect.poll(() => page.evaluate(() => [...document.images].every((image) => image.complete))).toBe(true)
  const width = page.viewportSize()!.width
  await page.screenshot({ path: `${OUT}/${name}.png`, ...(height ? { clip: { x: 0, y: 0, width, height } } : {}) })
  console.log(`  shot ${name}.png`)
}

/** The desktop filter sidebar's selects render their label only once hydrated. */
async function filtersHydrated(page: Page) {
  await expect(page.getByRole("complementary", { name: "Filters" }).getByText("Any rating")).toBeVisible()
}

type ProductSummary = { slug: string; name: string; in_stock: boolean }

/**
 * The showcase product, chosen by rule, not by position: in stock at 2-3 sellers (so the offers
 * table has rows to compare), and the generated description with the fewest repeated sentence
 * openers ("Customers like that ..." three times reads badly). Ties break by slug, so the choice
 * is stable for a given seed. Category, name and icon agree by construction (enrichment.py).
 */
async function pickShowcaseProduct(page: Page): Promise<string> {
  const candidates: { slug: string; repeats: number }[] = []
  for (let pageNumber = 1; pageNumber <= 20; pageNumber++) {
    const response = await page.request.get("/api/products/", {
      params: { in_stock: "true", ordering: "popular", page_size: "100", page: String(pageNumber) },
    })
    if (!response.ok()) break
    const list = await response.json()
    const details = await Promise.all(
      (list.results as ProductSummary[]).map(async (product) => (await page.request.get(`/api/products/${product.slug}/`)).json()),
    )
    for (const detail of details) {
      const sellers = detail.offers.filter((offer: { in_stock: boolean }) => offer.in_stock).length
      if (sellers < 2 || sellers > 3) continue
      const openers = (detail.description as string)
        .split(/(?<=\.)\s+/)
        .filter(Boolean)
        .map((sentence) => sentence.split(/\s+/).slice(0, 3).join(" "))
      candidates.push({ slug: detail.slug, repeats: openers.length - new Set(openers).size })
    }
    if (!list.next) break
  }
  candidates.sort((a, b) => a.repeats - b.repeats || a.slug.localeCompare(b.slug))
  expect(candidates.length, "a product with 2-3 sellers in stock").toBeGreaterThan(0)
  console.log(`  showcase product: ${candidates[0].slug} (${candidates[0].repeats} repeated sentence openers)`)
  return candidates[0].slug
}

/**
 * The shop shot's category + search term: the first candidate whose first two rows of results
 * (8 cards) are all in stock, so no "Out of stock" badge in the gallery.
 */
async function pickShopSearch(page: Page): Promise<{ category: string; term: string }> {
  const candidates = [
    { category: "bed-bath-table", term: "runner" },
    { category: "furniture-decor", term: "frame" },
    { category: "furniture-decor", term: "shelf" },
    { category: "health-beauty", term: "lotion" },
  ]
  for (const candidate of candidates) {
    const response = await page.request.get("/api/products/", { params: { category: candidate.category, q: candidate.term, page_size: "8" } })
    const results = (await response.json()).results as ProductSummary[]
    if (results.length === 8 && results.every((product) => product.in_stock)) {
      console.log(`  shop search: ${candidate.category} / "${candidate.term}"`)
      return candidate
    }
  }
  throw new Error("no category + search term with 8 in-stock results; update the candidates in pickShopSearch")
}

/** Open a product's page and wait for its offers table. */
async function openProduct(page: Page, slug: string) {
  await page.goto(`/shop/${slug}`)
  await expect(page.getByRole("table").getByText(/R\$/).first()).toBeVisible()
}

/** Open the shop's first in-stock product (any), for the orders that only fill the list. */
async function openFirstProduct(page: Page) {
  await page.goto("/shop?in_stock=true")
  await page.locator('main a[href^="/shop/"]').first().click()
  await expect(page).toHaveURL((url) => /^\/shop\/[a-z0-9-]+$/.test(url.pathname))
  await expect(page.getByRole("table").getByText(/R\$/).first()).toBeVisible()
}

async function emptyCartAndAdd(page: Page, slug?: string) {
  await page.goto("/cart")
  const remove = page.getByRole("button", { name: /^Remove / })
  while ((await remove.count()) > 0) {
    const before = await remove.count()
    await remove.first().click()
    await expect(remove).toHaveCount(before - 1)
  }
  if (slug) await openProduct(page, slug)
  else await openFirstProduct(page)
  await page.getByRole("button", { name: /^Add to cart/ }).first().click()
  await expect(page.getByRole("status").filter({ hasText: "Added to cart" })).toBeVisible()
  await expect(page.getByRole("link", { name: /Cart, 1 item/ })).toBeVisible()
}

async function fillCheckout(page: Page) {
  await expect(page.getByRole("button", { name: "Place order" })).toBeEnabled()
  await page.getByLabel("Street and number").fill("Av. Paulista, 1000")
  await page.getByLabel("City").fill("São Paulo")
  await page.getByRole("combobox", { name: "State" }).click()
  await page.getByRole("option", { name: "SP", exact: true }).click()
  await page.getByLabel("CEP").fill("01310100")
  await expect(page.getByLabel("CEP")).toHaveValue("01310-100")
}

async function placeOrder(page: Page): Promise<string> {
  await page.getByRole("button", { name: "Place order" }).click()
  await expect(page).toHaveURL((url) => /^\/orders\/[0-9a-f]{32}$/.test(url.pathname), { timeout: ASYNC })
  await expect(page.getByTestId("order-status")).toHaveText("Awaiting payment")
  return new URL(page.url()).pathname.split("/").at(-1)!
}

/** Cart -> checkout form filled (no submit) for an already-filled cart. */
async function toCheckout(page: Page) {
  await page.goto("/cart")
  await page.getByRole("link", { name: "Checkout" }).click()
  await expect(page).toHaveURL((url) => url.pathname === "/checkout")
  await fillCheckout(page)
}

/** On the order page: Pay -> provider's page -> pick an option -> submit. */
async function payOnProvider(page: Page, choice: "succeed" | "delayed") {
  await page.getByRole("button", { name: /^Pay R\$/ }).click()
  await expect(page).toHaveURL((url) => url.pathname.startsWith("/api/fake-provider/pay/pi_"))
  if (choice === "delayed") {
    await page.getByRole("radio", { name: /deliver the webhook after a delay/ }).check()
    await page.getByRole("combobox", { name: "Delay" }).selectOption("30")
  } else {
    await page.getByRole("radio", { name: "Succeed", exact: true }).check()
  }
}

test("README screenshots", async ({ browser }) => {
  const pageErrors: string[] = []

  // ---- Anonymous, light, desktop ----
  const visitor = await newContext(browser, "light")
  const anon = await visitor.newPage()
  anon.on("pageerror", (error) => pageErrors.push(error.message))

  await anon.goto("/")
  await expect(anon.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible()
  await expect(anon.getByText("Orders", { exact: true }).first()).toBeVisible()
  await shot(anon, "home", 340)

  // Shop with a category filter and a search term, chosen so the first rows are all in stock
  const { category, term } = await pickShopSearch(anon)
  await anon.goto("/shop")
  await anon.getByRole("complementary", { name: "Filters" }).locator(`a[href*="category=${category}"]`).first().click()
  await expect(anon).toHaveURL((url) => url.searchParams.get("category") === category)
  const cards = anon.locator('main a[href^="/shop/"]')
  await expect(cards.first()).toBeVisible()
  const search = anon.getByRole("searchbox", { name: "Search products" })
  await expect(async () => {
    await search.fill(term)
    await search.press("Enter")
    await expect(anon).toHaveURL((url) => url.searchParams.get("q") === term, { timeout: 5_000 })
  }).toPass({ timeout: 60_000 })
  await expect(anon.getByText(new RegExp(`products? for “${term}”`, "i"))).toBeVisible()
  await expect(cards.first()).toBeVisible()
  await filtersHydrated(anon)
  await shot(anon, "shop")
  const shopQuery = new URL(anon.url()).search

  // Product page with its offers
  await anon.setViewportSize({ width: 1280, height: 1000 }) // tall enough to show the offers table
  const showcase = await pickShowcaseProduct(anon)
  await openProduct(anon, showcase)
  await expect(anon.getByRole("table").getByRole("columnheader", { name: "Seller" })).toBeVisible()
  // The add-to-cart buttons are disabled until the page has hydrated
  await expect(anon.getByRole("button", { name: /^Add to cart/ }).first()).toBeEnabled()
  await shot(anon, "product")
  await visitor.close()

  // ---- Customer: cart, checkout, pay with a delayed webhook ----
  const customerCtx = await newContext(browser, "light")
  const customer = await customerCtx.newPage()
  customer.on("pageerror", (error) => pageErrors.push(error.message))
  await logIn(customer, "customer@example.com", PASSWORD)
  await emptyCartAndAdd(customer, showcase)

  await customer.goto("/cart")
  await expect(customer.getByRole("link", { name: "Checkout" })).toBeVisible()
  await expect(customer.getByText("R$").first()).toBeVisible()
  // The quantity select is disabled until the page has hydrated
  await expect(customer.getByRole("combobox", { name: /^Quantity of/ })).toBeEnabled()
  await shot(customer, "cart", 440)

  await toCheckout(customer)
  await shot(customer, "checkout")
  const orderId = await placeOrder(customer)

  await payOnProvider(customer, "delayed")
  await shot(customer, "payment-page")
  await customer.getByRole("button", { name: /^Pay R\$/ }).click()

  await expect(customer).toHaveURL((url) => url.pathname === `/orders/${orderId}`, { timeout: ASYNC })
  await expect(customer.getByRole("button", { name: "Payment in progress" })).toBeDisabled()
  await expect(customer.getByText("Confirming your payment…")).toBeVisible()
  await shot(customer, "order-processing")

  // The webhook arrives 30 s later; the page updates itself over SSE
  const status = customer.getByTestId("order-status")
  await expect(status).toHaveText("Approved", { timeout: ASYNC * 2 })
  await expect(customer.getByText("Payment received")).toBeVisible()
  await shot(customer, "order-approved")

  // Two more orders so the list isn't a single row: one paid at once, one left awaiting payment
  await emptyCartAndAdd(customer)
  await toCheckout(customer)
  await placeOrder(customer)
  await payOnProvider(customer, "succeed")
  await customer.getByRole("button", { name: /^Pay R\$/ }).click()
  await expect(customer.getByTestId("order-status")).toHaveText("Approved", { timeout: ASYNC })
  await emptyCartAndAdd(customer)
  await toCheckout(customer)
  await placeOrder(customer)

  await customer.goto("/orders")
  // Newest first: this run's three orders lead (a re-run on the same lab stack adds older rows
  // below them; the shot is cropped to the table either way)
  const rows = customer.getByRole("row")
  await expect(rows.nth(1)).toContainText("Awaiting payment")
  await expect(rows.nth(2)).toContainText("Approved")
  await expect(rows.nth(3)).toContainText("Approved")
  const table = await customer.getByRole("table").boundingBox()
  await shot(customer, "orders-list", Math.min(800, Math.round(table!.y + table!.height) + 40))
  await customerCtx.close()

  // ---- The confirmation email in Mailpit ----
  const mailCtx = await newContext(browser, "light")
  const mail = await mailCtx.newPage()
  const subject = `Payment confirmed for order #${orderId.slice(0, 8)}`
  let messageId = ""
  await expect
    .poll(
      async () => {
        const response = await mail.request.get(`${MAILPIT}/api/v1/search`, { params: { query: `subject:"${subject}"` } })
        const body = await response.json()
        messageId = body.messages?.[0]?.ID ?? ""
        return body.messages_count
      },
      { timeout: ASYNC },
    )
    .toBe(1)
  await mail.goto(`${MAILPIT}/view/${messageId}`)
  await expect(mail.frameLocator("iframe").first().getByText(/R\$/).first()).toBeVisible()
  await shot(mail, "email")
  await mailCtx.close()

  // ---- Staff, light ----
  const staffCtx = await newContext(browser, "light")
  const staff = await staffCtx.newPage()
  staff.on("pageerror", (error) => pageErrors.push(error.message))
  await logIn(staff, "staff@example.com", PASSWORD)

  // The replay ran before this script: pick a fully delivered copy for the timeline
  const delivered = await staff.request.get("/api/staff/events/", { params: { type: "OrderDelivered" } })
  expect(delivered.ok()).toBe(true)
  const replayOrder: string = (await delivered.json()).results[0].aggregate_id

  // Wait until the consumers have caught up, so every badge on the timeline is "processed"
  await expect
    .poll(
      async () => {
        const health = await (await staff.request.get("/api/staff/health/")).json()
        const behind = health.groups.filter((g: { pending: number; lag: number | null }) => g.pending > 0 || (g.lag ?? 0) > 0)
        return `${behind.length} groups behind, ${health.outbox.unpublished} unpublished`
      },
      { timeout: 5 * 60_000, intervals: [2_000] },
    )
    .toBe("0 groups behind, 0 unpublished")

  await staff.goto("/staff/events")
  await expect(staff.getByRole("heading", { level: 1, name: "Events" })).toBeVisible()
  await expect(staff.getByRole("row").nth(1)).toBeVisible()
  // The Type select shows its "All types" label only once hydrated
  await expect(staff.getByRole("combobox", { name: "Type" })).toHaveText("All types")
  await shot(staff, "staff-events")

  await staff.goto(`/staff/orders/${replayOrder}`)
  const events = staff.getByRole("list", { name: "Order events" }).getByRole("listitem")
  await expect(events.first()).toBeVisible()
  expect(await events.count()).toBeGreaterThanOrEqual(5) // placed, paid, invoiced, shipped, delivered
  await shot(staff, "staff-order-timeline")

  await staff.goto("/staff/health")
  await expect(staff.getByRole("heading", { level: 1, name: /health/i })).toBeVisible()
  await expect(staff.getByRole("row").nth(1)).toBeVisible()
  await shot(staff, "staff-health")

  await staff.setViewportSize({ width: 1280, height: 1400 }) // KPIs and the first charts in one frame
  await staff.goto("/staff/analytics")
  await expect(staff.getByRole("heading", { level: 1, name: "Analytics" })).toBeVisible()
  await expect(staff.locator(".recharts-surface").first()).toBeVisible()
  await expect(staff.locator(".recharts-line-curve, .recharts-bar-rectangle").first()).toBeVisible()
  await shot(staff, "staff-analytics")
  await staffCtx.close()

  // ---- Dark theme ----
  const darkCtx = await newContext(browser, "dark")
  const dark = await darkCtx.newPage()
  dark.on("pageerror", (error) => pageErrors.push(error.message))
  await dark.goto(`/shop${shopQuery}`)
  await expect(dark.locator("html")).toHaveClass(/dark/)
  await expect(dark.locator('main a[href^="/shop/"]').first()).toBeVisible()
  await filtersHydrated(dark)
  await shot(dark, "shop-dark")

  await logIn(dark, "staff@example.com", PASSWORD)
  await dark.setViewportSize({ width: 1280, height: 1400 })
  await dark.goto("/staff/analytics")
  await expect(dark.locator("html")).toHaveClass(/dark/)
  await expect(dark.locator(".recharts-line-curve, .recharts-bar-rectangle").first()).toBeVisible()
  await shot(dark, "staff-analytics-dark")
  await darkCtx.close()

  // ---- Mobile ----
  const mobileCtx = await newContext(browser, "light", MOBILE)
  const mobile = await mobileCtx.newPage()
  mobile.on("pageerror", (error) => pageErrors.push(error.message))
  await mobile.goto(`/shop${shopQuery}`)
  await expect(mobile.locator('main a[href^="/shop/"]').first()).toBeVisible()
  await shot(mobile, "shop-mobile")
  await mobileCtx.close()

  expect(pageErrors).toEqual([])
})
