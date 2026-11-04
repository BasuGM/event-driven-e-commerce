from django.urls import path

from .views import CheckoutView, OrderCancelView, OrderDetailView, OrderListView

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("orders/", OrderListView.as_view(), name="order-list"),
    path("orders/<str:order_id>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:order_id>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
]
