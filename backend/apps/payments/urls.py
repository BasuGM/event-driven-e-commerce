from django.urls import path

from .views import OrderPaymentView, webhook

urlpatterns = [
    path("orders/<str:order_id>/payment/", OrderPaymentView.as_view(), name="order-payment"),
    path("payments/webhook/", webhook, name="payments-webhook"),
]
