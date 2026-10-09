import shutil
from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, Product, Seller
from apps.core.olist_import import OlistImporter
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, Payment, Review

pytestmark = pytest.mark.django_db


def ext(prefix: str, label: str) -> str:
    """Fixture IDs are zero-padded to Olist's 32 characters, e.g. o000…0o1."""
    return prefix + "0" * (32 - len(prefix) - len(label)) + label


ORDER = lambda n: ext("o", f"o{n}")  # noqa: E731
REVIEW = lambda n: ext("r", f"r{n}")  # noqa: E731
USER = lambda n: ext("u", f"u{n}")  # noqa: E731


def run_import(olist_dir, *args):
    out = StringIO()
    call_command("import_olist", "--data-dir", str(olist_dir), *args, stdout=out)
    return out.getvalue()


def table_counts():
    return {
        model.__name__: model.objects.count()
        for model in (Category, Seller, Product, Customer, Order, OrderItem, Payment, Review)
    }


EXPECTED_COUNTS = {
    "Category": 3,  # perfumery, health_beauty + untranslated pc_gamer
    "Seller": 2,
    "Product": 3,
    "Customer": 4,  # c1 and c2 are the same person (u1)
    "Order": 5,  # o6 has an unknown customer
    "OrderItem": 5,  # unknown product + malformed price skipped
    "Payment": 5,  # one exact duplicate skipped
    "Review": 3,  # r1, and r2 shared by o2 and o3
}


def test_large_import_counts(olist_dir):
    run_import(olist_dir, "--size", "large")

    assert table_counts() == EXPECTED_COUNTS


def test_reimport_is_idempotent(olist_dir):
    run_import(olist_dir, "--size", "large")
    output = run_import(olist_dir, "--size", "large")

    assert table_counts() == EXPECTED_COUNTS
    # Second run reports zero new rows for every table
    for line in output.splitlines():
        if line.startswith("orders "):
            assert line.split()[1:4] == ["5", "0", "5"]


def test_skipped_rows_are_counted_by_reason(olist_dir):
    results = {r.name: r for r in OlistImporter(olist_dir, "large").run()}

    assert results["orders"].skipped == {"unknown customer": 1}
    assert results["order items"].skipped == {"unknown product": 1, "unparseable amount": 1}
    assert results["payments"].skipped == {"duplicate": 1}
    assert results["reviews"].skipped == {
        "duplicate": 1,
        "score out of range": 1,
        "unknown order": 1,
    }
    assert results["products"].notes == {"no category, imported uncategorised": 1}
    assert results["categories"].notes == {"no translation, pt name used": 1}


def test_summary_is_printed(olist_dir):
    output = run_import(olist_dir, "--size", "large")

    assert "table" in output and "skipped" in output
    assert "unknown product: 1" in output
    assert "Olist import (large) finished" in output


def test_review_shared_by_two_orders_is_kept_once_per_order(olist_dir):
    run_import(olist_dir, "--size", "large")

    shared = Review.objects.filter(external_id=REVIEW(2))
    assert sorted(shared.values_list("order__external_id", flat=True)) == [ORDER(2), ORDER(3)]
    assert shared.first().comment_title == "Ótimo"


def test_messy_values(olist_dir):
    run_import(olist_dir, "--size", "large")

    # Product with a blank category is kept, uncategorised
    assert Product.objects.filter(category__isnull=True).count() == 1
    # Untranslated category keeps its Portuguese name
    assert Category.objects.get(name="pc_gamer").name_english == "pc_gamer"
    # BOM-prefixed translation file still parsed by header name
    assert Category.objects.get(name="perfumaria").name_english == "perfumery"
    # Blank delivery dates become NULL
    canceled = Order.objects.get(external_id=ORDER(3))
    assert canceled.approved_at is None and canceled.delivered_customer_at is None
    assert canceled.status == Order.Status.CANCELED
    # Money is Decimal, never float
    assert OrderItem.objects.get(order__external_id=ORDER(2), item_number=2).price == Decimal("1500.50")
    assert Payment.objects.get(order__external_id=ORDER(2)).payment_type == "not_defined"


def test_timestamps_converted_from_sao_paulo_to_utc(olist_dir):
    run_import(olist_dir, "--size", "large")

    # Oct 2017, before DST started: UTC-3
    o1 = Order.objects.get(external_id=ORDER(1))
    assert o1.purchased_at == datetime(2017, 10, 2, 13, 56, 33, tzinfo=UTC)
    # Jan 2018, Brazilian summer time: UTC-2
    o2 = Order.objects.get(external_id=ORDER(2))
    assert o2.purchased_at == datetime(2018, 1, 15, 14, 0, 0, tzinfo=UTC)
    # Date-only columns keep their calendar date
    assert o1.estimated_delivery_date == date(2017, 10, 18)


def test_customer_deduplicated_by_unique_id_with_latest_address(olist_dir):
    run_import(olist_dir, "--size", "large")

    person = Customer.objects.get(external_id=USER(1))
    assert person.orders.count() == 2
    # Address comes from the most recent order (o2, Jan 2018)
    assert (person.city, person.state) == ("rio de janeiro", "RJ")


def test_small_sample_is_deterministic_and_consistent(olist_dir):
    run_import(olist_dir, "--size", "small", "--order-count", "3")
    first = set(Order.objects.values_list("external_id", flat=True))

    assert len(first) <= 3
    # Only rows related to the sampled orders are imported
    assert set(Customer.objects.values_list("pk", flat=True)) == set(
        Order.objects.values_list("customer_id", flat=True)
    )
    assert Product.objects.count() <= 3 and Seller.objects.count() <= 2

    # Same seed, same sample
    Review.objects.all().delete()
    OrderItem.objects.all().delete()
    Payment.objects.all().delete()
    Order.objects.all().delete()
    run_import(olist_dir, "--size", "small", "--order-count", "3")
    assert set(Order.objects.values_list("external_id", flat=True)) == first


def test_missing_files_fail_with_download_hint(olist_dir, tmp_path):
    for csv_file in olist_dir.glob("*.csv"):
        shutil.copy(csv_file, tmp_path)
    (tmp_path / "olist_orders_dataset.csv").unlink()

    with pytest.raises(CommandError) as exc_info:
        run_import(tmp_path, "--size", "small")

    message = str(exc_info.value)
    assert "olist_orders_dataset.csv" in message
    assert "Brazilian E-Commerce Public Dataset by Olist" in message
    assert "kaggle.com" in message
    assert Order.objects.count() == 0
