# Redis

An in-memory data store, used here for three jobs: the Celery task queue, the durable event
streams, and fire-and-forget Pub/Sub signals. Redis 7 (image `redis:7`) with the redis-py 6.4.0
client (pinned: Celery's transport needs `<6.5`). Official docs: [redis.io/docs](https://redis.io/docs/latest/).

## One server, several uses, separated by key prefix and DB number

Everything shares one Redis. Event streams live under a prefix (`events:order`,
`events:product`, `events:dlq`); tests use another prefix and logical DB 15 so they never touch
dev data.

```python
EVENTS_STREAM_PREFIX = "events"  # streams: events:order, events:product, events:dlq
```

```python
EVENTS_REDIS_URL = os.environ.get("EVENTS_TEST_REDIS_URL", "redis://redis:6379/15")
EVENTS_STREAM_PREFIX = "test-events"
```

Source: [settings/base.py](../../backend/config/settings/base.py) and
[settings/test.py](../../backend/config/settings/test.py).

## Persistence: AOF every second

Streams hold events until consumers acknowledge them, so Redis runs with an append-only file,
flushed every second. A hard crash can lose up to ~1 s of writes (a known issue in `CLAUDE.md`).
The e2e stack turns persistence off.

```yaml
command: ["redis-server", "--appendonly", "yes", "--appendfsync", "everysec"]
```

Source: [docker-compose.yml](../../docker-compose.yml), service `redis`. More:
[ADR 0001](../adr/0001-redis-streams-over-kafka.md).

## Client with timeouts

The relay talks to Redis while holding Postgres row locks, so a hung Redis must fail within
seconds instead of holding them.

```python
return redis.Redis.from_url(
    settings.EVENTS_REDIS_URL,
    socket_connect_timeout=settings.EVENTS_REDIS_CONNECT_TIMEOUT,
    socket_timeout=settings.EVENTS_REDIS_SOCKET_TIMEOUT,
    decode_responses=True,
)
```

Source: [events/streams.py](../../backend/apps/events/streams.py), `redis_client`.

## Celery broker

The task queue for Celery is just a Redis URL.

```python
CELERY_BROKER_URL = REDIS_URL
```

Source: [settings/base.py](../../backend/config/settings/base.py). More:
[celery-and-asgi](celery-and-asgi.md).

## Streams: `XADD`

A stream is an append-only log. The relay adds each outbox row as an entry; `MAXLEN ~` trims the
log approximately (cheap) so it can't grow forever.

```python
client.xadd(
    stream_name(row.aggregate_type),
    entry_fields(row),
    maxlen=settings.EVENTS_STREAM_MAXLEN,
    approximate=True,
)
```

Source: [events/relay.py](../../backend/apps/events/relay.py), `publish_batch`. More:
[redis-streams-and-pubsub](../concepts/redis-streams-and-pubsub.md),
[transactional-outbox](../concepts/transactional-outbox.md).

## Consumer groups: `XGROUP CREATE`

A group tracks, per stream, which entries each of its consumers has been given. Each consumer
here is its own group, so every consumer sees every event. `BUSYGROUP` just means "already
exists".

```python
try:
    self.client.xgroup_create(key, self.name, id="0", mkstream=True)
except redis.ResponseError as exc:
    if "BUSYGROUP" not in str(exc):
        raise
```

Source: [events/consumer.py](../../backend/apps/events/consumer.py), `ensure_groups`.

## Reading as a group: `XREADGROUP` and `XACK`

`>` asks for entries never delivered to this group. An entry stays *pending* until acknowledged,
and the consumer acks only after its database transaction commits, which is what makes delivery
at-least-once.

```python
response = self.client.xreadgroup(
    self.name,
    self.me,
    {key: ">" for key in self.stream_keys},
    count=READ_COUNT,
    block=settings.EVENTS_BLOCK_MS if block_ms is None else block_ms,
)
```

Source: [events/consumer.py](../../backend/apps/events/consumer.py), `run_once`. More:
[delivery-guarantees](../concepts/delivery-guarantees.md),
[state-based-vs-delta-handlers](../concepts/state-based-vs-delta-handlers.md).

## Reclaiming stuck entries: `XAUTOCLAIM`

If a consumer dies after reading but before acking, its pending entries go idle. Another
consumer claims entries idle longer than a threshold and retries them.

```python
result = self.client.xautoclaim(
    key, self.name, self.me,
    min_idle_time=settings.EVENTS_CLAIM_IDLE_MS, start_id=start, count=READ_COUNT,
)
```

Source: [events/consumer.py](../../backend/apps/events/consumer.py), `_reclaim`. More:
[retries-backoff-and-dead-letters](../concepts/retries-backoff-and-dead-letters.md).

## Dead-letter stream

After `EVENTS_MAX_DELIVERIES` failed deliveries, the entry is copied to `events:dlq` with the
error and acknowledged, so one poison event can't block the stream. Staff can retry it later.

```python
{
    **fields,
    "dlq_consumer": self.name,
    "dlq_stream": key,
    "dlq_entry_id": entry_id,
    "dlq_deliveries": str(deliveries),
    "dlq_error": error,
},
```

Source: [events/consumer.py](../../backend/apps/events/consumer.py), `_dead_letter`. More:
[event-pipeline](../flows/event-pipeline.md), [staff-tools](../flows/staff-tools.md).

## Inspecting groups: `XINFO GROUPS`

The staff health page reads pending counts and lag straight from Redis. A missing stream raises
`ResponseError`, which is shown as "no group yet".

```python
for key in {k for k, _ in expected}:
    try:
        infos[key] = {g["name"]: g for g in client.xinfo_groups(key)}
    except redis.ResponseError:  # the stream doesn't exist yet
        infos[key] = {}
```

Source: [staff/services.py](../../backend/apps/staff/services.py), `group_health`.

## Pub/Sub for live signals

`PUBLISH` sends a message to whoever is subscribed right now; nobody subscribed means it is
dropped. That is acceptable here: the message carries no state, and the SSE stream re-reads the
order from Postgres whenever any signal (or reconnect, or timeout) arrives.

```python
def publish_order_signal(order_id: str, token: str = "") -> int:
    try:
        return redis_client().publish(channel_name(order_id), token)
    except Exception:  # noqa: BLE001 - a missed signal only delays an update
        …
```

```python
pubsub = client.pubsub(ignore_subscribe_messages=True)
await pubsub.subscribe(channel_name(order_id))
```

Source: [orders/live.py](../../backend/apps/orders/live.py), `publish_order_signal`;
[orders/stream.py](../../backend/apps/orders/stream.py), `event_stream` (async client).
More: [live-tracking](../flows/live-tracking.md), [ADR 0007](../adr/0007-sse-signal-plus-snapshot.md).

## Deleting by pattern with `SCAN`

`SCAN` walks the keyspace in small steps (unlike `KEYS`, it doesn't block the server). `make reset`
uses it to drop only the event streams, leaving Celery's keys in the same Redis DB alone.

```python
keys = list(client.scan_iter(match=f"{settings.EVENTS_STREAM_PREFIX}:*", _type="stream"))
if keys:
    client.delete(*keys)
```

Source: [clear_event_streams.py](../../backend/apps/events/management/commands/clear_event_streams.py),
`Command.handle`.

## Healthcheck

```yaml
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
```

Source: [docker-compose.yml](../../docker-compose.yml), service `redis`.

## Not used here

- Redis as a cache (Django's cache framework is unused; Next caches pages itself).
- Lists, sets, sorted sets, hashes, locks (`SET NX`) and Lua scripts: the project's coordination
  uses Postgres locks instead.
- Redis Cluster / Sentinel, ACLs, TLS: single dev instance.
