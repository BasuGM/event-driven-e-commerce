import pytest

pytestmark = pytest.mark.django_db


def add(client, offer, quantity=1):
    return client.post("/api/cart/items/", {"offer_id": offer.id, "quantity": quantity}, format="json")


def test_empty_cart(user_client):
    data = user_client().get("/api/cart/").json()
    assert data == {
        "lines": [], "item_count": 0, "subtotal": "0.00", "freight_total": "0.00", "total": "0.00",
        "can_checkout": False,
    }


def test_add_and_merge_lines_with_totals(user_client, make_offer):
    client = user_client()
    offer = make_offer(stock=5, price="19.90", freight="7.50")
    assert add(client, offer, 2).status_code == 201
    data = add(client, offer, 1).json()

    assert len(data["lines"]) == 1
    line = data["lines"][0]
    assert (line["quantity"], line["unit_price"], line["line_total"], line["line_freight"]) == (3, "19.90", "59.70", "22.50")
    assert line["product"]["name"].startswith("Test Product")
    assert line["seller"]["state"] == "SP" and len(line["seller"]["id"]) == 8
    assert (data["item_count"], data["subtotal"], data["freight_total"], data["total"]) == (3, "59.70", "22.50", "82.20")
    assert data["can_checkout"] is True


def test_line_quantity_is_capped_at_ten(user_client, make_offer):
    client = user_client()
    offer = make_offer(stock=50)
    add(client, offer, 8)
    response = add(client, offer, 3)
    assert response.status_code == 400 and "quantity" in response.json()
    assert add(client, offer, 11).status_code == 400  # validated before touching the cart too


def test_update_and_remove(user_client, make_offer):
    client = user_client()
    a, b = make_offer(), make_offer()
    add(client, a)
    data = add(client, b).json()
    line_id = data["lines"][0]["id"]

    data = client.patch(f"/api/cart/items/{line_id}/", {"quantity": 4}, format="json").json()
    assert data["lines"][0]["quantity"] == 4
    assert client.patch(f"/api/cart/items/{line_id}/", {"quantity": 0}, format="json").status_code == 400

    data = client.delete(f"/api/cart/items/{line_id}/").json()
    assert [l["offer_id"] for l in data["lines"]] == [b.id]


def test_warnings_and_cart_never_reserves(user_client, make_offer):
    client = user_client()
    low, gone = make_offer(stock=2), make_offer(stock=0)
    add(client, low, 3)
    data = add(client, gone, 1).json()

    warnings = {l["offer_id"]: (l["warning"], l["available"]) for l in data["lines"]}
    assert warnings == {low.id: ("insufficient_stock", 2), gone.id: ("out_of_stock", 0)}
    assert data["can_checkout"] is False
    low.refresh_from_db()
    assert low.stock == 2  # adding to the cart holds nothing


def test_unknown_offer(user_client):
    assert user_client().post("/api/cart/items/", {"offer_id": 999999}, format="json").status_code == 400


def test_cannot_touch_someone_elses_line(user_client, make_offer):
    owner, other = user_client(), user_client()
    line_id = add(owner, make_offer()).json()["lines"][0]["id"]
    assert other.patch(f"/api/cart/items/{line_id}/", {"quantity": 2}, format="json").status_code == 404
    assert other.delete(f"/api/cart/items/{line_id}/").status_code == 404


def test_cart_query_count_is_constant(user_client, make_offer, django_assert_max_num_queries):
    client = user_client()
    for _ in range(5):
        add(client, make_offer())
    # session + user, cart get_or_create, lines with offer/product/category/seller in one JOIN
    with django_assert_max_num_queries(5):
        client.get("/api/cart/")
