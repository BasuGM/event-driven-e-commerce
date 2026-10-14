"""Cart reads and edits. The cart never reserves stock; it only reports availability."""

from __future__ import annotations

from decimal import Decimal

from rest_framework.exceptions import ValidationError

from apps.catalog.models import Offer

from .models import MAX_LINE_QUANTITY, Cart, CartItem


def get_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def cart_summary(cart: Cart) -> dict:
    lines = (
        cart.items.select_related("offer__product__category", "offer__seller").order_by("added_at", "id")
    )
    out, subtotal, freight_total, units, ok = [], Decimal("0.00"), Decimal("0.00"), 0, True
    for item in lines:
        offer = item.offer
        warning = None
        if offer.stock == 0:
            warning = "out_of_stock"
        elif item.quantity > offer.stock:
            warning = "insufficient_stock"
        ok = ok and warning is None
        line_total = offer.price * item.quantity
        line_freight = offer.freight * item.quantity
        subtotal += line_total
        freight_total += line_freight
        units += item.quantity
        out.append(
            {
                "id": item.id,
                "offer_id": offer.id,
                "product": {
                    "slug": offer.product.slug,
                    "name": offer.product.name,
                    "category": offer.product.category,
                },
                "seller": {
                    "id": offer.seller.external_id[:8],
                    "city": offer.seller.city,
                    "state": offer.seller.state,
                },
                "quantity": item.quantity,
                "unit_price": offer.price,
                "unit_freight": offer.freight,
                "line_total": line_total,
                "line_freight": line_freight,
                "available": offer.stock,
                "warning": warning,
            }
        )
    return {
        "lines": out,
        "item_count": units,
        "subtotal": subtotal,
        "freight_total": freight_total,
        "total": subtotal + freight_total,
        "can_checkout": bool(out) and ok,
    }


def add_item(user, offer_id: int, quantity: int) -> Cart:
    if not Offer.objects.filter(pk=offer_id).exists():
        raise ValidationError({"offer_id": ["Unknown offer."]})
    cart = get_cart(user)
    item, created = CartItem.objects.get_or_create(cart=cart, offer_id=offer_id, defaults={"quantity": quantity})
    if not created:
        if item.quantity + quantity > MAX_LINE_QUANTITY:
            raise ValidationError(
                {"quantity": [f"You can have at most {MAX_LINE_QUANTITY} of one item (you have {item.quantity})."]}
            )
        item.quantity += quantity
        item.save(update_fields=["quantity"])
    cart.save(update_fields=["updated_at"])
    return cart
