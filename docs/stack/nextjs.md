# Next.js

The React framework serving the storefront and staff pages (App Router, Turbopack). It also
proxies `/api/*` to Django and exposes one internal route for cache invalidation. Next.js 16.4.2
on Node 22. Official docs: [nextjs.org/docs](https://nextjs.org/docs).

## File-based routing and layouts

A folder under `src/app/` is a route; `page.tsx` is its page and `layout.tsx` wraps everything
below it. The root layout holds the header, the theme provider and the width-limited `<main>`.

```tsx
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" … suppressHydrationWarning>
      <body className="flex min-h-full flex-col">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <SiteHeader />
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">{children}</main>
```

Source: [app/layout.tsx](../../frontend/src/app/layout.tsx), `RootLayout`. `LayoutProps` and
`PageProps` are route-typed helpers Next generates.

## Server Components fetching data

Pages are `async` Server Components: they `await` data on the server and render HTML, with no
client-side fetching code. Several independent calls run in parallel with `Promise.all`.

```tsx
export default async function ShopPage({ searchParams }: PageProps<"/shop">) {
  const filters = parseShopParams(await searchParams)
  const [result, categories] = await Promise.all([getProducts(filters), getCategories()])
```

Source: [app/shop/page.tsx](../../frontend/src/app/shop/page.tsx), `ShopPage`. Reading
`searchParams` makes the route dynamic (rendered per request).

## Client Components: `"use client"`

A file that starts with the directive (and everything it imports) ships to the browser, which is
required for state, effects and event handlers. Error boundaries must be Client Components.

```tsx
"use client"

export { default } from "@/components/layout/backend-error"
```

Source: [app/shop/error.tsx](../../frontend/src/app/shop/error.tsx).

## Special files: `loading.tsx` and `error.tsx`

`loading.tsx` is the Suspense fallback while a route's data loads; `error.tsx` catches errors
below it. Every data view has both, which is how "loading" and "error" states are guaranteed.

```tsx
export default function Loading() {
  return <DashboardSkeleton />
}
```

Source: [app/loading.tsx](../../frontend/src/app/loading.tsx).

## `<Suspense>` for streaming and runtime data

Wrapping a slow or request-dependent part in `<Suspense>` lets the rest of the page render and
the part stream in later. Anything reading `searchParams` or `usePathname()` has to sit under one.

```tsx
<Suspense fallback={null}>
  <PendingCartIntent productPath={`/shop/${product.slug}`} searchParams={searchParams} />
</Suspense>
```

Source: [app/shop/[slug]/page.tsx](../../frontend/src/app/shop/[slug]/page.tsx), `ProductPage`.

## Dynamic routes and `generateMetadata`

`[slug]` is a route parameter (a promise, in current Next). `generateMetadata` sets the page's
`<title>` from the same data the page uses; a static `metadata` export covers fixed titles.

```tsx
export async function generateMetadata({ params }: PageProps<"/shop/[slug]">): Promise<Metadata> {
  const product = await getProduct((await params).slug)
  return { title: product?.name ?? "Product not found" }
}
```

Source: [app/shop/[slug]/page.tsx](../../frontend/src/app/shop/[slug]/page.tsx),
`generateMetadata`. The root layout's `title.template` (`"%s · Olist Commerce"`) completes it.

## `notFound()` and `redirect()`

Both throw, ending the render. `notFound()` shows the nearest not-found UI; `redirect()` sends the
visitor elsewhere (an empty or out-of-stock cart can't check out).

```tsx
if (!product) notFound()
```

```tsx
if (!cart.can_checkout) redirect("/cart") // empty, or something is out of stock
```

Source: [app/shop/[slug]/page.tsx](../../frontend/src/app/shop/[slug]/page.tsx);
[app/checkout/page.tsx](../../frontend/src/app/checkout/page.tsx), `CheckoutPage`. On a streamed
route the not-found page still has HTTP status 200; see [ADR 0013](../adr/0013-staff-pages-404.md).

## Protected pages: 401 becomes a redirect

Server fetchers throw `NotAuthenticatedError` on a 401; `orLogin` turns it into a redirect to
the login page that comes back afterwards.

```ts
export async function orLogin<T>(load: () => Promise<T>, path: string): Promise<T> {
  try {
    return await load()
  } catch (error) {
    if (error instanceof NotAuthenticatedError) redirect(loginHref(path))
    throw error
  }
}
```

Source: [lib/api/server.ts](../../frontend/src/lib/api/server.ts), `orLogin`.

## Reading cookies on the server

`cookies()` gives the incoming request's cookies; forwarding them to Django is how a Server
Component acts as the visitor. Reading cookies makes the caller dynamic, so it stays under
`<Suspense>`.

```ts
const cookieHeader = (await cookies()).toString()
```

Source: [lib/api/server.ts](../../frontend/src/lib/api/server.ts), `asVisitor`.

## `next/link` and navigation hooks

`<Link>` navigates without a full reload and prefetches. `usePathname()` reads the current URL,
used to highlight the active nav item; because it is runtime data, it sits in a Suspense boundary
so the header can still prerender.

```tsx
<Suspense fallback={<ItemLink item={item} active={false} className={className} />}>
  <ActiveAwareLink item={item} className={className} />
</Suspense>
```

Source: [components/layout/nav-link.tsx](../../frontend/src/components/layout/nav-link.tsx),
`NavLink`.

## `next/font`

Fonts are loaded at build time and exposed as CSS variables (used by Tailwind's font tokens).

```tsx
const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] })
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] })
```

Source: [app/layout.tsx](../../frontend/src/app/layout.tsx).

## `rewrites()`: a same-origin proxy to Django

The browser calls `/api/*` on the Next server, which forwards to Django, so session and CSRF
cookies are first-party. The SSE path is listed first and goes to the ASGI service instead.

```ts
return [
  { source: "/api/orders/:id/stream", destination: `${stream}/api/orders/:id/stream/` },
  { source: "/api/:path*", destination: `${backend}/api/:path*/` },
]
```

Source: [next.config.ts](../../frontend/next.config.ts), `rewrites`. More:
[ADR 0004](../adr/0004-sessions-behind-the-next-proxy.md).

## Config: trailing slashes and Turbopack

Django URLs end in `/`. Without `skipTrailingSlashRedirect`, Next would redirect `/api/cart/` to
`/api/cart`, and Django can't redirect a POST. CSS goes through Tailwind's Turbopack loader.

```ts
skipTrailingSlashRedirect: true,
cacheComponents: true,
…
turbopack: {
  rules: {
    "*.css": {
      loaders: ["@tailwindcss/turbopack"],
      as: "*.css",
    },
  },
},
```

Source: [next.config.ts](../../frontend/next.config.ts).

## Caching: `"use cache"`, `cacheLife`, `cacheTag`

With `cacheComponents` on, a function marked `"use cache"` has its result cached. `cacheLife` sets
how long it stays fresh; `cacheTag` names it so it can be expired on demand. Only the product
detail is cached; listings stay dynamic because filter combinations are unbounded and stock must
be fresh.

```ts
export async function getProduct(slug: string): Promise<ProductDetail | null> {
  "use cache"
  cacheLife({ stale: 60, revalidate: 300, expire: 3600 })
  cacheTag(productTag(slug), ALL_PRODUCTS)
```

Source: [lib/api/catalog.ts](../../frontend/src/lib/api/catalog.ts), `getProduct`; tag names in
[lib/cache-tags.ts](../../frontend/src/lib/cache-tags.ts), `productTag`. More:
[ADR 0017](../adr/0017-cache-invalidation-by-consumer.md),
[catalog-and-search](../flows/catalog-and-search.md).

## Route handlers and on-demand revalidation

A `route.ts` exporting `POST` is an HTTP endpoint. This one is called by the backend's
cache-invalidation consumer: it checks a shared secret in constant time, validates the body (see
[drf-and-openapi.md](drf-and-openapi.md#zod-at-a-server-boundary)) and expires each tag so the
next visit re-fetches.

```ts
export async function POST(request: Request) {
  if (!authorized(request.headers.get("x-revalidate-secret"))) {
    return Response.json({ detail: "Unauthorized" }, { status: 401 })
  }
  …
  for (const tag of tags) revalidateTag(tag, { expire: 0 })
```

Source: [app/internal/revalidate/route.ts](../../frontend/src/app/internal/revalidate/route.ts),
`POST`. It lives outside `/api` on purpose, because `/api/*` is rewritten to Django.

## Neutral metadata for pages that must not reveal themselves

A not-found staff page still returns HTTP 200 on a streamed route, so the prerendered `<head>`
must not give the page away: a layout sets a neutral title and `noindex` for every `/staff/*`
page; the real title is set client-side after the staff check.

```tsx
export const metadata: Metadata = {
  title: { absolute: "Olist Commerce" },
  robots: { index: false, follow: false },
}
```

Source: [app/staff/layout.tsx](../../frontend/src/app/staff/layout.tsx).

## URL search params as state, and `router.refresh()`

Filters live in the URL: Server Components parse `searchParams`; client controls call
`router.push` inside a transition. After a server-side change (live order updates, the dashboard's
10-second poll), `router.refresh()` re-renders the Server Components in place.

```tsx
const navigate = (href: string) =>
  startTransition(() => router.push(href, { scroll: false }))
```

```tsx
if (document.visibilityState === "visible") router.refresh()
```

Source: [components/shop/shop-navigation.tsx](../../frontend/src/components/shop/shop-navigation.tsx),
`ShopNavigationProvider`; [components/analytics/auto-refresh.tsx](../../frontend/src/components/analytics/auto-refresh.tsx),
`AutoRefresh`; parsing in [lib/shop-params.ts](../../frontend/src/lib/shop-params.ts),
`parseShopParams`.

## Full page load after an auth change

After login, register, logout and checkout the code uses `window.location.assign`, not
`router.push` plus `router.refresh()`. The header (user menu, cart badge) is a Server Component
in the root layout that a soft navigation reuses, and the refresh right after it raced the
navigation.

```tsx
// A full page load, not router.replace() + router.refresh(): the session changed, so every
// server-rendered part … must be rendered again.
window.location.assign(safeNext(next))
```

Source: [components/auth/login-form.tsx](../../frontend/src/components/auth/login-form.tsx),
`onSubmit`.

## Not used here

- Server Actions (`"use server"`): mutations go through the typed API client to Django.
- `next/image`, `generateStaticParams`, `useSearchParams`, middleware/proxy file: no images
  pipeline needed, pages are dynamic or cached by tag, and search params are read on the server.
- Parallel/intercepting routes, route groups beyond plain folders, i18n routing.
- ISR via `revalidate` exports: caching uses `"use cache"` instead.
