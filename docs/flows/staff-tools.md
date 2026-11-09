# Staff tools

Staff users (`is_staff`) get a **Staff** link in the header, with four pages:

| Page | What it shows |
|---|---|
| `/staff/events` | The event explorer: every domain event, newest first, filterable by type, aggregate id and date range, each with its JSON payload |
| `/staff/orders/<id>` | One order's events in order, each with the consumers that should process it and when they did |
| `/staff/health` | Per consumer group: pending, lag, active and inactive consumers. Also the outbox backlog and the last 100 dead letters, each with a **Retry** button |
| `/staff/analytics` | The sales dashboard ([analytics.md](analytics.md)) |

`/staff` itself redirects to `/staff/events`.

## Invisible to everyone else

**The API.** Every `/api/staff/*` endpoint uses `IsStaffOr404`
([backend/apps/staff/permissions.py](../../backend/apps/staff/permissions.py)). Anonymous
visitors and logged-in customers **both get 404**, not 401 or 403, because either of those
would confirm that the endpoint exists
(`test_staff_endpoints_are_404_for_anonymous_and_customers`).

**The pages** need more care. A Next.js route that streams its content has already sent HTTP 200
by the time a nested `notFound()` runs. So the static parts of a staff page must not give it
away:

- **No shared staff layout with staff chrome.** Each page renders its staff header (tabs and
  title) **inside** its data section, only **after** the staff API call has succeeded. A
  non-staff visitor sees the generic not-found UI and never a flash of staff navigation.
- **A neutral title.** [app/staff/layout.tsx](../../frontend/src/app/staff/layout.tsx) gives
  every `/staff/*` page the title "Olist Commerce" and `robots: noindex, nofollow`. Staff pages
  export no `metadata` title of their own.
- **The real title is set client-side.** "Events · Staff · Olist Commerce" and the like are set
  by `DocumentTitle` inside the staff header, so they never appear in the server HTML.
  - Next re-applies the neutral metadata title on every `router.refresh()`, and on navigation
    its streamed metadata can land after the component has mounted.
  - So `DocumentTitle` watches `<head>` with a `MutationObserver` while mounted, and restores
    the staff title. It uses a layout effect, so it disconnects before the next page's title is
    set.
  - Tested by [e2e/staff-title.spec.ts](../../frontend/e2e/staff-title.spec.ts) (through a real
    refresh) and `document-title.test.tsx`.

## Event explorer

**Where the history comes from.** The outbox is only a 7-day delivery buffer, so the explorer
reads **`EventLog`**. The `event_log` consumer writes every event from every stream into it,
exactly once: `event_types = ALL`, deduped by `ProcessedEvent` and a unique `event_id`
(`test_event_log_stores_every_event_once`).

**The list.** `GET /api/staff/events/`: newest first, 50 per page. Filters are validated by a
serializer:
- `type`;
- `aggregate_id`, the order's external id;
- `date_from`, `date_to`.

Filters live in the URL ([lib/staff-params.ts](../../frontend/src/lib/staff-params.ts)), and
blank fields redirect to a clean URL.

**An order's timeline** (`GET /api/staff/orders/<id>/events/`) lists the order's events, oldest
first. Each event shows **the consumers that should process it**: computed from the registered
consumers' streams and event types, not from what happened to run. Next to each, its
`ProcessedEvent.processed_at`, or "pending". So it shows exactly where a stuck event is stuck
(`test_order_timeline_lists_events_in_order_with_consumer_status`).

**It doesn't need the order to exist.** It reads only `EventLog` and `ProcessedEvent`. After a
`replay_reset` the timeline is simply empty. An event logged after its order was deleted (a
forced reset) still renders.

## Health

`GET /api/staff/health/` is built in
[backend/apps/staff/services.py](../../backend/apps/staff/services.py):

- **One row per expected (stream, group).** The expected pairs come from the consumer registry,
  so a consumer that has never started shows as "group doesn't exist". For each group:
  - `pending`: delivered but not acknowledged (`XPENDING`);
  - `lag`: entries not yet delivered to the group (`XINFO GROUPS`);
  - the last delivered id.
- **Active vs inactive consumers.** A consumer counts as active if it tried to read within
  `EVENTS_CONSUMER_ACTIVE_IDLE_MS` (1 min). Names left from restarts show as inactive, until a
  restarting consumer prunes the ones with nothing pending
  ([event-pipeline.md](event-pipeline.md#recovery-and-dead-letters)).
- **The outbox backlog:** the unpublished count and the oldest unpublished row's age.
- **The last 100 dead letters** from `events:dlq`. Each shows the event, the consumer that gave
  up, its delivery count and last error, and whether it has already been retried.

## Dead-letter retry

`POST /api/staff/dead-letters/<entry_id>/retry/` is staff-only, and needs a CSRF token
(`test_retry_needs_a_csrf_token`). The **Retry** button calls it, then refreshes the page.

`retry_dead_letter()`:

1. **Looks up the DLQ entry,** and strips the `dlq_*` fields to recover the original stream fields,
   including the **same event id**.
2. **Inserts `DeadLetterRetry(dlq_entry_id)`** (unique, and recording who retried it) and, in the
   same transaction, `XADD`s the original fields back onto the event's stream.
3. **Retrying the same DLQ entry again changes nothing.** It returns the earlier result. The
   unique row acts as the lock for concurrent clicks.

**Why only the failed consumer does any work.** The re-added entry is new, so **every** group on
that stream sees it:
- **Groups that already processed the event** find their `ProcessedEvent` row and just
  acknowledge it.
- **The consumer that dead-lettered it has no row,** because each of its attempts rolled back.
  So it applies the event now.

Net effect: exactly the failed consumer does the work, once
(`test_retry_redelivers_a_dead_letter_once_and_only_the_failed_consumer_applies_it`).

**What stays the same.** The DLQ entry stays on `events:dlq` for the record, marked as retried.
If the commit failed after the `XADD`, the event could be delivered again later. Consumer dedupe
absorbs that.

## Retention

Beat's `purge_old_events` keeps:
- `EventLog` and `ProcessedEvent` for 90 days (`EVENT_LOG_RETENTION_DAYS`), long enough for "what
  happened last quarter", and to show which consumers processed each logged event;
- published outbox rows for only 7 days (`test_purge_keeps_the_explorer_history_for_90_days_and_the_outbox_for_7`).

## Sources

- [backend/apps/staff/](../../backend/apps/staff/) (permissions, services, serializers, views, urls), [backend/apps/events/consumers/event_log.py](../../backend/apps/events/consumers/event_log.py), [backend/apps/events/models.py](../../backend/apps/events/models.py) (`EventLog`, `DeadLetterRetry`)
- [frontend/src/app/staff/](../../frontend/src/app/staff/), [frontend/src/components/staff/](../../frontend/src/components/staff/), [frontend/src/lib/staff-params.ts](../../frontend/src/lib/staff-params.ts), [frontend/src/lib/api/server.ts](../../frontend/src/lib/api/server.ts) (staff fetchers: 404 → `null` → `notFound()`)
- Tests: [test_staff_explorer.py](../../backend/tests/test_staff_explorer.py), [retry-dead-letter.test.tsx](../../frontend/src/components/staff/retry-dead-letter.test.tsx), [document-title.test.tsx](../../frontend/src/components/staff/document-title.test.tsx), [e2e/staff-title.spec.ts](../../frontend/e2e/staff-title.spec.ts)
