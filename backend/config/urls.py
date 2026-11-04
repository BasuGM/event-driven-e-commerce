from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.catalog.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.cart.urls")),
    path("api/", include("apps.orders.urls")),
    path("api/", include("apps.payments.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.ALLOW_FAKE_PAYMENTS:
    # The fake payment provider's hosted page (dev/test only). Under /api so the Next proxy
    # serves it to every browser (host and e2e container) from one relative URL.
    urlpatterns.append(path("api/fake-provider/", include("apps.fake_provider.urls")))
