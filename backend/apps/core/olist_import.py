"""Import the Olist Brazilian E-Commerce CSVs into our models.

Design notes:
- Every table is written with ``bulk_create(update_conflicts=True)``, i.e. Postgres
  ``INSERT ... ON CONFLICT DO UPDATE`` on the Olist natural key, so re-running is idempotent.
- Rows are validated in Python first; a bad row is counted and logged, never fatal.
- ``small`` picks a deterministic random sample of orders and then keeps only the rows those
  orders reference, so every foreign key resolves.
"""

from __future__ import annotations

import csv
import logging
import random
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO
from zoneinfo import ZoneInfo

from django.db import models, transaction

from apps.catalog.enrichment import category_slug, generate_product_text
from apps.catalog.models import Category, Product, Seller
from apps.catalog.stats import refresh_offers_and_stats
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, Payment, Review

logger = logging.getLogger(__name__)

KAGGLE_URL = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"

FILES = {
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "categories": "product_category_name_translation.csv",
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
}

SOURCE_TZ = ZoneInfo("America/Sao_Paulo")
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_SMALL_ORDER_COUNT = 2000
DEFAULT_SEED = 42
BATCH_SIZE = 2000
# Log at most this many individual bad rows per (table, reason); the rest only get counted.
MAX_LOGGED_PER_REASON = 5


class MissingFilesError(Exception):
    pass


class BadRow(Exception):
    """Raised by row converters; ``reason`` becomes the skipped-counter key."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# --- parsing helpers ---------------------------------------------------------------------


def parse_datetime(value: str, *, required: bool = False) -> datetime | None:
    """Olist timestamps are naive Sao Paulo local time; return an aware UTC datetime."""
    value = value.strip()
    if not value:
        if required:
            raise BadRow("missing required timestamp")
        return None
    try:
        naive = datetime.strptime(value, DATETIME_FORMAT)
    except ValueError:
        raise BadRow("unparseable timestamp") from None
    return naive.replace(tzinfo=SOURCE_TZ).astimezone(UTC)


def parse_date(value: str, *, required: bool = False) -> date | None:
    """Date-only columns (always midnight in the CSV) keep their local calendar date."""
    value = value.strip()
    if not value:
        if required:
            raise BadRow("missing required date")
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        raise BadRow("unparseable date") from None


def parse_int(value: str, *, required: bool = False) -> int | None:
    value = value.strip()
    if not value:
        if required:
            raise BadRow("missing required number")
        return None
    try:
        # Some Olist numeric columns are written as "1.0"
        number = float(value)
    except ValueError:
        raise BadRow("unparseable number") from None
    if not number.is_integer() or number < 0:
        raise BadRow("unparseable number")
    return int(number)


def parse_money(value: str) -> Decimal:
    try:
        amount = Decimal(value.strip())
    except InvalidOperation:
        raise BadRow("unparseable amount") from None
    if not amount.is_finite() or amount < 0:
        raise BadRow("unparseable amount")
    return amount.quantize(Decimal("0.01"))


# --- result bookkeeping ------------------------------------------------------------------


@dataclass
class TableResult:
    name: str
    processed: int = 0
    created: int = 0
    total: int = 0
    skipped: Counter = field(default_factory=Counter)  # rows not imported, by reason
    notes: Counter = field(default_factory=Counter)  # rows imported with a caveat


@dataclass
class TableSpec:
    """How to write one model: natural key + the columns to refresh on conflict."""

    model: type[models.Model]
    unique_fields: list[str]
    update_fields: list[str]


# --- importer ----------------------------------------------------------------------------


class OlistImporter:
    def __init__(
        self,
        data_dir: Path | str,
        size: str = "small",
        *,
        order_count: int = DEFAULT_SMALL_ORDER_COUNT,
        seed: int = DEFAULT_SEED,
        batch_size: int = BATCH_SIZE,
        stdout: TextIO | None = None,
    ):
        if size not in ("small", "large"):
            raise ValueError(f"size must be 'small' or 'large', got {size!r}")
        self.data_dir = Path(data_dir)
        self.size = size
        self.order_count = order_count
        self.seed = seed
        self.batch_size = batch_size
        self.stdout = stdout
        self.results: list[TableResult] = []

    # public API

    def check_files(self) -> None:
        missing = [name for name in FILES.values() if not (self.data_dir / name).is_file()]
        if missing:
            raise MissingFilesError(
                f"Missing Olist CSV file(s) in {self.data_dir}:\n"
                + "".join(f"  - {name}\n" for name in missing)
                + 'Download the Kaggle dataset "Brazilian E-Commerce Public Dataset by Olist" '
                f"from {KAGGLE_URL}, unzip it and put the CSVs directly in {self.data_dir} "
                "(or point OLIST_DATA_DIR / --data-dir at them)."
            )

    def run(self) -> list[TableResult]:
        self.check_files()
        self.results = []

        orders = self._read("orders")
        if self.size == "large":
            items, payments, reviews = self._read("items"), self._read("payments"), self._read("reviews")
            products, sellers = self._read("products"), self._read("sellers")
            customers = self._read("customers")
        else:
            # Keep only rows reachable from the sampled orders so every FK resolves.
            orders = self._sample_orders(orders)
            order_ids = {row["order_id"] for row in orders}
            items = self._read("items", lambda r: r["order_id"] in order_ids)
            payments = self._read("payments", lambda r: r["order_id"] in order_ids)
            reviews = self._read("reviews", lambda r: r["order_id"] in order_ids)
            product_ids = {row["product_id"] for row in items}
            seller_ids = {row["seller_id"] for row in items}
            olist_customer_ids = {row["customer_id"] for row in orders}
            products = self._read("products", lambda r: r["product_id"] in product_ids)
            sellers = self._read("sellers", lambda r: r["seller_id"] in seller_ids)
            customers = self._read("customers", lambda r: r["customer_id"] in olist_customer_ids)

        self._import_categories(products)
        self._import_sellers(sellers)
        self._import_products(products)
        unique_id_by_olist_customer = self._import_customers(customers, orders)
        self._import_orders(orders, unique_id_by_olist_customer)
        self._import_items(items)
        self._import_payments(payments)
        self._import_reviews(reviews)
        self._refresh_offers_and_stats()
        return self.results

    # reading

    def _read(self, key: str, keep: Callable[[dict], bool] | None = None) -> list[dict]:
        path = self.data_dir / FILES[key]
        # utf-8-sig strips the BOM present in the translation CSV
        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = [row for row in csv.DictReader(fh) if keep is None or keep(row)]
        self._say(f"Read {len(rows):,} rows from {path.name}")
        return rows

    def _sample_orders(self, orders: list[dict]) -> list[dict]:
        # Sort first so the sample depends only on the IDs, not on CSV row order.
        ids = sorted({row["order_id"] for row in orders})
        chosen = set(random.Random(self.seed).sample(ids, min(self.order_count, len(ids))))
        self._say(f"Small mode: sampled {len(chosen):,} of {len(ids):,} orders (seed={self.seed})")
        return [row for row in orders if row["order_id"] in chosen]

    # per-table imports

    def _import_categories(self, products: list[dict]) -> None:
        result = TableResult("categories")
        rows: dict[str, str] = {}
        for row in self._read("categories"):
            name = row["product_category_name"].strip()
            english = row["product_category_name_english"].strip()
            if not name or not english:
                self._skip(result, "missing name", row)
                continue
            rows[name] = english
        for row in products:
            name = row["product_category_name"].strip()
            if name and name not in rows:
                # Real gap in Olist (e.g. pc_gamer): keep the category with its Portuguese name.
                logger.warning("No English translation for category %r; using Portuguese name", name)
                result.notes["no translation, pt name used"] += 1
                rows[name] = name
        objs = (
            Category(name=name, name_english=english, slug=category_slug(english))
            for name, english in rows.items()
        )
        self._write(result, TableSpec(Category, ["name"], ["name_english", "slug"]), objs)

    def _import_sellers(self, sellers: list[dict]) -> None:
        result = TableResult("sellers")
        spec = TableSpec(Seller, ["external_id"], ["zip_code_prefix", "city", "state"])

        def build(row: dict) -> Seller:
            return Seller(
                external_id=row["seller_id"],
                zip_code_prefix=row["seller_zip_code_prefix"].strip(),
                city=row["seller_city"].strip(),
                state=row["seller_state"].strip(),
            )

        self._write(result, spec, self._convert(result, sellers, build, key="seller_id"))

    def _import_products(self, products: list[dict]) -> None:
        result = TableResult("products")
        categories = {
            name: (pk, english)
            for name, pk, english in Category.objects.values_list("name", "pk", "name_english")
        }
        dims = ["name_length", "description_length", "photos_qty", "weight_g", "length_cm",
                "height_cm", "width_cm"]
        spec = TableSpec(
            Product, ["external_id"], ["category", "name", "slug", "description", *dims]
        )

        def build(row: dict) -> Product:
            category_name = row["product_category_name"].strip()
            category_pk, category_english = categories.get(category_name, (None, None))
            product = Product(
                external_id=row["product_id"],
                category_id=category_pk,
                # Olist misspells "length" as "lenght" in these headers
                name_length=parse_int(row["product_name_lenght"]),
                description_length=parse_int(row["product_description_lenght"]),
                photos_qty=parse_int(row["product_photos_qty"]),
                weight_g=parse_int(row["product_weight_g"]),
                length_cm=parse_int(row["product_length_cm"]),
                height_cm=parse_int(row["product_height_cm"]),
                width_cm=parse_int(row["product_width_cm"]),
            )
            # Olist has no names/descriptions: generate them deterministically from the ID.
            text = generate_product_text(
                product.external_id,
                category_english,
                description_length=product.description_length,
                dims={f: getattr(product, f) for f in ("length_cm", "width_cm", "height_cm",
                                                       "weight_g")},
            )
            product.name, product.slug, product.description = text.name, text.slug, text.description
            if not category_name:
                result.notes["no category, imported uncategorised"] += 1
            return product

        self._write(result, spec, self._convert(result, products, build, key="product_id"))

    def _import_customers(self, customers: list[dict], orders: list[dict]) -> dict[str, str]:
        """Collapse Olist's per-order customer rows into one Customer per real person.

        Returns ``olist customer_id -> customer_unique_id`` for linking orders.
        """
        result = TableResult("customers")
        purchased_at = {row["customer_id"]: row["order_purchase_timestamp"] for row in orders}
        latest: dict[str, dict] = {}
        unique_id_by_olist_customer: dict[str, str] = {}
        for row in customers:
            unique_id = row["customer_unique_id"].strip()
            if not unique_id:
                self._skip(result, "missing customer_unique_id", row)
                continue
            unique_id_by_olist_customer[row["customer_id"]] = unique_id
            current = latest.get(unique_id)
            # ISO-like timestamp strings sort chronologically; the latest order's address wins
            if current is None or purchased_at.get(row["customer_id"], "") >= purchased_at.get(
                current["customer_id"], ""
            ):
                latest[unique_id] = row
        spec = TableSpec(Customer, ["external_id"], ["zip_code_prefix", "city", "state"])
        objs = (
            Customer(
                external_id=unique_id,
                zip_code_prefix=row["customer_zip_code_prefix"].strip(),
                city=row["customer_city"].strip(),
                state=row["customer_state"].strip(),
            )
            for unique_id, row in latest.items()
        )
        self._write(result, spec, objs)
        return unique_id_by_olist_customer

    def _import_orders(self, orders: list[dict], unique_id_by_olist_customer: dict[str, str]) -> None:
        result = TableResult("orders")
        customer_pk = dict(Customer.objects.values_list("external_id", "pk"))
        statuses = set(Order.Status.values)
        spec = TableSpec(
            Order,
            ["external_id"],
            ["customer", "olist_customer_id", "status", "purchased_at", "approved_at",
             "delivered_carrier_at", "delivered_customer_at", "estimated_delivery_date"],
        )

        def build(row: dict) -> Order:
            pk = customer_pk.get(unique_id_by_olist_customer.get(row["customer_id"], ""))
            if pk is None:
                raise BadRow("unknown customer")
            status = row["order_status"].strip()
            if status not in statuses:
                raise BadRow("invalid status")
            return Order(
                external_id=row["order_id"],
                customer_id=pk,
                olist_customer_id=row["customer_id"],
                status=status,
                purchased_at=parse_datetime(row["order_purchase_timestamp"], required=True),
                approved_at=parse_datetime(row["order_approved_at"]),
                delivered_carrier_at=parse_datetime(row["order_delivered_carrier_date"]),
                delivered_customer_at=parse_datetime(row["order_delivered_customer_date"]),
                estimated_delivery_date=parse_date(row["order_estimated_delivery_date"]),
            )

        self._write(result, spec, self._convert(result, orders, build, key="order_id"))

    def _import_items(self, items: list[dict]) -> None:
        result = TableResult("order items")
        order_pk = dict(Order.objects.values_list("external_id", "pk"))
        product_pk = dict(Product.objects.values_list("external_id", "pk"))
        seller_pk = dict(Seller.objects.values_list("external_id", "pk"))
        spec = TableSpec(
            OrderItem,
            ["order", "item_number"],
            ["product", "seller", "shipping_limit_at", "price", "freight_value"],
        )

        def build(row: dict) -> OrderItem:
            refs = (order_pk.get(row["order_id"]), product_pk.get(row["product_id"]),
                    seller_pk.get(row["seller_id"]))
            for pk, label in zip(refs, ("order", "product", "seller"), strict=True):
                if pk is None:
                    raise BadRow(f"unknown {label}")
            return OrderItem(
                order_id=refs[0],
                item_number=parse_int(row["order_item_id"], required=True),
                product_id=refs[1],
                seller_id=refs[2],
                shipping_limit_at=parse_datetime(row["shipping_limit_date"], required=True),
                price=parse_money(row["price"]),
                freight_value=parse_money(row["freight_value"]),
            )

        rows = self._convert(result, items, build, key=("order_id", "order_item_id"))
        self._write(result, spec, rows)

    def _import_payments(self, payments: list[dict]) -> None:
        result = TableResult("payments")
        order_pk = dict(Order.objects.values_list("external_id", "pk"))
        payment_types = set(Payment.PaymentType.values)
        spec = TableSpec(
            Payment, ["order", "sequential"], ["payment_type", "installments", "value"]
        )

        def build(row: dict) -> Payment:
            pk = order_pk.get(row["order_id"])
            if pk is None:
                raise BadRow("unknown order")
            payment_type = row["payment_type"].strip()
            if payment_type not in payment_types:
                raise BadRow("invalid payment type")
            return Payment(
                order_id=pk,
                sequential=parse_int(row["payment_sequential"], required=True),
                payment_type=payment_type,
                installments=parse_int(row["payment_installments"], required=True),
                value=parse_money(row["payment_value"]),
            )

        rows = self._convert(result, payments, build, key=("order_id", "payment_sequential"))
        self._write(result, spec, rows)

    def _import_reviews(self, reviews: list[dict]) -> None:
        result = TableResult("reviews")
        order_pk = dict(Order.objects.values_list("external_id", "pk"))
        spec = TableSpec(
            Review,
            ["external_id", "order"],
            ["score", "comment_title", "comment_message", "created_date", "answered_at"],
        )

        def build(row: dict) -> Review:
            pk = order_pk.get(row["order_id"])
            if pk is None:
                raise BadRow("unknown order")
            score = parse_int(row["review_score"], required=True)
            if not 1 <= score <= 5:
                raise BadRow("score out of range")
            return Review(
                external_id=row["review_id"],
                order_id=pk,
                score=score,
                comment_title=row["review_comment_title"].strip(),
                comment_message=row["review_comment_message"].strip(),
                created_date=parse_date(row["review_creation_date"], required=True),
                answered_at=parse_datetime(row["review_answer_timestamp"]),
            )

        # A review_id shared by several orders is legitimate (one row per order); only an
        # exact (review_id, order_id) repeat is a duplicate.
        rows = self._convert(result, reviews, build, key=("review_id", "order_id"))
        self._write(result, spec, rows)

    def _refresh_offers_and_stats(self) -> None:
        result = TableResult("offers")
        with transaction.atomic():
            stats = refresh_offers_and_stats()
        result.processed, result.created, result.total = (
            stats.offers_written, stats.offers_created, stats.offers_total
        )
        self._progress(result)
        self.results.append(result)
        changed = ", ".join(f"{label} {n:,}" for label, n in stats.products_changed.items())
        self._say(f"Product stats refreshed (products changed: {changed})")

    # shared machinery

    def _convert(
        self,
        result: TableResult,
        rows: Iterable[dict],
        build: Callable[[dict], models.Model],
        *,
        key: str | tuple[str, ...],
    ) -> Iterator[models.Model]:
        """Build model instances, skipping bad rows and in-file duplicates of the natural key.

        Duplicates must be dropped here: Postgres refuses an ``ON CONFLICT DO UPDATE`` that
        touches the same row twice within one statement.
        """
        fields = (key,) if isinstance(key, str) else key
        seen: set[tuple[str, ...]] = set()
        for row in rows:
            natural_key = tuple(row[f].strip() for f in fields)
            if natural_key in seen:
                self._skip(result, "duplicate", row)
                continue
            seen.add(natural_key)
            try:
                yield build(row)
            except BadRow as exc:
                self._skip(result, exc.reason, row)

    def _write(self, result: TableResult, spec: TableSpec, objs: Iterable[models.Model]) -> None:
        manager = spec.model.objects
        with transaction.atomic():
            before = manager.count()
            batch: list[models.Model] = []
            for obj in objs:
                batch.append(obj)
                if len(batch) >= self.batch_size:
                    self._flush(result, spec, batch)
                    batch = []
            if batch:
                self._flush(result, spec, batch)
            result.total = manager.count()
        result.created = result.total - before
        if result.processed == 0:
            self._progress(result)  # no batches ran, so nothing was printed yet
        self.results.append(result)

    def _flush(self, result: TableResult, spec: TableSpec, batch: list[models.Model]) -> None:
        spec.model.objects.bulk_create(
            batch,
            update_conflicts=True,
            unique_fields=spec.unique_fields,
            update_fields=spec.update_fields,
        )
        result.processed += len(batch)
        self._progress(result)

    def _skip(self, result: TableResult, reason: str, row: dict[str, Any]) -> None:
        result.skipped[reason] += 1
        if result.skipped[reason] <= MAX_LOGGED_PER_REASON:
            logger.warning("Skipping %s row (%s): %s", result.name, reason, dict(row))
        elif result.skipped[reason] == MAX_LOGGED_PER_REASON + 1:
            logger.warning("Further '%s' rows in %s are counted, not logged", reason, result.name)

    def _progress(self, result: TableResult) -> None:
        """One line per batch; the last batch's line doubles as the table's final count."""
        if self.stdout is None:
            return
        self.stdout.write(f"  {result.name:<12} {result.processed:>9,} rows written\n")
        self.stdout.flush()

    def _say(self, message: str) -> None:
        if self.stdout is not None:
            self.stdout.write(message + "\n")


def format_summary(results: list[TableResult]) -> str:
    def describe(counter: Counter) -> str:
        return ", ".join(f"{reason}: {n:,}" for reason, n in sorted(counter.items())) or "-"

    header = (
        f"{'table':<12} {'written':>9} {'new':>9} {'in DB':>9} {'skipped':>8}  details"
    )
    lines = [header, "-" * (len(header) + 20)]
    for r in results:
        details = []
        if r.skipped:
            details.append(f"skipped: {describe(r.skipped)}")
        if r.notes:
            details.append(f"notes: {describe(r.notes)}")
        lines.append(
            f"{r.name:<12} {r.processed:>9,} {r.created:>9,} {r.total:>9,} "
            f"{sum(r.skipped.values()):>8,}  {'; '.join(details) or '-'}"
        )
    return "\n".join(lines)
