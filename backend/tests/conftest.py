from pathlib import Path

import pytest
from rest_framework.test import APIClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "olist"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def olist_dir():
    return FIXTURES_DIR


# --- order-flow fixtures (no importer needed) ---------------------------------------------

import itertools
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Offer, Product, Seller
from apps.orders.services import ShippingAddress

_seq = itertools.count(1)

ADDRESS = {
    "full_name": "Ana Souza",
    "street": "Av. Paulista, 1000, apto 12",
    "city": "São Paulo",
    "state": "SP",
    "zip_code": "01310-100",
}


def _hex() -> str:
    return uuid.uuid4().hex


@pytest.fixture
def make_offer(db):
    def make(*, stock=5, price="100.00", freight="10.00", product=None, name=None) -> Offer:
        n = next(_seq)
        if product is None:
            category, _ = Category.objects.get_or_create(
                name="cama_mesa_banho", defaults={"name_english": "bed_bath_table", "slug": "bed-bath-table"}
            )
            product = Product.objects.create(
                external_id=_hex(), category=category, name=name or f"Test Product {n}", slug=f"test-product-{n}-{_hex()[:6]}"
            )
        seller = Seller.objects.create(external_id=_hex(), zip_code_prefix="01310", city="sao paulo", state="SP")
        return Offer.objects.create(
            product=product, seller=seller, price=Decimal(price), freight=Decimal(freight), stock=stock
        )

    return make


@pytest.fixture
def make_user(db):
    def make(email=None, password="s3cret-pass-123", name="Ana Souza"):
        email = email or f"user{next(_seq)}@example.com"
        first, _, last = name.partition(" ")
        return get_user_model().objects.create_user(
            username=email, email=email, password=password, first_name=first, last_name=last
        )

    return make


@pytest.fixture
def fill_cart():
    def fill(user, *lines):
        cart, _ = Cart.objects.get_or_create(user=user)
        for offer, quantity in lines:
            CartItem.objects.create(cart=cart, offer=offer, quantity=quantity)
        return cart

    return fill


@pytest.fixture
def address():
    return ShippingAddress(**ADDRESS)


@pytest.fixture
def user_client(make_user):
    """A logged-in API client (CSRF not enforced; see test_auth for the CSRF checks)."""

    def make(user=None):
        user = user or make_user()
        client = APIClient()
        client.force_login(user)
        client.user = user
        return client

    return make
