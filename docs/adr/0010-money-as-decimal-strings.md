# 0010. Money as `Decimal`, serialised as decimal strings

- **Status:** Accepted
- **Date:** 2026-10-13 (`DecimalField` money since commit `a964108`, Step 1; decimal strings in the API since `73666d8`, Step 2)

## Context

Prices, freight, totals, GMV and refunds all need exact cents. Binary floating point can't
represent most decimal fractions exactly. JSON numbers are parsed as IEEE-754 doubles by
JavaScript's `JSON.parse`, so a JSON number reaches the browser as a float.

## Options considered

1. **Floats** in the database or the API. They're rejected by the CLAUDE.md domain rule:
   "never floats".
2. **Integer cents.** Exact, but every display and import step must convert, and Olist's CSVs
   are in decimal reais.
3. **`Decimal` in Python and Postgres, decimal strings in JSON.**

## Decision

- **Storage:** `DecimalField(max_digits=12, decimal_places=2)`. The aggregate analytics columns
  are wider (`max_digits=14`).
- **The API, event payloads, and the outbox** carry money as decimal strings, like `"75.01"`.
  `DjangoJSONEncoder` serialises a `Decimal` that way.
- **Computations stay exact.** Medians are computed in `numeric`, never through
  `percentile_cont`, which goes through `float8`. AOV is computed with `Decimal` division,
  rounded half-up.

## Consequences

- **Exact to the cent.** The replay's analytics matched the imported totals to the cent
  (2026-11-09), consistent with exact arithmetic end to end.
- **The frontend formats, it doesn't calculate.** `formatBRL()` converts the string to a number
  only for `Intl.NumberFormat` display. No money arithmetic happens in JavaScript.
- **Clear API types.** Money fields are `string` in the generated TypeScript types, which makes
  them obvious to callers.

## Links

- [docs/api.md](../api.md#conventions), [docs/data-model.md](../data-model.md#conventions)
- [backend/apps/catalog/stats.py](../../backend/apps/catalog/stats.py) (median in numeric), [backend/apps/events/outbox.py](../../backend/apps/events/outbox.py), [frontend/src/lib/format.ts](../../frontend/src/lib/format.ts)
- Tests: `test_list_prices_are_strings_with_two_decimals`, `test_format_brl_matches_the_storefront`
