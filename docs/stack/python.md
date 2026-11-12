# Python

The language of the whole backend. Python 3.13 (image `python:3.13-slim`). This page lists only
the language and standard-library features the code actually uses. Official docs:
[docs.python.org/3.13](https://docs.python.org/3.13/).

## f-strings

Formatted string literals: expressions inside `{}`, with format specs after a colon.

```python
return f"{self.external_id[:8]} ({self.city}/{self.state})"
```

Source: [customers/models.py](../../backend/apps/customers/models.py), `Customer.__str__`.

## Type hints and `X | None`

Annotations document signatures for readers and editors; nothing checks them. `X | None`
is the modern spelling of "optional". `from __future__ import annotations` (at the top of many
modules) defers evaluating annotations.

```python
def lock_order(order_id: int, *, skip_locked: bool = False) -> Order | None:
```

Source: [orders/services.py](../../backend/apps/orders/services.py), `lock_order`.

## Keyword-only arguments

Parameters after a bare `*` must be passed by name, so a call reads clearly
(`lock_order(id, skip_locked=True)`) and a flag can't be swapped by position.

```python
def record_event(
    event_type: str, aggregate_type: str, aggregate_id: str, payload: dict, *, schema_version: int = 1
) -> OutboxEvent:
```

Source: [events/outbox.py](../../backend/apps/events/outbox.py), `record_event`.

## Comprehensions and the walrus operator

Comprehensions build lists and dicts in one expression; `:=` assigns inside a condition. The
catalog filter uses it to test and name a query parameter at once.

```python
if slug := params.get("category"):
    queryset = queryset.filter(category__slug=slug)
if (low := params.get("min_price")) is not None:
    queryset = queryset.filter(min_price__gte=low)
```

Source: [catalog/filters.py](../../backend/apps/catalog/filters.py), `filter_products`.

## `@property`

A method read like an attribute: derived values on a model without storing them.

```python
@property
def overdue_at(self):
    """When "processing" stops blocking Pay (the webhook may never come)."""
    if self.status != self.Status.PROCESSING or self.returned_at is None:
        return None
    return self.returned_at + timedelta(seconds=settings.PAYMENT_CONFIRMATION_TIMEOUT_SECONDS)
```

Source: [payments/models.py](../../backend/apps/payments/models.py), `PaymentIntent.overdue_at`.

## Exceptions as domain errors

Services raise plain exception classes; a single DRF exception handler maps them to HTTP. The
hierarchy carries the status code and a machine-readable `code`.

```python
class DomainError(Exception):
    status_code = 409
    code = "conflict"
    …

class OutOfStock(DomainError):
    code = "out_of_stock"
```

Source: [core/errors.py](../../backend/apps/core/errors.py), `DomainError`. More:
[state-machines](../concepts/state-machines.md).

## `@dataclass`

Generates `__init__`, `__eq__` and `__repr__` from annotated fields. `frozen=True` makes
instances immutable; `field(default_factory=…)` is for mutable defaults. Used for value objects
passed between layers.

```python
@dataclass(frozen=True)
class WebhookEvent:
    id: str
    type: str
    created: datetime
    …
    payload: dict = field(default_factory=dict)
```

Source: [payments/gateway.py](../../backend/apps/payments/gateway.py), `WebhookEvent`.

## `typing.Protocol`

A structural interface: any class with the right methods qualifies, no inheritance needed. The
payment provider is swapped by writing another class with the same shape.

```python
class PaymentGateway(Protocol):
    name: str
    …
```

Source: [payments/gateway.py](../../backend/apps/payments/gateway.py), `PaymentGateway`. More:
[ADR 0005](../adr/0005-fake-payment-provider.md).

## `collections.Counter`

A dict that counts. The importer tallies skipped rows by reason, then reports them.

```python
skipped: Counter = field(default_factory=Counter)  # rows not imported, by reason
notes: Counter = field(default_factory=Counter)  # rows imported with a caveat
```

Source: [core/olist_import.py](../../backend/apps/core/olist_import.py), `TableResult`.

## Reading CSV with `csv.DictReader`

Each row becomes a dict keyed by the header. `utf-8-sig` strips the byte-order mark one Olist
file carries; `newline=""` is what the `csv` module expects.

```python
with path.open(newline="", encoding="utf-8-sig") as fh:
    rows = [row for row in csv.DictReader(fh) if keep is None or keep(row)]
```

Source: [core/olist_import.py](../../backend/apps/core/olist_import.py), `_read`. More:
[olist-import](../flows/olist-import.md).

## `decimal.Decimal` for money

Exact decimal arithmetic. Constructors take strings, never floats; `quantize` with
`ROUND_HALF_UP` rounds to cents the way people expect.

```python
amount = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

Source: [core/formatting.py](../../backend/apps/core/formatting.py), `format_brl`. More:
[money-as-decimals](../concepts/money-as-decimals.md).

## `zoneinfo` and timezone-aware datetimes

Olist timestamps are Brazil local time; the importer attaches the zone, Django stores UTC, and
analytics converts back to Sao Paulo to decide which day an order belongs to.

```python
SOURCE_TZ = ZoneInfo("America/Sao_Paulo")
```

```python
def local_day(moment: datetime) -> date:
    return moment.astimezone(ZoneInfo(settings.ANALYTICS_TIMEZONE)).date()
```

Source: [core/olist_import.py](../../backend/apps/core/olist_import.py);
[analytics/projections.py](../../backend/apps/analytics/projections.py), `local_day`.

## `hashlib` for deterministic data

The product name generator seeds a random generator from a SHA-256 of the product's external ID,
so the same product always gets the same name and slug. (Synthetic *stock* is different: it is
computed in SQL with `md5`, see [postgresql.md](postgresql.md).)

```python
digest = hashlib.sha256(external_id.encode()).digest()
return random.Random(int.from_bytes(digest[:8], "big"))
```

Source: [catalog/enrichment.py](../../backend/apps/catalog/enrichment.py), `_rng`.

## `hmac` and constant-time comparison

Webhook signatures are an HMAC-SHA256 of `"<t>." + raw body`. `compare_digest` takes the same
time however many characters match, so it leaks nothing to an attacker timing guesses.

```python
return hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
…
if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
```

Source: [payments/signature.py](../../backend/apps/payments/signature.py), `compute` and `verify`.
More: [payments](../flows/payments.md).

## `logging`

One logger per module, named after it; `%s`-style arguments are formatted only if the record is
emitted.

```python
logger = logging.getLogger(__name__)
…
logger.warning("Fake provider: webhook %s got %s, retrying in %ss", event_id, status, countdown)
```

Source: [fake_provider/tasks.py](../../backend/apps/fake_provider/tasks.py), `deliver_event`.

## Threads and `threading.Event` as a stop flag

`run_consumers` starts one thread per consumer; a shared `Event` tells them all to stop. Each
thread closes its own database connection when it ends.

```python
threads = [
    threading.Thread(target=self._run, args=(CONSUMERS[name], stop), name=name, daemon=True)
    for name in names
]
```

Source: [run_consumers.py](../../backend/apps/events/management/commands/run_consumers.py),
`Command.handle`.

## Signal handling

SIGINT/SIGTERM handlers set the stop flag instead of killing the process, so the current step
finishes and the run is saved as `interrupted`. A second Ctrl-C restores the default and aborts.

```python
def request_stop(signum, frame):
    self.stdout.write("\nStopping after the current step (Ctrl-C again to abort hard)...")
    stop.set()
    signal.signal(signal.SIGINT, signal.default_int_handler)

previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
```

Source: [replay_orders.py](../../backend/apps/replay/management/commands/replay_orders.py),
`Command.handle`. More: [replay](../flows/replay.md).

## `asyncio` and async generators

The SSE view is an `async def` generator that yields text chunks, awaiting Redis messages. While
it waits, the event loop serves other connections, so an open stream costs a coroutine, not a
thread.

```python
async def event_stream(user, order_id: str, last_event_id: str | None) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.ORDER_STREAM_MAX_SECONDS
    …
    yield f"retry: {settings.ORDER_STREAM_RETRY_MS}\n\n"
```

Source: [orders/stream.py](../../backend/apps/orders/stream.py), `event_stream`. More:
[celery-and-asgi](celery-and-asgi.md).

## Not used here

- `contextlib.contextmanager`, `functools` (`lru_cache`), custom `Enum` classes: the code uses
  Django's `TextChoices` for enums and plain functions for the rest.
- `pydantic`, `attrs`, `TypedDict`: dataclasses and DRF serializers cover it.
- Type checking (`mypy`/`pyright`): hints are documentation only; there is no type-check step.
- `multiprocessing`: concurrency is processes managed by Compose plus threads in one command.
