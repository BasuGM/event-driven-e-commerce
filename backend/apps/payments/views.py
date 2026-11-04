import json

from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.serializers import DomainErrorSerializer
from apps.orders.views import OrderMixin

from .gateway import get_gateway, payments_enabled
from .services import handle_webhook, start_payment
from .signature import InvalidSignature


class PaymentStartSerializer(serializers.Serializer):
    redirect_url = serializers.CharField(help_text="Send the customer here to pay (the provider's page)")
    status = serializers.CharField()


class OrderPaymentView(OrderMixin, APIView):
    @extend_schema(
        summary="Start paying for an order: creates (or reuses) its payment, returns where to pay",
        request=None,
        responses={200: PaymentStartSerializer, 409: DomainErrorSerializer},
    )
    def post(self, request, order_id: str):
        if not payments_enabled():
            raise Http404
        order = self.get_order(request, order_id)
        intent = start_payment(order, return_url=f"/orders/{order.external_id}?payment=processing")
        return Response(PaymentStartSerializer({"redirect_url": intent.redirect_url, "status": intent.status}).data)


@csrf_exempt  # authenticated by the HMAC signature instead (no browser, no cookies)
@require_POST
def webhook(request):
    """The provider's webhook. A plain Django view on purpose: the signature covers the raw
    body, and DRF's request parsing would hand us re-serialised data."""
    gateway = get_gateway()
    try:
        event = gateway.parse_webhook(request.body, request.headers)
    except (InvalidSignature, ValueError, KeyError, json.JSONDecodeError):
        return JsonResponse({"detail": "Invalid webhook"}, status=400)
    outcome = handle_webhook(gateway.name, event)
    # 2xx for duplicates and ignored events too: the provider must stop retrying them
    return JsonResponse({"received": True, "outcome": outcome})
