"""Read side of the dashboard: sums over the projection rows (exact Decimal arithmetic)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Max, Min, Sum
from django.db.models.functions import TruncWeek

from .models import CategorySales, DailySales, DeliveryStats, StateSales

CENT = Decimal("0.01")
TOP_CATEGORIES = 10


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _filter(queryset, source: str, date_from: date, date_to: date):
    queryset = queryset.filter(day__gte=date_from, day__lte=date_to)
    return queryset if source == "all" else queryset.filter(source=source)


def bounds(source: str) -> tuple[date | None, date | None]:
    queryset = DailySales.objects.all() if source == "all" else DailySales.objects.filter(source=source)
    row = queryset.aggregate(first=Min("day"), last=Max("day"))
    return row["first"], row["last"]


def dashboard(source: str, date_from: date | None, date_to: date | None) -> dict:
    first, last = bounds(source)
    date_from = date_from or first or date.today()
    date_to = date_to or last or date.today()
    daily = _filter(DailySales.objects, source, date_from, date_to)
    delivery = _filter(DeliveryStats.objects, source, date_from, date_to)

    totals = daily.aggregate(
        orders=Sum("orders"), canceled=Sum("canceled_orders"), paid=Sum("paid_orders"), gmv=Sum("gmv")
    )
    orders, canceled, paid = totals["orders"] or 0, totals["canceled"] or 0, totals["paid"] or 0
    gmv = totals["gmv"] or Decimal("0.00")
    shipped = delivery.aggregate(delivered=Sum("delivered"), seconds=Sum("delivery_seconds_total"), late=Sum("late"))
    delivered, seconds, late = shipped["delivered"] or 0, shipped["seconds"] or 0, shipped["late"] or 0

    categories = list(
        _filter(CategorySales.objects, source, date_from, date_to)
        .values("category__slug", "category__name_english")
        .annotate(revenue=Sum("revenue"), units=Sum("units"))
        .order_by("-revenue", "category__slug")
    )
    top, rest = categories[:TOP_CATEGORIES], categories[TOP_CATEGORIES:]
    by_category = [
        {"slug": c["category__slug"] or "", "label": _label(c["category__name_english"]), "revenue": c["revenue"], "units": c["units"]}
        for c in top
    ]
    if rest:
        by_category.append({
            "slug": "other", "label": f"Other ({len(rest)} categories)",
            "revenue": sum((c["revenue"] for c in rest), Decimal("0.00")), "units": sum(c["units"] for c in rest),
        })

    return {
        "source": source,
        "date_from": date_from,
        "date_to": date_to,
        "first_day": first,
        "last_day": last,
        "kpis": {
            "orders": orders,
            "canceled_orders": canceled,
            "cancel_rate": _rate(canceled, orders),
            "paid_orders": paid,
            "gmv": gmv,
            "aov": (gmv / paid).quantize(CENT, rounding=ROUND_HALF_UP) if paid else None,
            "delivered": delivered,
            "avg_delivery_days": round(seconds / delivered / 86400, 1) if delivered else None,
            "late_share": _rate(late, delivered),
        },
        "daily": list(
            daily.values("day").annotate(orders=Sum("orders"), paid_orders=Sum("paid_orders"), gmv=Sum("gmv")).order_by("day")
        ),
        "by_category": by_category,
        "by_state": list(
            _filter(StateSales.objects, source, date_from, date_to)
            .values("state").annotate(orders=Sum("orders"), gmv=Sum("gmv")).order_by("-gmv", "state")
        ),
        "delivery_by_week": [
            {
                "week": row["week"],
                "delivered": row["delivered"],
                "avg_days": round(row["seconds"] / row["delivered"] / 86400, 1) if row["delivered"] else None,
                "late_share": _rate(row["late"], row["delivered"]),
            }
            for row in delivery.annotate(week=TruncWeek("day")).values("week")
            .annotate(delivered=Sum("delivered"), seconds=Sum("delivery_seconds_total"), late=Sum("late"))
            .order_by("week")
        ],
    }


def _label(name_english: str | None) -> str:
    from apps.catalog.enrichment import category_label

    return category_label(name_english) if name_english else "Uncategorised"


def default_window(last: date | None, days: int) -> tuple[date, date] | None:
    return (last - timedelta(days=days - 1), last) if last else None
