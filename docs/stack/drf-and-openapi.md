# The API contract: DRF, drf-spectacular, openapi-typescript, openapi-fetch, zod, react-hook-form

One chain, end to end: Django REST Framework serves JSON; drf-spectacular turns the views and
serializers into an OpenAPI schema; openapi-typescript turns the schema into TypeScript types;
openapi-fetch gives a typed client; zod + react-hook-form validate forms that mirror the request
types. Versions: DRF 3.18.3, drf-spectacular 0.30.0, openapi-typescript 7.13.0, openapi-fetch
0.17.0, zod 4.6.5, react-hook-form 7.89.0 (with `@hookform/resolvers` 5.9.1). Official docs:
[django-rest-framework.org](https://www.django-rest-framework.org/).

## DRF defaults in settings

One block sets the schema class, session-only auth, "logged in" as the default permission (public
views opt out) and a custom exception handler.

```python
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
}
```

Source: [settings/base.py](../../backend/config/settings/base.py), `REST_FRAMEWORK`.

## Views: `APIView` and generic views

Plain `APIView` for custom endpoints, generic views (`ListAPIView`, `RetrieveAPIView`) when the
shape is "a queryset through a serializer". There are no ViewSets or routers: URLs are listed
explicitly.

```python
class ProductDetailView(PublicMixin, generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"
    queryset = Product.objects.select_related("category").prefetch_related(…)
```

Source: [catalog/views.py](../../backend/apps/catalog/views.py), `ProductDetailView`.

## Serializers: output that is always present

Output serializers set `read_only_fields = fields`. drf-spectacular then marks every field as
always present, so the generated TypeScript type has no needless `| undefined`.

```python
class ProductListSerializer(serializers.ModelSerializer):
    category = CategoryRefSerializer(read_only=True, allow_null=True)
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "slug", "name", "category", "image_url", "min_price", "in_stock",
            …
        ]
        read_only_fields = fields
```

Source: [catalog/serializers.py](../../backend/apps/catalog/serializers.py),
`ProductListSerializer`.

## `SerializerMethodField` with a declared type

A computed field has no obvious type, so the method is annotated for the schema with
`extend_schema_field`.

```python
@extend_schema_field(serializers.BooleanField())
def get_in_stock(self, obj: Product) -> bool:
    return obj.min_price is not None
```

Source: [catalog/serializers.py](../../backend/apps/catalog/serializers.py),
`ProductListSerializer.get_in_stock`.

## Validating query parameters with a serializer

Query strings are validated like request bodies: bad values give a 400 with per-field messages,
and the same serializer documents the parameters in OpenAPI.

```python
@extend_schema(summary="Browse, filter and search products", parameters=[ProductListQuerySerializer])
class ProductListView(PublicMixin, generics.ListAPIView):
    def get_queryset(self):
        params = ProductListQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        return filter_products(Product.objects.select_related("category"), params.validated_data)
```

Source: [catalog/views.py](../../backend/apps/catalog/views.py), `ProductListView`; the
serializer is `ProductListQuerySerializer` in [catalog/filters.py](../../backend/apps/catalog/filters.py).

## Pagination, stricter than the default

DRF's default quietly ignores a bad `page_size`. The subclass answers malformed values with 400;
a valid page past the end is still 404.

```python
class StrictPageNumberPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100
```

Source: [catalog/pagination.py](../../backend/apps/catalog/pagination.py),
`StrictPageNumberPagination`.

## Custom authentication: 401 vs 403

DRF answers 403 for anonymous users unless the auth class supplies a `WWW-Authenticate` value.
The subclass does, so the frontend can tell "not logged in" (401) from "forbidden" (403).

```python
class SessionAuthentication(authentication.SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"
```

Source: [accounts/authentication.py](../../backend/apps/accounts/authentication.py),
`SessionAuthentication`. More: [auth-and-sessions](../flows/auth-and-sessions.md).

## Permissions

Every endpoint requires a session by default; public views set `permission_classes`. A custom
`BasePermission` turns "not staff" into a 404, so staff tools don't reveal themselves.

```python
class IsStaffOr404(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_staff):
            raise NotFound
        return True
```

Source: [staff/permissions.py](../../backend/apps/staff/permissions.py), `IsStaffOr404`. More:
[ADR 0013](../adr/0013-staff-pages-404.md).

## A custom exception handler

Services raise plain domain errors; one handler maps them to `{code, detail, …}` with the right
status, so views carry no `try/except` for them.

```python
def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response(exc.payload(), status=exc.status_code)
    return drf_exception_handler(exc, context)
```

Source: [core/exceptions.py](../../backend/apps/core/exceptions.py), `exception_handler`.

## Headers as input: `Idempotency-Key`

`POST /api/checkout/` requires an `Idempotency-Key` header, validated before any work. The header
is declared for the schema with `OpenApiParameter`, so it shows up in the generated types.

```python
parameters=[
    OpenApiParameter(
        "Idempotency-Key", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True,
        description="Unique per checkout attempt (8-255 chars). Retries reuse it.",
    )
],
```

Source: [orders/views.py](../../backend/apps/orders/views.py), `CheckoutView`. More:
[idempotency](../concepts/idempotency.md), [ADR 0016](../adr/0016-idempotency-key-for-checkout.md).

## drf-spectacular: documenting responses

`@extend_schema` states the summary, request body and every response status. Error bodies share
one `DomainError` schema, which the frontend relies on.

```python
@extend_schema(
    summary="Start paying for an order: creates (or reuses) its payment, returns where to pay",
    request=None,
    responses={200: PaymentStartSerializer, 409: DomainErrorSerializer},
)
```

Source: [payments/views.py](../../backend/apps/payments/views.py), `OrderPaymentView.post`.

## drf-spectacular settings and schema views

`COMPONENT_SPLIT_REQUEST` and `ENUM_NAME_OVERRIDES` keep component and enum names stable, which
keeps the TypeScript type names stable. Two URLs serve the schema and Swagger UI.

```python
SPECTACULAR_SETTINGS = {
    "TITLE": "Event-driven e-commerce API",
    …
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "HealthStatusEnum": "apps.core.serializers.HEALTH_CHOICES",
        "OrderStatusEnum": "apps.orders.models.Order.Status",
    },
}
```

Source: [settings/base.py](../../backend/config/settings/base.py), `SPECTACULAR_SETTINGS`;
routes in [config/urls.py](../../backend/config/urls.py).

## From schema to types: `make types`

The schema is dumped (and validated) into the frontend tree, then `openapi-typescript` writes
`schema.d.ts`. Run it after any API change; both files are committed.

```make
types: require-env
	$(COMPOSE) exec -T backend python manage.py spectacular --validate > frontend/src/lib/api/schema.yml
	$(FRONTEND) npm run types
```

```json
"types": "openapi-typescript src/lib/api/schema.yml -o src/lib/api/schema.d.ts",
```

Source: [Makefile](../../Makefile), `types`; [frontend/package.json](../../frontend/package.json).

## Named aliases over generated types

Components import friendly names, defined by indexing into the generated `components` type, so
a renamed schema is fixed in one file.

```ts
import type { components, paths } from "./schema"

export type ProductDetail = components["schemas"]["ProductDetail"]
export type OrderStatus = components["schemas"]["OrderStatusEnum"]
```

Source: [lib/api/client.ts](../../frontend/src/lib/api/client.ts).

## openapi-fetch: a typed client

`createClient<paths>()` returns `GET`/`POST` methods whose paths, query parameters and bodies are
checked against the schema, and whose result is `{ data, error, response }`.

```ts
export const api = createClient<paths>({
  baseUrl: process.env.API_URL ?? "http://localhost:8000",
})
```

```ts
const { data, error, response } = await withTimeout("products", (signal) =>
  api.GET("/api/products/", { params: { query: toApiQuery(filters) }, signal }),
)
```

Source: [lib/api/client.ts](../../frontend/src/lib/api/client.ts), `api`;
[lib/api/catalog.ts](../../frontend/src/lib/api/catalog.ts), `getProducts`.

## Timeouts without middleware

Every server-side call goes through `withTimeout` (an `AbortSignal.timeout`). It deliberately
isn't an openapi-fetch middleware, because middleware calls `Math.random()`, which Next's
prerender check rejects.

```ts
export async function withTimeout<T>(label: string, call: (signal: AbortSignal) => Promise<T>): Promise<T> {
  try {
    return await call(AbortSignal.timeout(TIMEOUT_MS))
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new BackendTimeoutError(…)
```

Source: [lib/api/client.ts](../../frontend/src/lib/api/client.ts), `withTimeout`.

## One client per side: server (visitor cookies) and browser (CSRF)

On the server, a client is built per call with the visitor's cookies forwarded to Django. In the
browser, a same-origin client adds `X-CSRFToken` to unsafe requests through openapi-fetch's
`fetch` option, reading the cookie on every request because Django rotates it at login.

```ts
async function asVisitor() {
  const cookieHeader = (await cookies()).toString()
  return createClient<paths>({
    baseUrl: process.env.API_URL ?? "http://localhost:8000",
    headers: cookieHeader ? { cookie: cookieHeader } : {},
  })
}
```

```ts
export const browserApi = createClient<paths>({
  baseUrl: "",
  fetch: (request) => {
    if (!SAFE_METHODS.has(request.method)) {
      request.headers.set("X-CSRFToken", readCookie("csrftoken") ?? "")
    }
    return fetch(request)
  },
})
```

Source: [lib/api/server.ts](../../frontend/src/lib/api/server.ts), `asVisitor`;
[lib/api/browser.ts](../../frontend/src/lib/api/browser.ts), `browserApi`. More:
[ADR 0004](../adr/0004-sessions-behind-the-next-proxy.md).

## Turning error bodies into something a form can show

Django returns three error shapes (domain `{code, detail}`, field errors, nested field errors).
`toProblem` flattens them into one type with a code, a message and per-field messages.

```ts
export type ApiProblem = {
  status: number
  code: string
  message: string
  fieldErrors: Record<string, string[]>
  lines?: DomainError["lines"]
}
```

Source: [lib/api/browser.ts](../../frontend/src/lib/api/browser.ts), `ApiProblem` and `toProblem`.

## zod schemas that mirror request types

A zod schema describes what the form accepts before anything is sent. It mirrors the API's
request type; the server still validates (password rules, duplicate email).

```ts
// Mirrors RegisterRequest; Django's password validators still run on the server.
export const registerSchema = z.object({
  name: z.string().trim().min(1, "Enter your name.").max(150),
  email: z.email("Enter a valid email address."),
  password: z.string().min(8, "Use at least 8 characters."),
})
type RegisterValues = z.infer<typeof registerSchema>
```

Source: [register-form.tsx](../../frontend/src/components/auth/register-form.tsx),
`registerSchema`. `z.infer` derives the TypeScript type from the schema.

## react-hook-form with `Controller`

`useForm` holds form state; `zodResolver` plugs the zod schema in; `Controller` binds each shadcn
`Field` to it. Server-side field errors are pushed back with `form.setError`.

```tsx
const form = useForm<RegisterValues>({
  resolver: zodResolver(registerSchema),
  defaultValues: { name: "", email: "", password: "" },
})
```

```tsx
<Controller
  name={name}
  control={form.control}
  render={({ field, fieldState }) => (
    <Field data-invalid={fieldState.invalid}>
```

Source: [register-form.tsx](../../frontend/src/components/auth/register-form.tsx),
`RegisterForm`. The pre-hydration rules for forms are in [react-and-typescript](react-and-typescript.md).

## zod at a server boundary

zod also validates input to the cache-invalidation route handler: anything that isn't a bounded
list of well-formed tags is a 400.

```ts
const bodySchema = z.object({
  tags: z.array(z.string().regex(REVALIDATABLE_TAG)).min(1).max(100),
})
…
const parsed = bodySchema.safeParse(await request.json().catch(() => null))
```

Source: [app/internal/revalidate/route.ts](../../frontend/src/app/internal/revalidate/route.ts),
`POST`. More: [ADR 0017](../adr/0017-cache-invalidation-by-consumer.md).

## Not used here

- DRF ViewSets, routers, `filter_backends`/django-filter, throttling, token or JWT auth,
  browsable API: explicit URLs, serializer-validated params, session auth only.
- drf-spectacular's `@extend_schema_view` and custom `OpenApiExample`s.
- openapi-fetch middleware (see timeouts above) and `openapi-react-query`.
- zod `.transform`/async refinements and react-hook-form `useFieldArray`.
- API versioning: a single unversioned `/api/`.
