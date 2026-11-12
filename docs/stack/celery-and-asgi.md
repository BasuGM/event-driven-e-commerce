# Celery (with beat) and uvicorn / ASGI

Two ways the backend does work outside a normal request. Celery runs background tasks and
scheduled jobs; uvicorn serves the one async endpoint (SSE) so open connections stay cheap.
Celery 5.6.3 (`celery[redis]`), uvicorn 0.54.0. Official docs:
[docs.celeryq.dev](https://docs.celeryq.dev/en/stable/), [uvicorn.org](https://www.uvicorn.org/).

## The Celery app, configured from Django settings

All `CELERY_*` Django settings configure the app; `autodiscover_tasks()` finds `tasks.py` in each
installed app. Importing the app in `config/__init__.py` makes `@shared_task` bind to it.

```python
app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

Source: [config/celery.py](../../backend/config/celery.py).

## Redis as the broker; results ignored

Tasks travel through Redis. Return values aren't stored (`CELERY_TASK_IGNORE_RESULT`): nothing
waits for them.

```python
CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_TIMEZONE = "UTC"
```

Source: [settings/base.py](../../backend/config/settings/base.py). More: [redis.md](redis.md).

## Worker and beat processes

The worker runs tasks; beat is a separate scheduler process that only enqueues them. Both are
compose services built from the backend image. Beat remembers its last-run times in a file on a
volume, so a restart doesn't forget them.

```yaml
command: celery -A config worker -l info --concurrency 2
…
command: celery -A config beat -l info -s /var/lib/celerybeat/schedule
```

Source: [docker-compose.yml](../../docker-compose.yml), services `worker` and `beat`.

## Defining a task

`@shared_task` turns a function into a task without importing the app object, so any Django app
can define them. The beat-driven sweeper is plain Python that loops in batches.

```python
@shared_task
def release_expired_reservations() -> int:
    """Beat runs this every minute. Loops in batches until nothing expired is left."""
    total = 0
    while released := release_expired(limit=100):
        total += released
        if released < 100:
            break
```

Source: [orders/tasks.py](../../backend/apps/orders/tasks.py), `release_expired_reservations`.

## Enqueueing: `.delay()` and `.apply_async()`

`.delay(args)` is shorthand for `.apply_async(args)`, which also accepts options such as a
`countdown` (seconds to wait). The fake provider uses the countdown to deliver webhooks late or
out of order.

```python
deliver_event.apply_async((delivery.event_id,), countdown=delivery.countdown)
```

Source: [fake_provider/provider.py](../../backend/apps/fake_provider/provider.py), `schedule`.

## Enqueue only after the database commits

A task started inside a transaction might run before the row it needs is visible. Enqueueing from
`transaction.on_commit` avoids that. `robust=True` logs a broker failure instead of raising, since
a beat job re-finds anything whose enqueue was lost.

```python
transaction.on_commit(lambda: _enqueue(notification.pk), robust=True)
…
# If the broker is down this raises (robust=True logs it): the beat sweep sends it later
send_notification.delay(notification_id)
```

Source: [events/consumers/notifications.py](../../backend/apps/events/consumers/notifications.py).
More: [notifications](../flows/notifications.md).

## Beat schedule: intervals and crontabs

Frequent jobs use a number of seconds. Daily jobs use `crontab` at a fixed UTC time: a 24-hour
interval counts from beat's start, so a beat restarted more often than daily would never run it.

```python
CELERY_BEAT_SCHEDULE = {
    "release-expired-reservations": {
        "task": "apps.orders.tasks.release_expired_reservations",
        "schedule": 60.0,
    },
    …
    "purge-old-events": {
        "task": "apps.events.tasks.purge_old_events",
        "schedule": crontab(hour=3, minute=0),
    },
}
```

Source: [settings/base.py](../../backend/config/settings/base.py), `CELERY_BEAT_SCHEDULE`.

## Task retries with backoff

`bind=True` gives the task `self`; `self.retry(countdown=…)` re-enqueues it with a delay. The
fake provider's webhook delivery doubles the wait per retry, capped at five minutes, like a real
provider.

```python
@shared_task(bind=True, max_retries=MAX_RETRIES)
def deliver_event(self, event_id: str) -> int:
    status = deliver(FakeEvent.objects.get(pk=event_id))
    if not 200 <= status < 300:
        countdown = min(300, 5 * 2**self.request.retries)
        raise self.retry(countdown=countdown)
```

Source: [fake_provider/tasks.py](../../backend/apps/fake_provider/tasks.py), `deliver_event`.
More: [retries-backoff-and-dead-letters](../concepts/retries-backoff-and-dead-letters.md).

## Retries kept in the database, tasks that are safe to repeat

Email retries don't use Celery's retry: the schedule lives in the `Notification` row (attempts,
`next_attempt_at`), and a beat task sweeps what is due. That survives a lost task and makes
"run it twice" harmless.

```python
delay = min(MAX_BACKOFF, BASE_BACKOFF * 2 ** (notification.attempts - 1))
notification.next_attempt_at = now + timedelta(seconds=delay)
```

```python
@shared_task
def send_due_notifications() -> dict[str, int]:
    """Beat, every 30 s: retries, and anything whose enqueue was lost."""
    return send_due()
```

Source: [notifications/sender.py](../../backend/apps/notifications/sender.py);
[notifications/tasks.py](../../backend/apps/notifications/tasks.py).

## Idempotent tasks with `SKIP LOCKED`

The sweeper handles each order in its own transaction and skips rows another process holds, so
two sweepers (or a sweeper and a payment) never fight and running it twice is safe.

```python
for order_id in candidates:
    with transaction.atomic():
        order = lock_order(order_id, skip_locked=True)
        if order is None or order.status != Order.Status.CREATED:
            continue
```

Source: [orders/services.py](../../backend/apps/orders/services.py), `release_expired`. More:
[row-locks-and-skip-locked](../concepts/row-locks-and-skip-locked.md).

## Tests: in-memory broker and eager calls

Test settings use `memory://` so nothing reaches Redis; a test can run a task inline with
`.apply(...)`, retries included.

```python
CELERY_BROKER_URL = "memory://"
```

```python
result = deliver_event.apply(args=(event.pk,))  # eager: retries run inline
```

Source: [settings/test.py](../../backend/config/settings/test.py);
[tests/test_payments_flow.py](../../backend/tests/test_payments_flow.py).

## uvicorn: a second server for the same code

`stream` is a compose service running the same Django project under uvicorn. `--reload` suits
dev; `--timeout-graceful-shutdown` bounds how long open streams delay a restart. The rest of the
API stays on WSGI (`runserver`), because on ASGI sync views would share one thread.

```yaml
command: >-
  uvicorn config.asgi:application --host 0.0.0.0 --port 8001
  --reload --timeout-graceful-shutdown 5
```

Source: [docker-compose.yml](../../docker-compose.yml), service `stream`.

## The ASGI entry point

```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()
```

Source: [config/asgi.py](../../backend/config/asgi.py). Django-side details (async views,
`sync_to_async`) are in [django.md](django.md#asgi-and-async-views).

## Server-Sent Events as an async generator

An SSE response is a never-ending `text/event-stream`. The async generator yields chunks and
awaits Redis messages in between; a heartbeat comment every 15 s keeps proxies from timing the
connection out, and `finally` cleans up on every exit, including a client disconnect.

```python
response = StreamingHttpResponse(
    event_stream(user, order_id, request.headers.get("Last-Event-ID")),
    content_type="text/event-stream",
)
response["Cache-Control"] = "no-cache, no-transform"
response["X-Accel-Buffering"] = "no"
```

Source: [orders/stream.py](../../backend/apps/orders/stream.py), `order_stream`. More:
[live-tracking](../flows/live-tracking.md), [ADR 0007](../adr/0007-sse-signal-plus-snapshot.md),
[python.md](python.md#asyncio-and-async-generators).

## Not used here

- Celery result backend, task chains/groups/chords, task routing and multiple queues, Flower:
  one default queue, fire-and-forget tasks.
- `autoretry_for` / `retry_backoff`: retries are explicit (`self.retry`, or rows in the database).
- gunicorn or a production ASGI/WSGI setup: dev servers only (listed under "Before deploying" in
  `CLAUDE.md`).
- WebSockets (out of scope; SSE is enough for one-way updates).
