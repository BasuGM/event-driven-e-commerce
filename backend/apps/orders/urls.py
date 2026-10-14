from django.urls import path

from .views import CheckoutView, OrderCancelView, OrderDetailView, OrderListView, OrderPayView

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("orders/", OrderListView.as_view(), name="order-list"),
    path("orders/<str:order_id>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:order_id>/pay/", OrderPayView.as_view(), name="order-pay"),
    path("orders/<str:order_id>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
]
