# Auth and sessions

Visitors log in with email and password and get a Django session cookie. There are no tokens
(JWT or otherwise). This works cleanly because the browser never talks to Django directly:
every `/api/*` call goes to the Next.js origin and is proxied, so Django's cookies are
first-party.

## The same-origin proxy

```
browser ──/api/*──▶ Next.js :3000 ──rewrite──▶ Django backend:8000
         cookies: sessionid, csrftoken (first-party, SameSite=Lax)
```

- **The rewrite.** [frontend/next.config.ts](../../frontend/next.config.ts) rewrites `/api/:path*`
  to `${API_URL}/api/:path*/`.
- **Trailing slashes.** `skipTrailingSlashRedirect: true` stops Next from redirecting Django's
  trailing-slash URLs. A redirected `POST` would fail, because Django can't redirect a POST
  under `APPEND_SLASH`.
- **What this avoids:** CORS configuration, third-party cookies, and storing a token in
  JavaScript-readable storage.
- **The cookie settings** in [config/settings/base.py](../../backend/config/settings/base.py):
  - `SESSION_COOKIE_HTTPONLY = True`: page scripts can't read the session cookie.
  - `CSRF_COOKIE_HTTPONLY = False`: on purpose, so the browser client can read the token and
    echo it back.
  - Both cookies are `SameSite=Lax`.

The ADR on sessions vs JWT will record the alternatives (written in the ADR batch).

### `CSRF_TRUSTED_ORIGINS`

- **The problem.** Through the proxy, Django sees `Host: backend:8000`, but the browser's
  `Origin: http://localhost:<port>`. Django's CSRF check compares the origin with the host, so
  the browser origins are listed explicitly in `CSRF_TRUSTED_ORIGINS` (from `.env`).
- **What isn't done instead.** Django is not told to trust `X-Forwarded-Host`. The backend port
  is published to the host, so anyone who can reach it directly could set that header.
- **Tests:** `test_untrusted_origin_is_rejected` and
  `test_proxy_shape_trusted_origin_with_backend_host_is_accepted`.

## Logging in

All of this is in [backend/apps/accounts/views.py](../../backend/apps/accounts/views.py).

1. **The CSRF cookie.** The frontend makes sure a `csrftoken` cookie exists. `ensureCsrf()`
   calls `GET /api/auth/csrf/`, which is decorated with `ensure_csrf_cookie`.
2. **The request.** `POST /api/auth/login/` with `{email, password}`.
   - The view is `csrf_protect`ed explicitly. DRF's `SessionAuthentication` only enforces CSRF
     for requests that are already authenticated, and login is anonymous. Without the
     decorator, another site could log a visitor into an attacker's account (login CSRF).
   - The account is looked up by email, case-insensitively. Then Django's `authenticate()`
     checks the password against that account's username.
   - On failure the response is `400 {"code": "invalid_credentials", …}`. The message is the
     same whether the email or the password was wrong.
3. **The session.** `login()` starts the session. Django then rotates both the session id and
   the CSRF token.
4. **A full page load to `next`** (`window.location.assign`). See
   [After an auth change: a full page load](#after-an-auth-change-a-full-page-load).

### CSRF rotation is Django's behaviour

The CSRF rotation at login is
[Django's built-in behaviour](https://docs.djangoproject.com/en/6.1/ref/csrf/#why-might-a-user-encounter-a-csrf-validation-failure-after-logging-in):
`django.contrib.auth.login()` calls `django.middleware.csrf.rotate_token()`. The project
doesn't implement it. The project's only part is to cope with it.
[frontend/src/lib/api/browser.ts](../../frontend/src/lib/api/browser.ts) reads the `csrftoken`
cookie **on every unsafe request** and sends it as `X-CSRFToken`, instead of caching the token
once. A token cached before login would be stale afterwards.

### Registering and logging out

- **`POST /api/auth/register/`** creates the user and logs them in (201).
  - The email is lower-cased and must be unique, case-insensitively. A partial unique index on
    `Lower(email)` backs this up.
  - The password goes through Django's password validators, and failures come back as 400 field
    messages.
  - The username is set to the email.
- **`POST /api/auth/logout/`** ends the session (204).
- **Register and logout also end with a full page load:** to `next` after registering, to `/` after
  logging out.

`seed_dev_users` creates four dev accounts (admin, staff, customer, replay). It refuses to run
without `ALLOW_DEV_SEED`, which only the dev and test settings set.

## 401, 403, 404

| Situation | Status | Why |
|---|---|---|
| Not logged in, on an endpoint that needs a session | **401** | The custom `SessionAuthentication` in [authentication.py](../../backend/apps/accounts/authentication.py) returns a `WWW-Authenticate` value (`Session`). That's what makes DRF answer 401 instead of 403 |
| Logged in, but the CSRF token is missing or wrong | **403** | |
| Another user's order, or cart line | **404** | A 403 would confirm that the thing exists |
| Any `/api/staff/*` endpoint without `is_staff` (including anonymous) | **404** | `IsStaffOr404` ([staff-tools.md](staff-tools.md)) |

The frontend relies on that split. A 401 means "send the visitor to the login page". A 403 is a
real error.

Every endpoint requires a session by default (`DEFAULT_PERMISSION_CLASSES = IsAuthenticated`).
The public ones opt out explicitly: the catalog, health, stats, the auth endpoints, and the
signed webhook.

## Server Components act as the visitor

Pages are mostly Server Components. They fetch data on the server, so they have to send the
visitor's session themselves. `asVisitor()` in
[frontend/src/lib/api/server.ts](../../frontend/src/lib/api/server.ts) builds a typed client
for `API_URL`, and copies the incoming request's cookies into a `cookie` header.

- **Reading cookies makes a component dynamic.** These fetchers therefore run under
  `<Suspense>` or a `loading.tsx`, and never inside `"use cache"`. A cached page must not
  contain one visitor's data.
- **Protected pages use `orLogin()`.** It wraps the fetch and turns a 401 (`NotAuthenticatedError`)
  into `redirect("/login?next=<path>")`.
- **The header's account area** (`HeaderAccount`) renders under its own `<Suspense>`. It shows
  the user menu and the cart badge from one `GET /api/auth/me/`. If that call fails, the
  header falls back to "logged out" rather than breaking the page.
- **Client Components inside cached or prerendered pages never read cookies or the URL.**
  What they need is passed in as props. For example, `AddToCart` receives `returnTo` from the
  page instead of calling `usePathname()`.

## After an auth change: a full page load

After login, register and logout, the forms navigate with `window.location.assign()`, not a
client-side `router.push`/`replace`:

- **Why a full load.** The session changed, so everything server-rendered for the old session must
  render again: the header's user menu and cart badge (a Server Component in the root layout,
  which a client-side navigation reuses unchanged), and any route the client router has cached.
- **What it replaced.** The forms used to call `router.replace(next)` and then immediately
  `router.refresh()`, to re-render the header. Under load that refresh's request could stall, and
  the navigation then never completed: the URL stayed on `/login`. A Playwright trace from
  2026-11-09 shows this for the identical checkout pattern: the refresh's request was still
  pending after more than 20 s, and the URL never changed. Seen in 3 of 6 full e2e runs.
- **The regression check.** The e2e `logIn()` helper asserts the header shows the account menu
  after login.

## Before hydration: disabled controls and POST forms

A server-rendered page is visible before React hydrates it. Until then, its buttons look ready but
do nothing, and a form falls back to the browser's native behaviour.

- **The risk that's now closed.** The login, register and checkout forms used to have no `method`,
  and their inputs carry `name` attributes. A submit before hydration was therefore a native
  **GET** to the current URL, with the fields in the query string:
  `/login?next=/shop&email=…&password=…`, or the shipping address on `/checkout`. That puts
  credentials in the URL, browser history, server access logs and `Referer` headers.
- **The fix, part 1: `method="post"`** on all three forms, so even a native submit never puts
  fields in the URL.
- **The fix, part 2: controls disabled until hydrated.** The `useHydrated()` hook
  ([frontend/src/lib/use-hydrated.ts](../../frontend/src/lib/use-hydrated.ts)) returns false in
  the server render and during hydration, then true. These controls render **disabled** until
  then:
  - the login, register and Place order submits (a disabled default button also blocks a submit
    by Enter);
  - Pay, Cancel order, Add to cart, the cart's quantity and Remove, the account menu (which holds
    Log out), and the dead-letter Retry.

  So a click can't be lost, and a form can't be submitted natively. Playwright waits for a control
  to be enabled before clicking.
- **Tests.** A unit test server-renders the login form and checks its `method="post"` and its
  disabled submit ([use-hydrated.test.tsx](../../frontend/src/lib/use-hydrated.test.tsx)). In e2e,
  a "Pay" click made 0.9 s before hydration had sent no request at all; that can't happen now.

## After login: `next` and the cart intent

- **The `next` redirect.** The login and register pages accept `?next=<path>`. `safeNext()` in
  [frontend/src/lib/urls.ts](../../frontend/src/lib/urls.ts) allows only same-site relative
  paths. It rejects `//evil.com` and `/\evil.com`, so `next` can't be used as an open redirect.
- **Add to cart while logged out.**
  - When the add returns 401, the visitor is sent to log in with the intent encoded in `next`,
    as `?add=<offer>.<quantity>.<nonce>`
    ([cart-intent.ts](../../frontend/src/lib/cart-intent.ts)).
  - Back on the product page, `CartIntentReplay` adds the item once. It claims the nonce in
    `sessionStorage` first, so a reload or a Back press that brings the URL back never adds it
    twice.
  - It then strips the parameter with `history.replaceState`.
- **Browser-generated keys use `crypto.getRandomValues`.** `crypto.randomUUID` only exists in
  secure contexts, so it fails on plain HTTP via another host, such as the e2e container or a LAN
  address.

## Not done yet

There is no rate limiting on login or register, cookies aren't `Secure` yet, and there is no
HTTPS. These are listed in CLAUDE.md's "Before deploying" checklist and in
[limitations-and-roadmap.md](../limitations-and-roadmap.md).

## Sources

- [backend/apps/accounts/](../../backend/apps/accounts/) (views, serializers, authentication, models)
- [backend/config/settings/base.py](../../backend/config/settings/base.py) (sessions, CSRF, `REST_FRAMEWORK`)
- [frontend/next.config.ts](../../frontend/next.config.ts), [frontend/src/lib/api/server.ts](../../frontend/src/lib/api/server.ts), [frontend/src/lib/api/browser.ts](../../frontend/src/lib/api/browser.ts), [frontend/src/lib/urls.ts](../../frontend/src/lib/urls.ts), [frontend/src/lib/cart-intent.ts](../../frontend/src/lib/cart-intent.ts)
- [frontend/src/components/auth/](../../frontend/src/components/auth/) (login and register forms), [frontend/src/components/layout/user-menu.tsx](../../frontend/src/components/layout/user-menu.tsx) (logout), [frontend/src/lib/use-hydrated.ts](../../frontend/src/lib/use-hydrated.ts)
- Tests: [test_auth.py](../../backend/tests/test_auth.py), [cart-intent.test.ts](../../frontend/src/lib/cart-intent.test.ts), [use-hydrated.test.tsx](../../frontend/src/lib/use-hydrated.test.tsx), [e2e/helpers.ts](../../frontend/e2e/helpers.ts) (`logIn`)
