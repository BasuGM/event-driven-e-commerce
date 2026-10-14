from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.models import Product
from apps.catalog.stats import refresh_product_stats

pytestmark = pytest.mark.django_db


def ext(prefix: str, label: str) -> str:
    return prefix + "0" * (32 - len(prefix) - len(label)) + label


@pytest.fixture
def catalog(olist_dir):
    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=StringIO())
    return {n: Product.objects.get(external_id=ext("9d0d0c7", f"p{n}")) for n in range(1, 5)}


def slugs(response):
    assert response.status_code == 200, response.json()
    return [p["slug"] for p in response.json()["results"]]


# --- categories ---------------------------------------------------------------------------


def test_categories_only_lists_categories_with_products(api_client, catalog):
    data = api_client.get("/api/categories/").json()
    by_slug = {c["slug"]: c for c in data}
    assert set(by_slug) == {"perfumery", "health-beauty", "pc-gamer"}
    assert by_slug["perfumery"] == {
        "slug": "perfumery", "label": "Perfumery", "group": "beauty", "product_count": 1
    }


# --- list: shape, ordering, pagination ----------------------------------------------------


def test_list_is_lean(api_client, catalog):
    item = api_client.get("/api/products/").json()["results"][0]
    assert set(item) == {
        "slug", "name", "category", "image_url", "min_price", "in_stock", "rating_avg", "rating_count"
    }


def test_default_ordering_is_popular(api_client, catalog):
    # sales_count: p1=4, p2=3, p3=2, p4=1
    assert slugs(api_client.get("/api/products/")) == [catalog[n].slug for n in (1, 2, 3, 4)]


@pytest.mark.parametrize(
    "ordering, expected",
    [
        ("price", [1, 2, 3, 4]),  # 58.90, 75.01, 1500.50, then no price last
        ("-price", [3, 2, 1, 4]),  # no price still last
        ("rating", [3, 1, 2, 4]),  # 4.00, 3.50, 3.33, 3.00
        # first sale: p4 in o8 (2018-08), p2 & p3 tie in o2 (2018-01, id breaks the tie), p1 in o1
        ("newest", [4, 2, 3, 1]),
    ],
)
def test_orderings(api_client, catalog, ordering, expected):
    response = api_client.get("/api/products/", {"ordering": ordering})
    assert slugs(response) == [catalog[n].slug for n in expected]


def test_pagination(api_client, catalog):
    first = api_client.get("/api/products/", {"page_size": 3}).json()
    second = api_client.get("/api/products/", {"page_size": 3, "page": 2}).json()
    assert first["count"] == 4 and len(first["results"]) == 3 and first["next"]
    assert len(second["results"]) == 1 and second["next"] is None
    assert api_client.get("/api/products/", {"page": 99}).status_code == 404


# --- list: filters and search -------------------------------------------------------------


def test_filter_by_category(api_client, catalog):
    assert slugs(api_client.get("/api/products/", {"category": "pc-gamer"})) == [catalog[3].slug]


def test_filter_by_price_range(api_client, catalog):
    response = api_client.get("/api/products/", {"min_price": "60", "max_price": "1500.50"})
    assert set(slugs(response)) == {catalog[2].slug, catalog[3].slug}


def test_filter_by_min_rating(api_client, catalog):
    response = api_client.get("/api/products/", {"min_rating": "3.5"})
    assert set(slugs(response)) == {catalog[1].slug, catalog[3].slug}


@pytest.mark.parametrize("value, expected", [("true", {1, 2, 3}), ("false", {4})])
def test_filter_in_stock(api_client, catalog, value, expected):
    response = api_client.get("/api/products/", {"in_stock": value})
    assert set(slugs(response)) == {catalog[n].slug for n in expected}


def test_search_matches_word_prefixes_in_name(api_client, catalog):
    target = catalog[1]
    words = target.name.split()
    query = " ".join(w[:3] for w in words[-2:])  # e.g. "Bod Lot" for "... Body Lotion"
    assert target.slug in slugs(api_client.get("/api/products/", {"q": query}))


def test_search_matches_category_name(api_client, catalog):
    assert slugs(api_client.get("/api/products/", {"q": "perfum"})) == [catalog[1].slug]


def test_search_ranks_name_matches_above_category_matches(api_client, catalog):
    # Give p2 (uncategorised) "perfumery" in its name: name weight A beats p1's category (B).
    Product.objects.filter(pk=catalog[2].pk).update(name="Perfumery Travel Case")
    refresh_product_stats([catalog[2].pk], labels=("search",))
    assert slugs(api_client.get("/api/products/", {"q": "perfumery"})) == [
        catalog[2].slug, catalog[1].slug
    ]


def test_search_ignores_punctuation_only_query(api_client, catalog):
    assert len(slugs(api_client.get("/api/products/", {"q": "!!! ::"}))) == 4


# --- list: validation ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "params, field",
    [
        ({"min_price": "abc"}, "min_price"),
        ({"min_price": "-1"}, "min_price"),
        ({"min_price": "10", "max_price": "5"}, "max_price"),
        ({"min_rating": "6"}, "min_rating"),
        ({"in_stock": "maybe"}, "in_stock"),
        ({"ordering": "cheapest"}, "ordering"),
        ({"category": "does-not-exist"}, "category"),
        ({"q": "x" * 101}, "q"),
        ({"page": "0"}, "page"),
        ({"page": "abc"}, "page"),
        ({"page_size": "101"}, "page_size"),
        ({"page_size": "-5"}, "page_size"),
    ],
)
def test_bad_params_return_400(api_client, catalog, params, field):
    response = api_client.get("/api/products/", params)
    assert response.status_code == 400
    assert field in response.json()


# --- detail and reviews -------------------------------------------------------------------


def test_detail_has_offers_cheapest_first_without_stock_numbers(api_client, catalog):
    data = api_client.get(f"/api/products/{catalog[3].slug}/").json()
    assert data["description"] and data["dimensions"]["weight_g"] is not None
    assert [(o["price"], o["in_stock"]) for o in data["offers"]] == [
        ("1400.00", False), ("1500.50", True)
    ]
    assert set(data["offers"][0]) == {"id", "seller_id", "seller_city", "seller_state", "price", "in_stock"}
    assert data["offers"][0]["seller_state"] == "SC"


def test_detail_404(api_client, catalog):
    assert api_client.get("/api/products/nope/").status_code == 404


def test_reviews_are_deduplicated_and_newest_first(api_client, catalog):
    data = api_client.get(f"/api/products/{catalog[1].slug}/reviews/").json()
    # r6 is attached to o7 and o8 (both contain p1) but must appear once
    assert data["count"] == 4
    dates = [r["created_date"] for r in data["results"]]
    assert dates == sorted(dates, reverse=True)
    assert data["results"][0]["title"] == "Bom"


def test_reviews_404_for_unknown_product(api_client, catalog):
    assert api_client.get("/api/products/nope/reviews/").status_code == 404


def test_reviews_paginate(api_client, catalog):
    data = api_client.get(f"/api/products/{catalog[1].slug}/reviews/", {"page_size": 3}).json()
    assert len(data["results"]) == 3 and data["next"]


# --- query counts (N+1 guards) ------------------------------------------------------------


def test_list_query_count(api_client, catalog, django_assert_num_queries):
    with django_assert_num_queries(2):  # count + page (category via JOIN)
        api_client.get("/api/products/", {"page_size": 100})
    with django_assert_num_queries(3):  # + category slug validation
        api_client.get("/api/products/", {"category": "perfumery"})


def test_detail_query_count(api_client, catalog, django_assert_num_queries):
    with django_assert_num_queries(2):  # product + category, offers + sellers
        api_client.get(f"/api/products/{catalog[3].slug}/")


def test_reviews_query_count(api_client, catalog, django_assert_num_queries):
    with django_assert_num_queries(3):  # product lookup, count, page
        api_client.get(f"/api/products/{catalog[1].slug}/reviews/")


def test_categories_query_count(api_client, catalog, django_assert_num_queries):
    with django_assert_num_queries(1):
        api_client.get("/api/categories/")


def test_list_prices_are_strings_with_two_decimals(api_client, catalog):
    item = next(
        p for p in api_client.get("/api/products/").json()["results"] if p["slug"] == catalog[2].slug
    )
    assert item["min_price"] == "75.01" and Decimal(item["min_price"]) == Decimal("75.01")
    assert item["category"] is None
