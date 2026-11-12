# Django

The Python web framework the backend is built on: ORM, migrations, auth, sessions, admin,
templates, mail, and (for SSE) its ASGI support. Django 6.1.2. Official docs:
[docs.djangoproject.com](https://docs.djangoproject.com/en/6.1/).

## Settings split per environment

`base.py` holds shared settings; `dev.py` and `test.py` import it and override a few values.
`DJANGO_SETTINGS_MODULE` picks one. Dev-only switches (`ALLOW_DEV_SEED`, `ALLOW_FAKE_PAYMENTS`)
exist only in those two files.

```python
from .base import *  # noqa: F403

DEBUG = True
# Dev-only accounts (admin / staff / customer) may be seeded in this environment.
ALLOW_DEV_SEED = True
```

Source: [settings/dev.py](../../backend/config/settings/dev.py).

## Apps

A Django "app" is a package of models, views and commands. Each domain area has one, registered
in `INSTALLED_APPS` by its dotted path.

```python
INSTALLED_APPS = [
    …
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "apps.accounts",
    "apps.core",
    "apps.catalog",
    …
]
```

Source: [settings/base.py](../../backend/config/settings/base.py), `INSTALLED_APPS`.

## Models and `TextChoices`

A model class is a table. `TextChoices` gives a status field named, validated values that also
work as constants in code (`FakeIntent.Status.SUCCEEDED`).

```python
class FakeIntent(models.Model):
    class Status(models.TextChoices):
        REQUIRES_PAYMENT = "requires_payment"
        SUCCEEDED = "succeeded"
        …
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUIRES_PAYMENT)
```

Source: [fake_provider/models.py](../../backend/apps/fake_provider/models.py), `FakeIntent`.
Constraints and indexes on `Meta` are covered in [postgresql.md](postgresql.md).

## Custom user model

Set at the start of the project (`AUTH_USER_MODEL = accounts.User`) because it can't be swapped
later. It extends `AbstractUser` and adds a case-insensitive unique email via a functional
constraint.

```python
class User(AbstractUser):
    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"), condition=~models.Q(email=""), name="uniq_user_email_ci"
            )
        ]
```

Source: [accounts/models.py](../../backend/apps/accounts/models.py), `User`.

## Migrations

Schema changes are migration files, never edited once applied. Adding a required column to a
populated table is three steps: add it nullable, backfill, then enforce in a later migration.
The backfill uses `RunPython` with the *historical* models (`apps.get_model`), not imports.

```python
def backfill(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")
    …
migrations.RunPython(backfill, migrations.RunPython.noop),
```

Source: [catalog/migrations/0002_enrichment_fields_and_offer.py](../../backend/apps/catalog/migrations/0002_enrichment_fields_and_offer.py),
`backfill`.

## Queries that stay constant: `select_related` and `prefetch_related`

`select_related` joins a forward foreign key into the same query; `prefetch_related` runs one
extra query for the related rows. `Prefetch` customises that extra query. The catalog,
cart and order endpoints have query-count tests (the staff endpoints don't yet; see
[api.md](../api.md)).

```python
queryset = Product.objects.select_related("category").prefetch_related(
    Prefetch("offers", queryset=Offer.objects.select_related("seller").order_by("price", "id"))
)
```

Source: [catalog/views.py](../../backend/apps/catalog/views.py), `ProductDetailView`.

## Aggregates, `annotate`, `Coalesce`, `Subquery`

`annotate` adds computed columns to each row. Here, totals come from aggregates, and the
reservation expiry is a correlated `Subquery` because a second join would multiply item rows and
inflate the sums.

```python
.annotate(
    item_count=Count("items"),
    items_total=Coalesce(Sum("items__price"), ZERO),
    total=F("items_total") + F("freight_total"),
    reservation_expires_at=Subquery(active_expiry),
)
```

Source: [orders/selectors.py](../../backend/apps/orders/selectors.py), `orders_with_totals`.

## `update_or_create`

Look up by the given fields; update the `defaults` if the row exists, create it otherwise. It
makes the dev-account seed safe to re-run.

```python
user, created = User.objects.update_or_create(
    username=username,
    defaults={
        "email": f"{username}@example.com",
        …
        "is_staff": is_staff,
    },
)
```

Source: [seed_dev_users.py](../../backend/apps/core/management/commands/seed_dev_users.py),
`Command.handle`.

## Transactions: `atomic`, `select_for_update`, `on_commit`

`transaction.atomic()` groups writes; `select_for_update()` locks rows (see
[postgresql.md](postgresql.md)); `transaction.on_commit()` runs a callback only after the outer
transaction commits, so a Celery task never starts for data that isn't visible yet.

```python
        intent.save(update_fields=["status"])
        …
        transaction.on_commit(lambda: schedule(deliveries))
```

Source: [fake_provider/provider.py](../../backend/apps/fake_provider/provider.py), the function
that decides a payment. More: [transactions-and-isolation](../concepts/transactions-and-isolation.md),
[transactional-outbox](../concepts/transactional-outbox.md).

## Raw SQL with `connection.cursor()`

For set-based work the ORM would make awkward (projections, stats), the code runs SQL with bound
parameters (`%s`, `%(name)s`) on the connection's cursor, inside `atomic()`.

```python
with transaction.atomic(), connection.cursor() as cursor:
    …
    for table, insert in INSERTS.items():
        cursor.execute(f"DELETE FROM {table} WHERE source = %(source)s AND day = ANY(%(days)s)", params)
```

Source: [analytics/projections.py](../../backend/apps/analytics/projections.py), `recompute_days`
(table names come from a fixed dict, values are always parameters).

## Full-text search helpers

`django.contrib.postgres` supplies `SearchVectorField`, `GinIndex`, `SearchQuery` and
`SearchRank`.

```python
if query is not None:
    queryset = queryset.filter(search_vector=query)
    …
    queryset = queryset.annotate(rank=SearchRank(F("search_vector"), query))
```

Source: [catalog/filters.py](../../backend/apps/catalog/filters.py), `filter_products`. More:
[postgresql.md](postgresql.md#full-text-search).

## Management commands

A class with `handle()` run as `python manage.py <name>`. Seeding, the relay, the consumers, the
importer and the replay are all commands; the dev-only ones refuse to run unless a setting
allows it.

```python
class Command(BaseCommand):
    help = "Create or refresh the dev-only accounts admin / staff / customer / replay."

    def handle(self, *args, **options):
        if not getattr(settings, "ALLOW_DEV_SEED", False):
            raise CommandError("seed_dev_users only runs with dev/test settings (ALLOW_DEV_SEED).")
```

Source: [seed_dev_users.py](../../backend/apps/core/management/commands/seed_dev_users.py).

## Admin

Registering a `ModelAdmin` gives a staff UI for free; `list_display`, `search_fields` and an
annotated queryset (to sort by a computed column) are the features used.

```python
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name_english", "name", "slug", "product_count"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_product_count=Count("products"))
```

Source: [catalog/admin.py](../../backend/apps/catalog/admin.py), `CategoryAdmin`.

## Middleware

Settings list the request/response hooks in order. Sessions, CSRF and auth come from Django's
stock ones.

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    …
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
```

Source: [settings/base.py](../../backend/config/settings/base.py), `MIDDLEWARE`.

## Sessions and CSRF

Auth is session cookies only. `ensure_csrf_cookie` sets the `csrftoken` cookie on a GET; unsafe
requests must send it back as `X-CSRFToken`. DRF's own check only covers *authenticated*
requests, so anonymous login and register are wrapped in `csrf_protect` by hand.

```python
@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
```

Source: [accounts/views.py](../../backend/apps/accounts/views.py), `LoginView`. More:
[auth-and-sessions](../flows/auth-and-sessions.md), [ADR 0004](../adr/0004-sessions-behind-the-next-proxy.md).

## A plain view for raw bodies

The payment webhook is a normal Django view, not DRF: its HMAC covers the exact bytes received,
and DRF would hand back parsed data. `csrf_exempt` is safe because the signature authenticates
the caller.

```python
@csrf_exempt  # authenticated by the HMAC signature instead (no browser, no cookies)
@require_POST
def webhook(request):
    gateway = get_gateway()
    try:
        event = gateway.parse_webhook(request.body, request.headers)
```

Source: [payments/views.py](../../backend/apps/payments/views.py), `webhook`.

## Templates

Emails are rendered with Django's template engine into a text and an HTML body.

```python
render_to_string("notifications/order_email.txt", context),
render_to_string("notifications/order_email.html", context),
```

Source: [notifications/rendering.py](../../backend/apps/notifications/rendering.py), `render`.

## Email and `MAILERS`

Django 6.1's `MAILERS` setting supersedes the `EMAIL_*` settings, which are deprecated but still
work (Django 6.1.2's global settings file marks them for removal in Django 2028). Dev points at the Mailpit
container; tests swap in an in-memory backend. A message is built with
`EmailMultiAlternatives`: text plus an HTML alternative.

```python
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": os.environ.get("EMAIL_HOST", "mailpit"),
            …
        },
    }
}
```

```python
email = EmailMultiAlternatives(
    notification.subject, notification.body_text, settings.DEFAULT_FROM_EMAIL,
    [notification.recipient], headers={"Message-ID": message_id(notification)},
)
email.attach_alternative(notification.body_html, "text/html")
email.send()
```

Source: [settings/base.py](../../backend/config/settings/base.py), `MAILERS`;
[notifications/sender.py](../../backend/apps/notifications/sender.py). More:
[notifications](../flows/notifications.md).

## ASGI and async views

The same project serves SSE from an ASGI entry point. The async view returns a
`StreamingHttpResponse` fed by an async generator. Under WSGI it refuses, because the response
would be buffered whole.

```python
application = get_asgi_application()
```

```python
async def order_stream(request, order_id: str):
    if not isinstance(request, ASGIRequest):
        # Under WSGI an async stream would be buffered whole and hold a worker for minutes
        return JsonResponse({"detail": "Served by the stream service (ASGI)."}, status=404)
```

Source: [config/asgi.py](../../backend/config/asgi.py);
[orders/stream.py](../../backend/apps/orders/stream.py), `order_stream`. More:
[celery-and-asgi](celery-and-asgi.md), [live-tracking](../flows/live-tracking.md).

## Calling sync ORM code from async

The ORM is synchronous. `sync_to_async(..., thread_sensitive=False)` runs it on a thread pool, so
concurrent streams don't queue behind one thread; the wrapper closes its DB connection because
connections are per thread.

```python
read = sync_to_async(_read_and_close, thread_sensitive=False)
```

Source: [orders/stream.py](../../backend/apps/orders/stream.py), `read`.

## Test settings

Tests always run under `config.settings.test`: a fast password hasher, in-memory Celery broker,
a separate Redis DB, shorter timeouts.

```python
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
…
CELERY_BROKER_URL = "memory://"
```

Source: [settings/test.py](../../backend/config/settings/test.py). More:
[backend-testing](backend-testing.md).

## Not used here

- Django signals (`post_save` etc.): side effects are explicit service calls and outbox events.
- Django's cache framework and `django.contrib.messages` UI: caching is Next's job.
- Class-based template views, forms and the form framework: the UI is a separate Next app.
- Custom model managers / `QuerySet` subclasses: queries live in `selectors.py` and services.
- JWT or token auth: sessions only.
