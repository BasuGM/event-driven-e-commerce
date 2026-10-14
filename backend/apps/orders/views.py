import re

from django.conf import settings
from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.pagination import StrictPageNumberPagination
from apps.core.idempotency import run_idempotent

from . import services
from .selectors import order_detail, orders_with_totals
from .serializers import (
    CheckoutSerializer,
    DomainErrorSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    PaySerializer,
)

IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_\-:.]{8,255}$")


class OrderPagination(StrictPageNumberPagination):
    page_size = 10
    max_page_size = 50


def _detail(request, order) -> dict:
    fresh = order_detail(request.user).get(pk=order.pk)
    return OrderDetailSerializer(fresh, context={"request": request}).data


class CheckoutView(APIView):
    @extend_schema(
        summary="Place an order from your cart (holds stock until you pay)",
        request=CheckoutSerializer,
        parameters=[
            OpenApiParameter(
                "Idempotency-Key", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True,
                description="Unique per checkout attempt (8-255 chars). Retries reuse it.",
            )
        ],
        responses={201: OrderDetailSerializer, 400: DomainErrorSerializer, 409: DomainErrorSerializer},
    )
    def post(self, request):
        key = request.headers.get("Idempotency-Key", "")
        if not IDEMPOTENCY_KEY.match(key):
            raise ValidationError({"idempotency_key": ["Send an Idempotency-Key header (8-255 URL-safe chars)."]})
        data = CheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        address = services.ShippingAddress(**data.validated_data["shipping"])

        def place():
            order = services.checkout(request.user, address)
            return status.HTTP_201_CREATED, _detail(request, order), order

        result = run_idempotent(request.user, key, data.validated_data, place)
        response = Response(result.body, status=result.status)
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class OrderListView(generics.ListAPIView):
    serializer_class = OrderListSerializer
    pagination_class = OrderPagination

    @extend_schema(summary="Your orders, newest first")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return orders_with_totals(self.request.user)


class OrderMixin:
    def get_order(self, request, order_id: str):
        # Only your own orders exist for you: anyone else's is a 404, not a 403
        order = orders_with_totals(request.user).filter(external_id=order_id).first()
        if order is None:
            raise Http404
        return order


class OrderDetailView(OrderMixin, APIView):
    @extend_schema(summary="One of your orders", responses=OrderDetailSerializer)
    def get(self, request, order_id: str):
        # One query for ownership + totals; prefetches for lines and history
        order = order_detail(request.user).filter(external_id=order_id).first()
        if order is None:
            raise Http404
        return Response(OrderDetailSerializer(order, context={"request": request}).data)


class OrderPayView(OrderMixin, APIView):
    @extend_schema(
        summary="Simulate a payment (dev/test only: ALLOW_FAKE_PAYMENTS)",
        request=PaySerializer,
        responses={200: OrderDetailSerializer, 409: DomainErrorSerializer},
    )
    def post(self, request, order_id: str):
        if not settings.ALLOW_FAKE_PAYMENTS:
            raise Http404
        order = self.get_order(request, order_id)
        data = PaySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.pay(order.pk, data.validated_data["outcome"])
        return Response(_detail(request, order))


class OrderCancelView(OrderMixin, APIView):
    @extend_schema(
        summary="Cancel an unpaid order (returns its stock)",
        request=None,
        responses={200: OrderDetailSerializer, 409: DomainErrorSerializer},
    )
    def post(self, request, order_id: str):
        order = self.get_order(request, order_id)
        services.cancel(order.pk)
        return Response(_detail(request, order))
