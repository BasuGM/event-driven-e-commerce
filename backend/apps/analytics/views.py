from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.staff.permissions import IsStaffOr404

from .queries import dashboard
from .serializers import AnalyticsFilterSerializer, DashboardSerializer


class AnalyticsView(APIView):
    """Business metrics: staff only (404 for everyone else), like the event explorer."""

    permission_classes = [IsStaffOr404]

    @extend_schema(
        summary="Analytics dashboard data (staff)",
        parameters=[
            OpenApiParameter("source", str, enum=["all", "olist", "app", "replay"]),
            OpenApiParameter("date_from", str, description="YYYY-MM-DD (purchase day, Sao Paulo time)"),
            OpenApiParameter("date_to", str, description="YYYY-MM-DD"),
        ],
        responses=DashboardSerializer,
    )
    def get(self, request):
        filters = AnalyticsFilterSerializer(data=request.query_params)
        if not filters.is_valid():
            raise ValidationError(filters.errors)
        data = filters.validated_data
        return Response(DashboardSerializer(dashboard(data["source"], data.get("date_from"), data.get("date_to"))).data)
