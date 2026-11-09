# 0007. SSE: Pub/Sub signal + DB snapshot, on a separate ASGI service

- **Status:** Accepted
- **Date:** 2026-11-04 (commit `3961297`, Step 6); the snapshot is read after subscribing since commit `cec4819`

## Context

An open order page should update by itself when the order changes, for example when the
payment webhook arrives. The updates flow server → client only, and are rare: a few per order.
The API is synchronous Django under WSGI. CLAUDE.md lists websockets as out of scope.

## Options considered

1. **Short-interval polling.** Simple, but it wastes requests and is slow to show changes.
   CLAUDE.md: "No 2-second polling anywhere."
2. **Websockets.** Out of scope per CLAUDE.md. Updates flow only server → browser, and websockets
   would add a protocol upgrade and custom reconnect logic, for two-way traffic the page doesn't
   need. SSE is plain HTTP through the existing proxy, with automatic reconnect and
   `Last-Event-ID` built in.
3. **SSE with the state inside each message.** Pub/Sub is fire-and-forget, so a missed message
   would leave the page wrong until the next one.
4. **SSE where the message is only a signal, and the state comes from the database.** A dropped
   signal is fixed by the next one, a reconnect or a fallback poll.
5. **Run the whole API on ASGI.** Synchronous Django views would then share a thread-sensitive
   executor and queue behind each other.

## Decision

Option 4, served by a **separate ASGI `stream` service** (uvicorn) for this one path. The rest
of the API stays on WSGI.
- **The signal.** The `order_live` consumer publishes `live:order:<id>`. The stream then
  re-reads a snapshot built by the same serializer as the order API, and sends it as
  `id: <version>`.
- **Versions.** The version is a content hash. A reconnect's `Last-Event-ID` equal to the current
  version gets no replay, and an unchanged version is never re-sent.
- **Subscribe first.** The stream subscribes **before** it reads the first snapshot, so a change
  committed while it connects isn't missed.
- **The page.** It calls `router.refresh()` when the version differs from the one it rendered:
  one render path.
- **The proxy.** `Cache-Control: no-transform` and `X-Accel-Buffering: no` stop proxy buffering,
  and a heartbeat every 15 s stays under the proxy's 30 s idle timeout.

## Consequences

- **An open stream costs a suspended coroutine, not a worker thread.** The view refuses under
  WSGI with a 404.
- **Correct even when signals are lost.** The fallbacks:
  - Redis down → the stream re-reads the database every 5 s;
  - the stream service down → EventSource reconnects;
  - EventSource gives up → the page refreshes every 15 s.
- **One more service** to deploy and route, and its own production checklist: proxy buffering,
  timeouts, HTTP/1.1.
- **One Redis connection per open stream.** At scale this becomes one shared subscriber per
  process with fan-out.
- **Only the order detail page is live.** The orders list would need a per-user channel.

## Links

- [docs/flows/live-tracking.md](../flows/live-tracking.md)
- [backend/apps/orders/stream.py](../../backend/apps/orders/stream.py), [backend/apps/orders/live.py](../../backend/apps/orders/live.py), [backend/config/asgi.py](../../backend/config/asgi.py), [frontend/src/lib/use-order-live.ts](../../frontend/src/lib/use-order-live.ts)
- Tests: [test_order_stream.py](../../backend/tests/test_order_stream.py)
