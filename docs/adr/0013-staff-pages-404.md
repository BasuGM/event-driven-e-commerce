# 0013. Staff pages answer 404 to everyone else

- **Status:** Accepted
- **Date:** 2026-11-05 (commit `204f26a`, Step 7a; title handling refined in `fad9cf3`)

## Context

The staff tools (event explorer, consumer health, dead-letter retry, sales analytics) expose
internal and business data. Someone who isn't staff shouldn't learn that they exist. Two
constraints complicate this:
- **401 and 403 confirm existence.** A 401 says "this exists, log in"; a 403 says "this exists,
  not for you".
- **A streamed page already sent 200.** On a streamed Next.js route, a nested `notFound()` comes
  after the HTTP 200 status has been sent. So a staff page's static shell must reveal nothing.

## Options considered

1. **Standard auth responses** (401 / 403). Simple, but they reveal the endpoints.
2. **404 for everyone who isn't staff**, in both the API and the pages.

## Decision

- **The API.** `IsStaffOr404` raises `NotFound` for anonymous and non-staff users alike.
- **The pages.** There's no shared layout with staff chrome. Each page renders its staff header
  only after its own staff API call succeeded. `app/staff/layout.tsx` sets only a neutral title
  ("Olist Commerce") and `noindex, nofollow`.
- **The real page title.** It's set client-side by `DocumentTitle` after the check, and kept
  through `router.refresh()` with a `MutationObserver`.

## Consequences

- **Nothing reveals the staff tools to an outsider:** not the status, the title, the navigation,
  nor the HTML.
- **A staff page's not-found still has HTTP status 200** (Next's streaming behaviour). Only the
  content and metadata are neutral.
- **The title needs client-side care:** a mutation observer, an e2e test through a real refresh,
  and a component test.
- **Debugging is a little less friendly.** A staff user who isn't logged in sees "not found",
  not "please log in".

## Links

- [docs/flows/staff-tools.md](../flows/staff-tools.md)
- [backend/apps/staff/permissions.py](../../backend/apps/staff/permissions.py), [frontend/src/app/staff/layout.tsx](../../frontend/src/app/staff/layout.tsx), [frontend/src/components/staff/document-title.tsx](../../frontend/src/components/staff/document-title.tsx)
- Tests: `test_staff_endpoints_are_404_for_anonymous_and_customers`, [e2e/staff-title.spec.ts](../../frontend/e2e/staff-title.spec.ts)
