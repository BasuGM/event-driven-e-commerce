# 0004. Django sessions over JWT, behind the Next proxy

- **Status:** Accepted
- **Date:** 2026-10-14 (commit `46e9db7`, Step 3)

## Context

A Next.js frontend and a Django API run as separate services. Both the browser (Client
Components) and the Next server (Server Components) need to call the API as the logged-in
visitor. CLAUDE.md: "Session auth only (no JWT)."

## Options considered

1. **JWT in browser storage.** Stateless on the server. The token is readable by any script on
   the page, and revoking it before expiry needs extra machinery.
2. **JWT in an httpOnly cookie, with a cross-origin API.** It needs CORS with credentials and
   `SameSite=None` cookies, which are third-party cookies from the browser's point of view.
3. **Django sessions, cross-origin.** The same CORS and third-party-cookie problems as option 2.
4. **Django sessions, same-origin through a proxy.** Next rewrites `/api/*` to Django, so the
   browser sees one origin and the `sessionid` and `csrftoken` cookies are first-party.

## Decision

Option 4:
- Django's session auth, with the custom `SessionAuthentication` that answers 401 for anonymous
  requests;
- CSRF via the `X-CSRFToken` header;
- `CSRF_TRUSTED_ORIGINS` listing the browser origins, because Django sees `Host: backend:8000`
  behind the proxy, and `X-Forwarded-Host` is deliberately not trusted;
- Server Components forward the visitor's cookies to `API_URL`.

Why sessions over JWT:
- **Logout and revocation take effect immediately:** delete the session.
- **No token is readable by page scripts.**
- **The same-origin proxy makes the cookies first-party.**
- **There's no refresh-token flow to build.**

## Consequences

- **No CORS configuration and no tokens in JavaScript.** The session cookie is HttpOnly (`SESSION_COOKIE_HTTPONLY`).
- **CSRF protection is required, and is in place.**
  - Login and register are explicitly `csrf_protect`ed, because DRF only enforces CSRF for
    authenticated requests.
  - The browser client re-reads the token on every request, because Django rotates it at login.
- **Every API call from the browser takes one extra hop** through the Next proxy. The SSE stream
  needs special headers to get through it unbuffered ([0007](0007-sse-signal-plus-snapshot.md)).
- **Reading cookies makes a Server Component dynamic.** Visitor-specific fetches can't be
  cached, so they live under `<Suspense>`.
- **Before production:** secure cookies, HTTPS, and the real origins in
  `CSRF_TRUSTED_ORIGINS`. These are in CLAUDE.md's "Before deploying" list.

## Links

- [docs/flows/auth-and-sessions.md](../flows/auth-and-sessions.md)
- [frontend/next.config.ts](../../frontend/next.config.ts), [backend/apps/accounts/authentication.py](../../backend/apps/accounts/authentication.py), [frontend/src/lib/api/server.ts](../../frontend/src/lib/api/server.ts), [frontend/src/lib/api/browser.ts](../../frontend/src/lib/api/browser.ts)
- Tests: `test_unauthenticated_is_401_not_403`, `test_login_requires_csrf_token`, `test_proxy_shape_trusted_origin_with_backend_host_is_accepted`
