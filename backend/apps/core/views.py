from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product, Seller
from apps.customers.models import Customer
from apps.orders.models import Order

from .health import check_db, check_redis, outbox_backlog
from .serializers import HealthSerializer, StatsSerializer


def _label(ok: bool) -> str:
    return "ok" if ok else "error"


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        operation_id="health_retrieve",
        responses={200: HealthSerializer, 503: HealthSerializer},
        summary="Status of the database and Redis",
    )
    def get(self, request):
        db_ok, redis_ok = check_db(), check_redis()
        data = {
            "status": _label(db_ok and redis_ok),
            "db": _label(db_ok),
            "redis": _label(redis_ok),
            "outbox": outbox_backlog() if db_ok else None,
        }
        code = status.HTTP_200_OK if db_ok and redis_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(HealthSerializer(data).data, status=code)


class StatsView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        operation_id="stats_retrieve",
        responses=StatsSerializer,
        summary="Row counts for the dashboard",
    )
    def get(self, request):
        data = {
            "products": Product.objects.count(),
            "orders": Order.objects.count(),
            "customers": Customer.objects.count(),
            "sellers": Seller.objects.count(),
        }
        return Response(StatsSerializer(data).data)
