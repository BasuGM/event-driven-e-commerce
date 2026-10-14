import itertools

import pytest
from django.db import transaction

from apps.core.errors import InvalidTransition
from apps.orders.models import Order
from apps.orders.state import TRANSITIONS, can_transition, transition

pytestmark = pytest.mark.django_db

S = Order.Status
LEGAL = {
    (S.CREATED, S.APPROVED), (S.CREATED, S.CANCELED),
    (S.APPROVED, S.INVOICED), (S.APPROVED, S.CANCELED),
    (S.INVOICED, S.SHIPPED),
    (S.SHIPPED, S.DELIVERED),
}


def test_table_matches_the_spec():
    assert {(a, b) for a, targets in TRANSITIONS.items() for b in targets} == LEGAL


@pytest.fixture
def order(make_user, address, make_offer, fill_cart):
    from apps.orders.services import checkout

    user = make_user()
    fill_cart(user, (make_offer(), 1))
    return checkout(user, address)


@pytest.mark.parametrize("from_status, to_status", list(itertools.product(S.values, S.values)))
def test_every_pair(order, from_status, to_status):
    Order.objects.filter(pk=order.pk).update(status=from_status)
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if (from_status, to_status) in LEGAL:
            transition(locked, to_status, "test")
            assert Order.objects.get(pk=order.pk).status == to_status
            last = order.status_history.last()
            assert (last.from_status, last.to_status, last.reason) == (from_status, to_status, "test")
        else:
            assert not can_transition(from_status, to_status)
            with pytest.raises(InvalidTransition):
                transition(locked, to_status, "test")
            assert Order.objects.get(pk=order.pk).status == from_status


def test_approved_and_delivered_stamp_timestamps(order):
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        for status in (S.APPROVED, S.INVOICED, S.SHIPPED, S.DELIVERED):
            transition(locked, status, "test")
    order.refresh_from_db()
    assert order.approved_at and order.delivered_carrier_at and order.delivered_customer_at
    assert [h.to_status for h in order.status_history.all()] == [
        S.CREATED, S.APPROVED, S.INVOICED, S.SHIPPED, S.DELIVERED
    ]


@pytest.mark.django_db(transaction=True)  # the default test wrapper is itself a transaction
def test_transition_outside_a_transaction_is_refused(order):
    with pytest.raises(RuntimeError):
        transition(order, S.APPROVED, "test")
