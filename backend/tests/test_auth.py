import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

TRUSTED = "http://localhost:3000"  # CSRF_TRUSTED_ORIGINS in test settings


def csrf_client() -> tuple[APIClient, str]:
    """A client that enforces CSRF like a browser, with a token from /api/auth/csrf/."""
    client = APIClient(enforce_csrf_checks=True)
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 200
    return client, client.cookies["csrftoken"].value


def post(client, url, data, token=None, origin=TRUSTED):
    headers = {}
    if token:
        headers["HTTP_X_CSRFTOKEN"] = token
    if origin:
        headers["HTTP_ORIGIN"] = origin
    return client.post(url, data, format="json", **headers)


def test_me_is_null_when_logged_out():
    assert APIClient().get("/api/auth/me/").json() == {"user": None, "cart_count": 0}


def test_login_me_logout(make_user):
    make_user("ana@example.com", name="Ana Souza")
    client, token = csrf_client()

    response = post(client, "/api/auth/login/", {"email": "ANA@example.com", "password": "s3cret-pass-123"}, token)
    assert response.status_code == 200
    assert response.json()["name"] == "Ana Souza"
    assert client.get("/api/auth/me/").json()["user"]["email"] == "ana@example.com"

    # Login rotates the CSRF token: the old one no longer works for unsafe requests
    new_token = client.cookies["csrftoken"].value
    assert new_token != token
    assert post(client, "/api/auth/logout/", {}, new_token).status_code == 204
    assert client.get("/api/auth/me/").json() == {"user": None, "cart_count": 0}


def test_wrong_password_is_rejected(make_user):
    make_user("ana@example.com")
    client, token = csrf_client()
    response = post(client, "/api/auth/login/", {"email": "ana@example.com", "password": "nope"}, token)
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_credentials"


def test_register_creates_user_and_logs_in():
    client, token = csrf_client()
    response = post(
        client, "/api/auth/register/",
        {"name": "Bruno Lima", "email": "Bruno@Example.com", "password": "a-long-passphrase"}, token,
    )
    assert response.status_code == 201
    assert response.json()["email"] == "bruno@example.com"
    assert client.get("/api/auth/me/").json()["user"]["name"] == "Bruno Lima"


def test_register_validates_password_and_duplicate_email(make_user):
    make_user("taken@example.com")
    client, token = csrf_client()
    weak = post(client, "/api/auth/register/", {"name": "X", "email": "new@example.com", "password": "12345678"}, token)
    assert weak.status_code == 400 and "non_field_errors" in weak.json()
    dup = post(client, "/api/auth/register/", {"name": "X", "email": "TAKEN@example.com", "password": "a-long-passphrase"}, token)
    assert dup.status_code == 400 and "email" in dup.json()


# --- CSRF -------------------------------------------------------------------------------------


def test_login_requires_csrf_token(make_user):
    make_user("ana@example.com")
    client, _ = csrf_client()
    response = post(client, "/api/auth/login/", {"email": "ana@example.com", "password": "s3cret-pass-123"}, token=None)
    assert response.status_code == 403  # login CSRF is blocked too


def test_unsafe_request_without_token_is_403_when_logged_in(make_user):
    user = make_user()
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.post("/api/cart/items/", {"offer_id": 1, "quantity": 1}, format="json")
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_untrusted_origin_is_rejected(make_user):
    make_user("ana@example.com")
    client, token = csrf_client()
    response = post(
        client, "/api/auth/login/", {"email": "ana@example.com", "password": "s3cret-pass-123"}, token,
        origin="http://evil.example.com",
    )
    assert response.status_code == 403


def test_proxy_shape_trusted_origin_with_backend_host_is_accepted(make_user):
    """Through the Next rewrite Django sees Host=backend:8000 but Origin=the browser's origin."""
    make_user("ana@example.com")
    client, token = csrf_client()
    response = client.post(
        "/api/auth/login/", {"email": "ana@example.com", "password": "s3cret-pass-123"}, format="json",
        HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN=TRUSTED, HTTP_HOST="backend:8000",
    )
    assert response.status_code == 200


def test_unauthenticated_is_401_not_403():
    assert APIClient().get("/api/cart/").status_code == 401
    assert APIClient().get("/api/orders/").status_code == 401


def test_seeded_dev_users_can_log_in_by_email(monkeypatch):
    monkeypatch.setenv("DEV_USER_PASSWORD", "dev-pass-for-tests")
    call_command("seed_dev_users", stdout=None)
    for name in ("admin", "staff", "customer"):
        client, token = csrf_client()
        response = post(client, "/api/auth/login/", {"email": f"{name}@example.com", "password": "dev-pass-for-tests"}, token)
        assert response.status_code == 200, name


def test_me_includes_cart_count(user_client, make_offer, fill_cart):
    client = user_client()
    fill_cart(client.user, (make_offer(), 2), (make_offer(), 3))
    data = client.get("/api/auth/me/").json()
    assert data["cart_count"] == 5 and data["user"]["email"] == client.user.email
