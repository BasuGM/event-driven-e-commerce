"""Stripe-style webhook signatures: HMAC-SHA256 over "<t>." + raw body, timestamp tolerance."""

import json
import time

import pytest

from apps.payments.signature import InvalidSignature, compute, sign, verify

SECRET = "whsec_test"
BODY = b'{"id":"evt_1","type":"payment_intent.succeeded"}'


def test_a_valid_signature_returns_its_timestamp():
    now = time.time()
    header = sign(SECRET, BODY, timestamp=int(now))
    assert verify(header, BODY, SECRET, tolerance=300, now=now) == int(now)


@pytest.mark.parametrize(
    "header, body, secret, age",
    [
        ("sign-with-wrong-secret", BODY, SECRET, 0),
        ("valid", BODY.replace(b"evt_1", b"evt_2"), SECRET, 0),  # body changed by a byte
        ("valid", BODY + b" ", SECRET, 0),  # even whitespace: the HMAC is over the raw bytes
        ("valid", BODY, SECRET, 301),  # outside the tolerance
        ("valid", BODY, SECRET, -301),  # from the future
        ("", BODY, SECRET, 0),
        ("t=abc,v1=00", BODY, SECRET, 0),
        ("v1=deadbeef", BODY, SECRET, 0),  # no timestamp
        ("valid", BODY, "", 0),  # no secret configured: never accept
    ],
)
def test_rejects_anything_not_signed_by_us_just_now(header, body, secret, age):
    t = int(time.time()) - age
    if header == "valid":
        header = sign(SECRET, BODY, timestamp=t)
    elif header == "sign-with-wrong-secret":
        header = sign("whsec_other", BODY, timestamp=t)
    with pytest.raises(InvalidSignature, match="^invalid signature$"):
        verify(header, body, secret, tolerance=300)


def test_accepts_any_matching_v1_for_secret_rotation():
    t = int(time.time())
    header = f"t={t},v1={compute('whsec_old', t, BODY)},v1={compute(SECRET, t, BODY)}"
    assert verify(header, BODY, SECRET, tolerance=300) == t


@pytest.mark.django_db
def test_the_webhook_view_rejects_bad_signatures_with_a_vague_400(api_client):
    body = json.dumps({"id": "evt_x", "type": "payment_intent.succeeded", "created": int(time.time()),
                       "data": {"object": {"id": "pi_x"}}}).encode()
    good = sign(SECRET, body)
    for header, payload in [("t=1,v1=00", body), (good, body + b"\n"), (sign("nope", body), body)]:
        response = api_client.generic(
            "POST", "/api/payments/webhook/", payload, content_type="application/json", HTTP_FAKE_SIGNATURE=header
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid webhook"}

    accepted = api_client.generic(
        "POST", "/api/payments/webhook/", body, content_type="application/json", HTTP_FAKE_SIGNATURE=good
    )
    assert accepted.status_code == 200  # unknown payment: recorded, nothing to do
    assert accepted.json() == {"received": True, "outcome": "no_change"}
