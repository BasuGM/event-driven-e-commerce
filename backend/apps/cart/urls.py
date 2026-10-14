from django.urls import path

from .views import CartItemsView, CartItemView, CartView

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/items/", CartItemsView.as_view(), name="cart-items"),
    path("cart/items/<int:item_id>/", CartItemView.as_view(), name="cart-item"),
]
