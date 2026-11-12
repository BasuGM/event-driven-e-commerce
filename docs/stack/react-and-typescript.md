# React and TypeScript

React renders the UI as components; TypeScript checks the types. Both are used through Next.js
(see [nextjs.md](nextjs.md)). React 19.3.0 (with react-dom), TypeScript 5.9.3 in `strict` mode.
Official docs: [react.dev](https://react.dev/), [typescriptlang.org/docs](https://www.typescriptlang.org/docs/).

## Components and props

A component is a function that takes props and returns JSX. Props get an inline type; optional
ones are marked `?`. Most components here are Server Components (no state, no `"use client"`).

```tsx
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: React.ReactNode
}) {
```

Source: [components/layout/page-header.tsx](../../frontend/src/components/layout/page-header.tsx),
`PageHeader`.

## Conditional rendering and lists

`cond && <X/>` and ternaries decide what shows; `.map` renders lists (each with a `key`). Empty
states are written explicitly, since every data view needs one.

```tsx
{product.offers.length > 0 ? (
  <OffersTable offers={product.offers} productSlug={product.slug} />
) : (
  <p className="text-sm text-muted-foreground">No sellers offer this product right now.</p>
)}
```

Source: [app/shop/[slug]/page.tsx](../../frontend/src/app/shop/[slug]/page.tsx), `ProductPage`.

## `useState`

State local to a component; calling the setter re-renders it. Used for form-level error
messages and connection status.

```tsx
const [formError, setFormError] = useState<string | null>(null)
```

Source: [components/auth/register-form.tsx](../../frontend/src/components/auth/register-form.tsx),
`RegisterForm`.

## `useEffect` and cleanup

Runs after render to synchronise with something outside React (a timer, a subscription). The
returned function cleans up before the next run or on unmount. The dashboard refreshes itself on
a timer this way.

```tsx
useEffect(() => {
  const timer = window.setInterval(() => {
    if (document.visibilityState === "visible") router.refresh()
  }, REFRESH_MS)
  return () => window.clearInterval(timer)
}, [router])
```

Source: [components/analytics/auto-refresh.tsx](../../frontend/src/components/analytics/auto-refresh.tsx),
`AutoRefresh`.

## `useRef`

A box that survives renders without causing one. Here it lets a long-lived `EventSource`
callback read the *latest* rendered version without re-subscribing.

```tsx
const renderedRef = useRef(renderedVersion)
renderedRef.current = renderedVersion
```

Source: [lib/use-order-live.ts](../../frontend/src/lib/use-order-live.ts), `useOrderLive`.

## `useMemo`

Caches a computed value until its dependencies change. The debounce hook returns a stable
function so consumers can list it in an effect's dependencies without it changing every render.

```tsx
return useMemo(() => {
  const debounced = (...args: A) => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => callbackRef.current(...args), delay)
  }
  debounced.cancel = () => clearTimeout(timer.current)
  return debounced
}, [delay])
```

Source: [hooks/use-debounced-callback.ts](../../frontend/src/hooks/use-debounced-callback.ts),
`useDebouncedCallback`.

## `useTransition`

Marks an update as non-urgent and gives a `pending` flag. For navigation it keeps the current
results on screen (dimmed) until the new ones arrive instead of flashing a skeleton; for async
handlers it disables buttons while a request runs.

```tsx
const [isPending, startTransition] = useTransition()

const navigate = (href: string) =>
  startTransition(() => router.push(href, { scroll: false }))
```

Source: [components/shop/shop-navigation.tsx](../../frontend/src/components/shop/shop-navigation.tsx),
`ShopNavigationProvider`.

## Context

Passes values down without threading props. The shop's filters and `apply` function are provided
once and read by the search box, sort select and filter panel through a small hook that fails
loudly outside the provider.

```tsx
const ShopNavigationContext = createContext<ShopNavigation | null>(null)
…
export function useShopNavigation(): ShopNavigation {
  const value = useContext(ShopNavigationContext)
  if (!value) throw new Error("useShopNavigation must be used inside ShopNavigationProvider")
  return value
}
```

Source: [components/shop/shop-navigation.tsx](../../frontend/src/components/shop/shop-navigation.tsx),
`useShopNavigation`.

## Custom hooks

A function starting with `use` that composes other hooks. `useOrderLive` wraps `EventSource` for
the order page: it opens the stream, asks Next to re-render when the server's snapshot differs
from what is on screen, and falls back to a slow refresh if the stream gives up.

```tsx
const source = new EventSource(`/api/orders/${orderId}/stream/`)
source.onopen = () => setConnection("live")
source.addEventListener("snapshot", (event) => {
  const next = JSON.parse((event as MessageEvent<string>).data) as OrderSnapshot
  setSnapshot(next)
  if (next.version !== renderedRef.current) router.refresh()
})
```

Source: [lib/use-order-live.ts](../../frontend/src/lib/use-order-live.ts), `useOrderLive`.
More: [live-tracking](../flows/live-tracking.md).

## `useLayoutEffect` and `MutationObserver`

A layout effect runs synchronously after the DOM updates, before paint. The staff page title
uses one so its observer disconnects in the same commit that unmounts the component, before it
could overwrite the next page's title.

```tsx
useLayoutEffect(() => {
  const full = `${title} · Staff · Olist Commerce`
  const apply = () => {
    if (document.title !== full) document.title = full
  }
  apply()
  const observer = new MutationObserver(apply)
  observer.observe(document.head, { childList: true, subtree: true, characterData: true })
  return () => observer.disconnect()
}, [title])
```

Source: [components/staff/document-title.tsx](../../frontend/src/components/staff/document-title.tsx),
`DocumentTitle`.

## Hydration: `useSyncExternalStore` and "disabled until hydrated"

Server HTML shows a button before its click handler exists. `useHydrated` is `false` during the
server render and hydration and `true` afterwards, so JavaScript-driven controls render disabled
until they work, and forms use `method="post"` as a no-JS fallback.

```tsx
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true, // client
    () => false, // server render and hydration
  )
}
```

```tsx
<Button onClick={pay} disabled={!hydrated || pending}>
```

Source: [lib/use-hydrated.ts](../../frontend/src/lib/use-hydrated.ts), `useHydrated`;
[components/orders/order-actions.tsx](../../frontend/src/components/orders/order-actions.tsx),
`OrderActions`.

## Server/client split: no browser APIs in cached or prerendered components

Client Components inside cached pages must not read the URL or cookies themselves; they get what
they need as props (for instance `returnTo`). Browser-only values use APIs that exist everywhere
(`crypto.getRandomValues`, not `crypto.randomUUID`, which needs a secure context).

```ts
const bytes = crypto.getRandomValues(new Uint8Array(16))
```

Source: [lib/checkout-attempt.ts](../../frontend/src/lib/checkout-attempt.ts).

## TypeScript: strict mode and the `@/` alias

`strict` turns on null checks and the rest of the strict family. `paths` lets imports start from
`src/` (`@/lib/...`) instead of long relative paths. `make typecheck` runs `tsc --noEmit`.

```json
"strict": true,
…
"paths": {
  "@/*": ["./src/*"]
}
```

Source: [frontend/tsconfig.json](../../frontend/tsconfig.json).

## Union types as results

A discriminated union (`status` is the discriminant) makes the caller handle every case; a
failed filter isn't an exception, it is data.

```ts
export type ProductsResult =
  | { status: "ok"; page: ProductPage }
  | { status: "invalid"; errors: Record<string, string[]> }
```

Source: [lib/api/catalog.ts](../../frontend/src/lib/api/catalog.ts), `ProductsResult`.

## `as const` and deriving types from values

`as const` freezes an array into a tuple of literals; indexing it with `number` derives the union
type, so the list of orderings is written once.

```ts
export const ORDERINGS = ["popular", "price", "-price", "rating", "newest"] as const
export type ShopOrdering = (typeof ORDERINGS)[number]

export const ORDERING_LABELS: Record<ShopOrdering, string> = {
```

Source: [lib/shop-params.ts](../../frontend/src/lib/shop-params.ts). `Record<Key, Value>` makes the
compiler require a label for every ordering.

## Generics

A type parameter lets one function work over many types while keeping them linked. `withTimeout`
returns whatever its callback returns; the debounce hook keeps the callback's argument types.

```ts
export async function withTimeout<T>(label: string, call: (signal: AbortSignal) => Promise<T>): Promise<T> {
```

```ts
export function useDebouncedCallback<A extends unknown[]>(callback: (...args: A) => void, delay: number) {
```

Source: [lib/api/client.ts](../../frontend/src/lib/api/client.ts), `withTimeout`;
[hooks/use-debounced-callback.ts](../../frontend/src/hooks/use-debounced-callback.ts).

## Utility types: `Pick`, `Path`

`Pick` builds a type from some fields of another; here the stream's snapshot is "the order
detail's fields that can change, plus a version". `Path<T>` (from react-hook-form) is the union
of valid field names for a form's value type.

```ts
export type OrderSnapshot = Pick<
  OrderDetail,
  "status" | "status_history" | "payment" | "can_pay" | "can_cancel" | "reservation_expires_at"
> & { version: string }
```

Source: [lib/use-order-live.ts](../../frontend/src/lib/use-order-live.ts), `OrderSnapshot`.

## Types generated from the API

Request and response types come from the OpenAPI schema, not hand-written, so a backend change
that breaks the frontend fails `make typecheck`.

```ts
type OrderPayment = components["schemas"]["OrderPayment"]
```

Source: [components/orders/payment-confirmation.tsx](../../frontend/src/components/orders/payment-confirmation.tsx).
More: [drf-and-openapi.md](drf-and-openapi.md#from-schema-to-types-make-types).

## `satisfies`

Checks a value against a type *without widening it*: `revenueConfig` is validated as a
`ChartConfig` but keeps its exact keys, so charts can refer to `gmv` and get autocomplete.

```ts
const revenueConfig = { gmv: { label: "GMV", color: "var(--chart-1)" } } satisfies ChartConfig
```

Source: [components/analytics/charts.tsx](../../frontend/src/components/analytics/charts.tsx).

## Not used here

- `forwardRef` (React 19 passes `ref` as a prop), `useCallback`, `useOptimistic`,
  `useActionState`, `useReducer`: simple state and transitions were enough.
- Class components, higher-order components, a global state library (Redux, Zustand): server
  data plus the URL is the state.
- Enums, decorators, namespaces; `any` is avoided (`strict`).
