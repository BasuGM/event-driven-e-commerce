from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.catalog.stats import SALES_SQL


class Command(BaseCommand):
    help = (
        "Recompute sales_count/first_sold_at for every product, excluding canceled and "
        "unavailable orders. One-off for data counted before Step 4; safe to re-run."
    )

    def handle(self, *args, **options):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(SALES_SQL.format(scope=""))
            changed = cursor.rowcount
        self.stdout.write(self.style.SUCCESS(f"sales_count backfilled: {changed} product(s) changed"))
