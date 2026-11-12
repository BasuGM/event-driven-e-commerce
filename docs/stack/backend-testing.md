# Backend testing: pytest and pytest-django

pytest finds and runs `test_*` functions with plain `assert`; pytest-django adds database access,
Django settings and Django-aware fixtures. pytest 9.1.1, pytest-django 4.14.0. Run with
`make test-backend`. Official docs: [docs.pytest.org](https://docs.pytest.org/),
[pytest-django.readthedocs.io](https://pytest-django.readthedocs.io/).

## `pytest.ini`: settings, strict markers, test paths

`--ds` forces the test settings module (it beats `DJANGO_SETTINGS_MODULE` from `.env`);
`--strict-markers` makes a misspelled marker an error.

```ini
[pytest]
python_files = test_*.py
testpaths = tests
addopts = -ra --strict-markers --ds=config.settings.test
```

Source: [backend/pytest.ini](../../backend/pytest.ini). A test asserts it holds:
[tests/test_settings.py](../../backend/tests/test_settings.py), `test_tests_run_with_test_settings`.

## Plain tests with `assert`

No test classes or `self.assertEqual`: a function and an `assert`. pytest rewrites the assert to
show both sides on failure.

```python
def test_a_valid_signature_returns_its_timestamp():
    now = time.time()
    header = sign(SECRET, BODY, timestamp=int(now))
    assert verify(header, BODY, SECRET, tolerance=300, now=now) == int(now)
```

Source: [tests/test_payments_signature.py](../../backend/tests/test_payments_signature.py).

## Database access: `django_db`

A test that touches the database needs the `django_db` mark. By default each test runs inside a
transaction that is rolled back at the end, so tests don't leak rows into each other. A module
can mark every test at once with `pytestmark`.

```python
pytestmark = pytest.mark.django_db
```

Source: [tests/test_catalog_api.py](../../backend/tests/test_catalog_api.py).

## Fixtures

A `@pytest.fixture` function provides a value to any test that names it as a parameter. The
shared ones live in `conftest.py`. Factory fixtures return a function, so a test can build as
many objects as it needs with its own arguments.

```python
@pytest.fixture
def make_user(db):
    def make(email=None, password="s3cret-pass-123", name="Ana Souza"):
        email = email or f"user{next(_seq)}@example.com"
        …
        return get_user_model().objects.create_user(
            username=email, email=email, password=password, first_name=first, last_name=last
        )

    return make
```

Source: [tests/conftest.py](../../backend/tests/conftest.py), `make_user` (the built-in `db`
fixture enables database access).

## Fixtures that wrap setup and teardown

Code before `yield` is setup, code after is teardown. The Redis fixture clears every key under
the test prefix before and after each test, so stream and group state never leaks.

```python
@pytest.fixture
def events_redis(settings):
    client = redis_client()
    def clear():
        keys = list(client.scan_iter(f"{settings.EVENTS_STREAM_PREFIX}:*"))
        if keys:
            client.delete(*keys)

    clear()
    yield client
    clear()
```

Source: [tests/conftest.py](../../backend/tests/conftest.py), `events_redis`. The `settings`
fixture is pytest-django's: a view of Django settings that is reset after each test.

## `parametrize`: one test, many cases

One function runs once per row, each reported separately. The signature tests list every way a
webhook can be wrong.

```python
@pytest.mark.parametrize(
    "header, body, secret, age",
    [
        ("valid", BODY + b" ", SECRET, 0),  # even whitespace: the HMAC is over the raw bytes
        ("valid", BODY, SECRET, 301),  # outside the tolerance
        …
    ],
)
def test_rejects_anything_not_signed_by_us_just_now(header, body, secret, age):
```

Source: [tests/test_payments_signature.py](../../backend/tests/test_payments_signature.py).

## `pytest.raises`

Asserts that code raises, optionally matching the message.

```python
with pytest.raises(InvalidSignature, match="^invalid signature$"):
    verify(header, body, secret, tolerance=300)
```

Source: [tests/test_payments_signature.py](../../backend/tests/test_payments_signature.py).

## Testing the API with `APIClient`

DRF's test client makes requests without a network. `force_login` signs a user in without going
through the login view (CSRF isn't enforced for it; the auth tests check CSRF separately).

```python
@pytest.fixture
def api_client():
    return APIClient()
```

```python
data = api_client.get("/api/categories/").json()
by_slug = {c["slug"]: c for c in data}
```

Source: [tests/conftest.py](../../backend/tests/conftest.py), `api_client`;
[tests/test_catalog_api.py](../../backend/tests/test_catalog_api.py),
`test_categories_only_lists_categories_with_products`.

## Pinning query counts: `django_assert_num_queries`

The four catalog endpoints have exact-count tests (`django_assert_num_queries`); the cart, order
list and order detail endpoints have upper-bound tests (`django_assert_max_num_queries`). Staff
endpoints have none yet. A changed count catches N+1 regressions the moment someone drops a
`select_related`. The pinned list is in [api.md](../api.md).

```python
def test_list_query_count(api_client, catalog, django_assert_num_queries):
    with django_assert_num_queries(2):  # count + page (category via JOIN)
        api_client.get("/api/products/", {"page_size": 100})
```

Source: [tests/test_catalog_api.py](../../backend/tests/test_catalog_api.py), `test_list_query_count`.

## Running management commands: `call_command`

Seed data and the importer are tested by running the real command against tiny CSVs in
`tests/fixtures/olist/` (including deliberately messy rows).

```python
@pytest.fixture
def catalog(olist_dir):
    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=StringIO())
```

Source: [tests/test_catalog_api.py](../../backend/tests/test_catalog_api.py), `catalog`. More:
[olist-import](../flows/olist-import.md).

## `monkeypatch`, `mock` and `caplog`

`monkeypatch` swaps an attribute for one test and restores it after; `unittest.mock.patch.object`
replaces a function with a stub; `caplog` captures log records for assertions.

```python
def test_waits_logging_once_then_starts(caplog, monkeypatch):
    monkeypatch.setattr(readiness, "POLL_SECONDS", 0)
    checks = iter([{"events_outboxevent"}] * 4 + [set()])
    with mock.patch.object(readiness, "missing_event_tables", side_effect=lambda: next(checks)):
        with caplog.at_level(logging.INFO, logger="apps.events.readiness"):
```

Source: [tests/test_events_readiness.py](../../backend/tests/test_events_readiness.py),
`test_waits_logging_once_then_starts`.

## Real concurrency: `transaction=True` and threads

The default test transaction hides other connections' view of the data. For races (two buyers,
one last unit) `django_db(transaction=True)` commits for real and truncates tables afterwards;
the test starts threads at the same instant with a `Barrier`, each with its own connection.

```python
pytestmark = pytest.mark.django_db(transaction=True)

def run_concurrently(*functions):
    barrier = threading.Barrier(len(functions))
    …
    for thread in threads:
        thread.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a thread hung (deadlock?)"
```

Source: [tests/test_concurrency.py](../../backend/tests/test_concurrency.py), `run_concurrently`.
More: [row-locks-and-skip-locked](../concepts/row-locks-and-skip-locked.md),
[lock-ordering-and-deadlocks](../concepts/lock-ordering-and-deadlocks.md).

## Testing "must be inside a transaction" rules

A rule such as "state changes need an open transaction" can't be tested inside pytest-django's
default test transaction, which is itself a transaction; the test opts out.

```python
@pytest.mark.django_db(transaction=True)  # the default test wrapper is itself a transaction
def test_transition_outside_a_transaction_is_refused(order):
    with pytest.raises(RuntimeError):
        transition(order, S.APPROVED, "test")
```

Source: [tests/test_state_machine.py](../../backend/tests/test_state_machine.py),
`test_transition_outside_a_transaction_is_refused`. More: [state-machines](../concepts/state-machines.md).

## Simulating failure mid-operation

Race and recovery tests patch a step so another actor "takes over" at a precise moment, then
assert what was and wasn't written.

```python
monkeypatch.setattr(services, "HEARTBEAT_SECONDS", 0.0)  # heartbeat before every step
…
runner = services.Runner(run, plan, on_step=taken_over_after_five)
run = runner.execute()

assert runner.taken_over
assert replay_events().count() == 5  # nothing after the takeover
```

Source: [tests/test_replay.py](../../backend/tests/test_replay.py),
`test_a_taken_over_run_stops_without_writing_further_steps`. More: [replay](../flows/replay.md).

## Real services in tests; no mocks at the boundaries

Tests use the real Postgres, the real Redis (DB 15, `test-events:` prefix) and Celery's in-memory
broker, so locking, constraints and stream behaviour are exercised for real. Eager task runs use
`.apply(...)`.

```python
EVENTS_REDIS_URL = os.environ.get("EVENTS_TEST_REDIS_URL", "redis://redis:6379/15")
EVENTS_STREAM_PREFIX = "test-events"
```

Source: [config/settings/test.py](../../backend/config/settings/test.py). More:
[testing](../testing.md), [celery-and-asgi.md](celery-and-asgi.md#tests-in-memory-broker-and-eager-calls).

## Not used here

- Test classes and `unittest.TestCase`, `factory_boy`/`model_bakery` (factory fixtures in
  `conftest.py` instead), `pytest-xdist` (tests share one database and one Redis DB),
  `pytest-cov`.
- `freezegun`/`time-machine`: tests pass `now=` into the code instead of freezing the clock.
- Mutation or property-based tests (hypothesis).
