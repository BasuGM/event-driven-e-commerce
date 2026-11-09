# 0001. Redis Streams over Kafka

- **Status:** Accepted
- **Date:** 2026-10-09 (in the stack from commit `a964108`, Step 1; implemented in `b633ef4`, Step 4)

## Context

The order flow publishes domain events, and several independent consumers react to them. The
transport has to provide:
- durable delivery that survives a consumer being down;
- independent consumer groups that each see every event;
- per-consumer acknowledgement and redelivery of unacknowledged work;
- somewhere to put events that keep failing.

The project runs on one laptop through Docker Compose, and Redis is already in the stack as the
Celery broker.

## Options considered

1. **Kafka.** The industry standard for event streaming: partitioned, replicated, long retention,
   per-partition ordering. It's another distributed system to run (brokers, plus ZooKeeper or
   KRaft). CLAUDE.md lists it as out of scope: "Redis Streams covers the concepts".
2. **RabbitMQ.** A queue broker. It has no replayable log, so a new consumer couldn't process
   history.
3. **Redis Pub/Sub.** Fire-and-forget: a subscriber that's away misses messages. It's used only
   for live-update *signals*, never for events ([0007](0007-sse-signal-plus-snapshot.md)).
4. **Redis Streams.** An append-only log per stream, with:
   - consumer groups (`XREADGROUP`), a pending-entries list, and `XACK`;
   - reclaiming stuck work (`XAUTOCLAIM`);
   - approximate trimming (`MAXLEN ~`).

## Decision

Redis Streams: one stream per aggregate type (`events:order`, `events:product`), one consumer
group per consumer, and a dead-letter stream `events:dlq`.

Why:
- **Redis was already in the stack**, as the Celery broker and for Pub/Sub.
- **Streams provide everything this project needs:** consumer groups, acknowledgements, a pending
  list, and replay.
- **Kafka would add a cluster to operate** for no benefit at this scale.

**What would trigger a move to Kafka:**
- many independent teams consuming the events;
- long retention requirements;
- throughput that needs partitioning.

## Consequences

- **Gained, with no new infrastructure:** consumer groups, redelivery, reclaiming, and
  dead-lettering, all built on primitives Redis already has.
- **Durability depends on Redis persistence.** It uses AOF with `appendfsync everysec`, so a hard
  crash can lose up to about 1 s of entries that the outbox already marked published.
- **Retention is bounded by memory.** Streams are trimmed to about 100,000 entries, so a group
  lagging further than that would miss events. There's no Kafka-style long retention for
  replaying months of history; [0014](0014-replay-through-real-services.md) re-creates history
  through the services instead.
- **No partitions.** Throughput scales with consumer threads and relay instances, not with
  partitions. There's also no ordering guarantee once more than one relay runs or entries are
  reclaimed, so handlers must be state-based ([0003](0003-state-based-idempotent-consumers.md)).
- **One Redis instance** serves Celery, streams and Pub/Sub. That's simple here, and a single
  point of failure at scale.

## Links

- [docs/flows/event-pipeline.md](../flows/event-pipeline.md), [docs/limitations-and-roadmap.md](../limitations-and-roadmap.md)
- [backend/apps/events/streams.py](../../backend/apps/events/streams.py), [backend/apps/events/consumer.py](../../backend/apps/events/consumer.py), [docker-compose.yml](../../docker-compose.yml) (`redis`)
