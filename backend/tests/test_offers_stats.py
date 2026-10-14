from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection

from apps.catalog.models import Offer, Product
from apps.catalog.stats import stock_sql

pytestmark = pytest.mark.django_db


def ext(prefix: str, label: str) -> str:
    return prefix + "0" * (32 - len(prefix) - len(label)) + label


P = {n: ext("9d0d0c7", f"p{n}") for n in range(1, 5)}
S = {1: ext("5e11e7", "s1"), 2: ext("5e11e7", "s2"), 3: "5e11e7000000000000000000000293s3"}


@pytest.fixture
def imported(olist_dir):
    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=StringIO())


def offer(p: int, s: int) -> Offer:
    return Offer.objects.get(product__external_id=P[p], seller__external_id=S[s])


def product(p: int) -> Product:
    return Product.objects.get(external_id=P[p])


def test_offer_price_is_median_of_item_prices(imported):
    assert offer(1, 1).price == Decimal("60.00")  # odd: [58.90, 60.00, 70.00]
    assert offer(2, 1).price == Decimal("75.01")  # even: (50.01 + 100.00) / 2 = 75.005, half-up
    assert offer(3, 2).price == Decimal("1500.50")  # single item


def test_stock_is_deterministic_with_known_out_of_stock_pairs(imported, olist_dir):
    # The fixture's third seller ID was chosen so both of its offers hash to stock 0.
    assert offer(3, 3).stock == 0 and offer(4, 3).stock == 0
    assert offer(1, 1).stock > 0
    stocks = dict(Offer.objects.values_list("pk", "stock"))
    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=StringIO())
    assert dict(Offer.objects.values_list("pk", "stock")) == stocks


def test_stock_formula_puts_about_ten_percent_out_of_stock():
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT avg(CASE WHEN stock = 0 THEN 1.0 ELSE 0 END), min(stock), max(stock)
            FROM (SELECT {stock_sql("md5(g::text)", "'seller'")} AS stock
                  FROM generate_series(1, 10000) g) t
            """
        )
        share, low, high = cursor.fetchone()
    assert Decimal("0.08") < share < Decimal("0.12")
    assert (low, high) == (0, 50)


def test_min_price_ignores_out_of_stock_offers(imported):
    assert product(1).min_price == Decimal("58.90")
    assert product(2).min_price == Decimal("75.01")  # the 30.00 offer (p2/s2) has no stock
    assert product(3).min_price == Decimal("1500.50")  # the cheaper 1400.00 offer is out of stock
    assert product(4).min_price is None  # only offer is out of stock


def test_sales_and_first_sold_at(imported):
    assert [product(n).sales_count for n in range(1, 5)] == [4, 3, 2, 1]
    assert product(1).first_sold_at == datetime(2017, 10, 2, 13, 56, 33, tzinfo=UTC)


def test_ratings_count_each_review_once_per_product(imported):
    # p1 is in o1 (r1=4), o3 (r2=5), o7 (r5=2, r6=3) and o8 (r6 again): r6 counts once.
    p1 = product(1)
    assert (p1.rating_count, p1.rating_avg) == (4, Decimal("3.50"))
    p2 = product(2)
    assert (p2.rating_count, p2.rating_avg) == (3, Decimal("3.33"))
    assert (product(4).rating_count, product(4).rating_avg) == (1, Decimal("3.00"))


def test_search_vector_is_populated(imported):
    assert not Product.objects.filter(search_vector__isnull=True).exists()


def test_reimport_changes_nothing(imported, olist_dir):
    fields = ["name", "slug", "description", "min_price", "rating_avg", "rating_count",
              "sales_count", "first_sold_at"]
    before_products = list(Product.objects.order_by("pk").values(*fields))
    before_offers = list(Offer.objects.order_by("pk").values("price", "stock"))
    out = StringIO()

    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=out)

    assert list(Product.objects.order_by("pk").values(*fields)) == before_products
    assert list(Offer.objects.order_by("pk").values("price", "stock")) == before_offers
    assert "products changed: sales 0, ratings 0, min_price 0, search 0" in out.getvalue()


def test_offer_freight_is_median_of_item_freight(imported):
    assert offer(1, 1).freight == Decimal("8.00")  # [13.29, 8.00, 8.00]
    assert offer(2, 1).freight == Decimal("14.00")  # even: (8.00 + 20.00) / 2


def test_reseed_never_overwrites_live_stock(imported, olist_dir):
    # Stock belongs to the order flow once an offer exists (reservations decrement it)
    Offer.objects.filter(pk=offer(1, 1).pk).update(stock=2)
    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=StringIO())
    assert offer(1, 1).stock == 2
