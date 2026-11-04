from django.urls import path

from .views import OrderPaymentView, payment_return, webhook

urlpatterns = [
    path("orders/<str:order_id>/payment/", OrderPaymentView.as_view(), name="order-payment"),
    path("orders/<str:order_id>/payment/return/", payment_return, name="order-payment-return"),
    path("payments/webhook/", webhook, name="payments-webhook"),
]
