# 0012. `Order.source` with no default

- **Status:** Accepted
- **Date:** 2026-11-09 (commit `4c3cd2f`, Step 7b; `replay` added in `fad9cf3`, Step 7c)

## Context

Orders come from different places:
- **imported Olist history**: two years of data, no customer accounts;
- **orders placed in the app**;
- **replayed copies of history** (later).

Analytics must report them separately: a day of test orders shouldn't flatten two years of
history. The shop must also ignore replay copies for prices, sales counts and public counts.
Before this decision there was no explicit marker; "has a user account" was only an indirect
hint.

## Options considered

1. **Infer the origin** (a customer with a user = app). It's implicit, and breaks as soon as a
   third origin appears; replay copies belong to a user too.
2. **A boolean such as "is imported".** It can't express a third value.
3. **A `source` field with a default** (for example `app`). A new creation path that forgets to
   set it would silently be counted as the default.
4. **A required `source` with no default.**

## Decision

`Order.source` is `olist` | `app` | `replay`, and required, with **no default**:
- the importer sets `olist`;
- `checkout()` sets `app`;
- the replay sets `replay`.

CLAUDE.md: "no default, so a new creation path can't forget it". It was added to a populated
table in three migrations:
1. add the column as nullable;
2. backfill with frozen SQL: `app` if the customer has a user, else `olist`;
3. make it required, with the index `(source, purchased_at)`.

## Consequences

- **Every creation path has to say where an order came from,** and Django refuses to create an
  order without it.
- **Analytics reports every metric per source,** and the dashboard defaults to `olist`.
- **The shop's exclusions are explicit SQL conditions** (`o.source <> 'replay'`), so they're easy
  to audit.
- **Event payloads carry it as `order_source`.** The name `source` was already taken in
  `ReservationExpired`. Consumers use it to skip replay events.

## Links

- [docs/data-model.md](../data-model.md#migration-pattern-for-populated-tables), [docs/flows/analytics.md](../flows/analytics.md)
- [backend/apps/orders/models.py](../../backend/apps/orders/models.py), [backend/apps/orders/migrations/](../../backend/apps/orders/migrations/) (0003–0005)
