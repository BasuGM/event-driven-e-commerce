from datetime import timedelta

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.pagination import StrictPageNumberPagination
from apps.events.models import EventLog

from . import services
from .permissions import IsStaffOr404
from .serializers import (
    DeadLetterRetrySerializer,
    EventFilterSerializer,
    EventLogSerializer,
    StaffHealthSerializer,
    TimelineEventSerializer,
)


class StaffView:
    permission_classes = [IsStaffOr404]


class EventPagination(StrictPageNumberPagination):
    page_size = 50
    max_page_size = 200


class EventListView(StaffView, generics.ListAPIView):
    serializer_class = EventLogSerializer
    pagination_class = EventPagination

    @extend_schema(
        summary="Event log (staff): newest first",
        parameters=[
            OpenApiParameter("type", str), OpenApiParameter("aggregate_id", str),
            OpenApiParameter("date_from", str, description="YYYY-MM-DD"),
            OpenApiParameter("date_to", str, description="YYYY-MM-DD"),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        filters = EventFilterSerializer(data=self.request.query_params)
        if not filters.is_valid():
            raise ValidationError(filters.errors)
        data = filters.validated_data
        queryset = EventLog.objects.order_by("-occurred_at", "-id")
        if "type" in data:
            queryset = queryset.filter(type=data["type"])
        if "aggregate_id" in data:
            queryset = queryset.filter(aggregate_id=data["aggregate_id"])
        if "date_from" in data:
            queryset = queryset.filter(occurred_at__gte=services.day_start(data["date_from"]))
        if "date_to" in data:
            queryset = queryset.filter(occurred_at__lt=services.day_start(data["date_to"]) + timedelta(days=1))
        return queryset


class EventTypesView(StaffView, APIView):
    @extend_schema(summary="Event types seen in the log (staff)", responses={200: {"type": "array", "items": {"type": "string"}}})
    def get(self, request):
        return Response(sorted(EventLog.objects.values_list("type", flat=True).distinct()))


class OrderTimelineView(StaffView, APIView):
    @extend_schema(summary="Every event for one order, oldest first, with consumer status (staff)",
                   responses=TimelineEventSerializer(many=True))
    def get(self, request, order_id: str):
        return Response(TimelineEventSerializer(services.order_timeline(order_id), many=True).data)


class HealthView(StaffView, APIView):
    @extend_schema(summary="Consumer groups, outbox backlog and dead letters (staff)", responses=StaffHealthSerializer)
    def get(self, request):
        return Response(StaffHealthSerializer(services.health()).data)


class DeadLetterRetryView(StaffView, APIView):
    @extend_schema(
        summary="Re-deliver a dead-lettered event to its stream (staff; idempotent)",
        request=None,
        responses=DeadLetterRetrySerializer,
    )
    def post(self, request, entry_id: str):
        try:
            retry, created = services.retry_dead_letter(entry_id, user=request.user)
        except services.DeadLetterNotFound:
            raise NotFound from None
        retry.created = created
        return Response(DeadLetterRetrySerializer(retry).data)
