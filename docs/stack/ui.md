# UI: Tailwind, shadcn/ui, Radix, next-themes, lucide, react-day-picker, Recharts

The styling and component layer of the frontend. Tailwind 4.3.3 (utility CSS), shadcn/ui CLI 4.21.4
(copies component source into the repo; style `radix-nova`), radix-ui 1.7.0 (accessible
primitives underneath), next-themes 0.4.6, lucide-react 1.54.0, react-day-picker 10.0.2 (with
date-fns 4.4.0 as its date library), Recharts 3.8.0. Official docs:
[tailwindcss.com](https://tailwindcss.com/docs), [ui.shadcn.com](https://ui.shadcn.com/docs).

## Tailwind: utility classes and responsive prefixes

Styles are classes on the element. Unprefixed classes apply everywhere; `sm:`, `md:`, `lg:` apply
from that width up, so layouts are written mobile-first (the app supports 375 px and up).

```tsx
<ul className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-4" aria-busy="true" …>
```

Source: [components/shop/product-grid-skeleton.tsx](../../frontend/src/components/shop/product-grid-skeleton.tsx),
`ProductGridSkeleton`.

## Tailwind 4: CSS-first setup

There is no `tailwind.config.js`: Tailwind is imported in the global stylesheet, and `@theme
inline` maps utility names (`bg-background`, `text-success`) to CSS variables. CSS goes through
Tailwind's Turbopack loader (see [nextjs.md](nextjs.md#config-trailing-slashes-and-turbopack)).

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";

@theme inline {
  --color-background: var(--background);
  --color-success: var(--success);
  --color-rating: var(--rating);
```

Source: [app/globals.css](../../frontend/src/app/globals.css).

## Theme tokens as CSS variables (light and dark)

Colours are defined once as variables in `oklch`; `:root` holds the light values and `.dark` the
dark ones, so components never hard-code a colour. Beyond shadcn's tokens the project adds
`--success`, `--rating` and `--category-1..8`.

```css
:root {
  --success: oklch(0.527 0.154 150.069);
  …
}
.dark {
  --success: oklch(0.723 0.192 149.579);
```

Source: [app/globals.css](../../frontend/src/app/globals.css).

## The `dark:` variant

`@custom-variant dark` ties the `dark:` prefix to a `.dark` class on an ancestor (set by
next-themes), instead of the OS media query.

```css
@custom-variant dark (&:is(.dark *));
```

Source: [app/globals.css](../../frontend/src/app/globals.css). Used in
[theme-toggle.tsx](../../frontend/src/components/layout/theme-toggle.tsx): the sun icon scales
away with `dark:scale-0` while the moon scales in.

## Design tokens in components

Project components use the token utilities (`text-muted-foreground`, `bg-accent`) rather than raw
colours. Tints for product placeholders are static class strings (so Tailwind can see them),
picked by a hash of the category slug.

```ts
const TINTS = [
  "bg-category-1/12 text-category-1",
  "bg-category-2/12 text-category-2",
  …
]
```

Source: [components/shop/category-placeholder.tsx](../../frontend/src/components/shop/category-placeholder.tsx),
`TINTS`.

## `cn()`: conditional class names

`cn` joins class names, drops falsy ones and lets a later Tailwind class override an earlier
conflicting one. It is the `cn` npm package (a drop-in for `clsx` + `tailwind-merge`), re-exported
from [lib/utils.ts](../../frontend/src/lib/utils.ts).

```tsx
className={cn(
  "flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm transition-colors …",
  active ? "bg-accent font-medium text-foreground" : "text-muted-foreground",
)}
```

Source: [components/shop/filters-panel.tsx](../../frontend/src/components/shop/filters-panel.tsx),
the category link.

## shadcn/ui: components you own

`npx shadcn add <name>` copies the component's source into `src/components/ui/`, configured by
`components.json` (aliases, icon library, CSS file). Feature components compose these primitives
rather than hand-rolling buttons, dialogs or tables. The files in `ui/` are CLI-managed; edit
the feature components instead.

```json
"style": "radix-nova",
"tailwind": {
  "css": "src/app/globals.css",
  "baseColor": "neutral",
  "cssVariables": true,
"iconLibrary": "lucide",
```

Source: [frontend/components.json](../../frontend/components.json). Installed primitives: alert,
alert-dialog, badge, breadcrumb, button, calendar, card, chart, collapsible, dropdown-menu, field,
input, label, pagination, popover, select, separator, sheet, skeleton, switch, table.

## Variants with `cva`

shadcn components define their look variants with class-variance-authority: a base string plus
named variant choices, which become typed props (`variant="ghost"`, `size="sm"`).

```ts
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg …",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/80",
```

Source: [components/ui/button.tsx](../../frontend/src/components/ui/button.tsx), `buttonVariants`
(generated, trimmed).

## Composition: card parts and `asChild`

shadcn pieces are small and combined (`Card`, `CardHeader`, `CardContent`). `asChild` (from
Radix's `Slot`) renders the component's styling onto *your* element, so a breadcrumb or menu item
can be a real `<Link>`.

```tsx
<BreadcrumbLink asChild>
  <Link href="/shop">Shop</Link>
</BreadcrumbLink>
```

Source: [app/shop/[slug]/page.tsx](../../frontend/src/app/shop/[slug]/page.tsx), `ProductPage`.

## Radix primitives

Behaviour and accessibility (focus trapping, keyboard handling, ARIA) come from Radix, imported
through the single `radix-ui` package inside the shadcn files. Project code uses them through
shadcn: a dropdown for the user menu, an alert dialog for "Cancel order", a sheet for mobile
navigation, a popover for the date range.

```tsx
import { AlertDialog as AlertDialogPrimitive } from "radix-ui"
```

Source: [components/ui/alert-dialog.tsx](../../frontend/src/components/ui/alert-dialog.tsx);
used in [components/orders/order-actions.tsx](../../frontend/src/components/orders/order-actions.tsx).

## Loading states with `Skeleton`

Every data view has a skeleton that mirrors its final layout, used by `loading.tsx` files and
`<Suspense>` fallbacks.

```tsx
<Card className="gap-0 py-0">
  <div className="p-3 pb-0">
    <Skeleton className="aspect-square w-full rounded-lg" />
  </div>
```

Source: [components/shop/product-grid-skeleton.tsx](../../frontend/src/components/shop/product-grid-skeleton.tsx).

## Forms: `Field` components

shadcn 4's form pieces are `Field`, `FieldLabel`, `FieldError`, `FieldGroup`, wired to
react-hook-form with `Controller` (see [drf-and-openapi.md](drf-and-openapi.md#react-hook-form-with-controller)).
`data-invalid` and `aria-invalid` carry the error state for styling and screen readers.

```tsx
<Field data-invalid={fieldState.invalid}>
  <FieldLabel htmlFor="login-email">Email</FieldLabel>
  <Input {...field} id="login-email" type="email" autoComplete="email" aria-invalid={fieldState.invalid} />
  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
</Field>
```

Source: [components/auth/login-form.tsx](../../frontend/src/components/auth/login-form.tsx),
`LoginForm`.

## Accessibility basics

Labels for every input (visually hidden with `sr-only` when the design has none), `aria-label`
on icon-only buttons, `aria-hidden` on decorative icons, `aria-current` on the active link, and
visible focus rings.

```tsx
<label htmlFor="shop-search" className="sr-only">
```

```tsx
aria-current={active ? "page" : undefined}
```

Source: [components/shop/search-box.tsx](../../frontend/src/components/shop/search-box.tsx);
[components/shop/filters-panel.tsx](../../frontend/src/components/shop/filters-panel.tsx).

## next-themes: dark mode

`ThemeProvider` sets the `dark` class on `<html>` before hydration (from the OS preference or the
user's choice); `useTheme` reads and sets it. A known harmless console warning is listed under
"Known issues" in `CLAUDE.md`.

```tsx
<ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
```

```tsx
const { theme, setTheme } = useTheme()
```

Source: [app/layout.tsx](../../frontend/src/app/layout.tsx), `RootLayout`;
[components/layout/theme-toggle.tsx](../../frontend/src/components/layout/theme-toggle.tsx),
`ThemeToggle`.

## lucide-react icons

Icons are React components sized with `size-*` classes. A map from category group to icon turns
data into UI without any `if` chain.

```tsx
const ICONS: Record<CategoryGroup, LucideIcon> = {
  textiles: BedDouble,
  furniture: Sofa,
  housewares: CookingPot,
  …
}
```

Source: [components/shop/category-placeholder.tsx](../../frontend/src/components/shop/category-placeholder.tsx),
`ICONS`.

## react-day-picker: a date-range picker

shadcn's `Calendar` wraps react-day-picker. The analytics filter puts a two-month range
calendar in a popover and applies the chosen range to the URL. (date-fns is react-day-picker's
date library; project code doesn't import it.)

```tsx
<Calendar
  mode="range"
  numberOfMonths={2}
  defaultMonth={toDate(shown.from)}
  selected={range}
  onSelect={setRange}
/>
```

Source: [components/analytics/analytics-filters.tsx](../../frontend/src/components/analytics/analytics-filters.tsx),
`AnalyticsFilters`.

## Recharts: charts through shadcn's `ChartContainer`

Recharts draws SVG charts from components (`AreaChart`, `BarChart`, `XAxis`…). shadcn's
`ChartContainer` adds sizing and turns a `ChartConfig` (series names and theme colours) into CSS
variables such as `--color-gmv`, which the series reference. `satisfies ChartConfig` checks the
config while keeping its keys.

```tsx
const revenueConfig = { gmv: { label: "GMV", color: "var(--chart-1)" } } satisfies ChartConfig

<ChartContainer config={revenueConfig} className="h-64 w-full">
  <AreaChart data={data} margin={{ left: 8, right: 16 }}>
    …
    <Area isAnimationActive={false} dataKey="gmv" type="monotone" fill="var(--color-gmv)" … />
```

Source: [components/analytics/charts.tsx](../../frontend/src/components/analytics/charts.tsx),
`RevenueChart`. Animation is off because the dashboard re-renders every 10 s. More:
[analytics](../flows/analytics.md), [ADR 0011](../adr/0011-analytics-projections-recompute.md).

## Recharts: time axis, gaps and formatters

The X axis is numeric and time-scaled, so uneven dates sit proportionally apart. A `null` point
is inserted wherever days are more than 31 apart, which breaks the line instead of drawing across
(Olist history ends in 2018, app orders start in 2026). Money arrives as strings: converted to
numbers only for drawing, formatted as BRL for display.

```tsx
<XAxis dataKey="ts" type="number" scale="time" domain={["dataMin", "dataMax"]} … />
<ChartTooltip content={<ChartTooltipContent … formatter={(v) => brl(v)} />} />
```

```ts
if (previous && ts - previous.ts > GAP_DAYS * DAY_MS) points.push({ ts: previous.ts + DAY_MS, gmv: null })
```

Source: [components/analytics/charts.tsx](../../frontend/src/components/analytics/charts.tsx),
`RevenueChart` and `revenueSeries`.

## Recharts: top-N bars

Categories are drawn as horizontal bars (`layout="vertical"`); the "other" bucket from the API
becomes a one-line note instead of a giant bar.

```tsx
<BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
  <XAxis type="number" … />
  <YAxis type="category" dataKey="label" … width={150} />
  <Bar isAnimationActive={false} dataKey="revenue" fill="var(--color-revenue)" radius={4} />
```

Source: [components/analytics/charts.tsx](../../frontend/src/components/analytics/charts.tsx),
`CategoryChart`.

## Not used here

- A `tailwind.config.js`, Tailwind plugins such as typography, and separate `clsx` /
  `tailwind-merge` packages (the `cn` package replaces both).
- TanStack Table: not installed (`CLAUDE.md`: added with the first feature that needs it); the
  tables that exist use shadcn's plain `Table`.
- Toast notifications (sonner), tabs, accordion and other shadcn primitives not in the list above.
- `next/image` (product images are generated placeholders) and CSS modules / styled-components.
- Direct `date-fns` imports; Recharts' built-in animations.
