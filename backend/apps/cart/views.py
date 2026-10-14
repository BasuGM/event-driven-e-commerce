from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CartItem
from .serializers import AddCartItemSerializer, CartSerializer, UpdateCartItemSerializer
from .services import add_item, cart_summary, get_cart


def cart_response(cart, code=status.HTTP_200_OK) -> Response:
    return Response(CartSerializer(cart_summary(cart)).data, status=code)


class CartView(APIView):
    @extend_schema(responses=CartSerializer, summary="Your cart with current prices and availability")
    def get(self, request):
        return cart_response(get_cart(request.user))


class CartItemsView(APIView):
    @extend_schema(request=AddCartItemSerializer, responses={201: CartSerializer}, summary="Add an offer to your cart")
    def post(self, request):
        data = AddCartItemSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        cart = add_item(request.user, data.validated_data["offer_id"], data.validated_data["quantity"])
        return cart_response(cart, status.HTTP_201_CREATED)


class CartItemView(APIView):
    def _item(self, request, item_id) -> CartItem:
        # Scoped to your own cart: someone else's item is simply "not found"
        return get_object_or_404(CartItem, pk=item_id, cart__user=request.user)

    @extend_schema(request=UpdateCartItemSerializer, responses=CartSerializer, summary="Change a line's quantity")
    def patch(self, request, item_id: int):
        item = self._item(request, item_id)
        data = UpdateCartItemSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        item.quantity = data.validated_data["quantity"]
        item.save(update_fields=["quantity"])
        return cart_response(item.cart)

    @extend_schema(request=None, responses=CartSerializer, summary="Remove a line")
    def delete(self, request, item_id: int):
        item = self._item(request, item_id)
        cart = item.cart
        item.delete()
        return cart_response(cart)
