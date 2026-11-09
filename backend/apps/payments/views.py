import json

from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.selectors import orders_with_totals
from apps.orders.serializers import DomainErrorSerializer
from apps.core.errors import ReplayReadOnly
from apps.orders.views import OrderMixin, refuse_replay

from .gateway import get_gateway, payments_enabled
from .services import handle_webhook, mark_returned, start_payment
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
        order = self.get_actionable_order(request, order_id)
        intent = start_payment(order, return_url=f"/api/orders/{order.external_id}/payment/return/")
        return Response(PaymentStartSerializer({"redirect_url": intent.redirect_url, "status": intent.status}).data)


def payment_return(request, order_id: str):
    """Where the provider sends the customer back. Records "processing" server-side (so the
    page shows "payment in progress" even after a reload), then goes to the order page. A GET
    with a side effect, deliberately: it's a redirect target, and it only changes UI state."""
    order_path = f"/orders/{order_id}"
    if not request.user.is_authenticated:
        return HttpResponseRedirect(f"/login?next={order_path}")
    order = orders_with_totals(request.user).filter(external_id=order_id).first()
    if order is None:
        raise Http404
    try:
        refuse_replay(order)
    except ReplayReadOnly as exc:  # a plain Django view: no DRF exception handler here
        return JsonResponse(exc.payload(), status=exc.status_code)
    mark_returned(order)
    return HttpResponseRedirect(order_path)


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
