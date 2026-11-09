"""Backfill Order.source for existing rows: orders whose customer has a user account were placed
in the app; everything else came from the Olist import. Frozen: raw SQL, no app imports."""

from django.db import migrations

BACKFILL = """
UPDATE orders_order o
SET source = CASE WHEN c.user_id IS NOT NULL THEN 'app' ELSE 'olist' END
FROM customers_customer c
WHERE c.id = o.customer_id AND o.source IS NULL
"""


def backfill(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(BACKFILL)


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_order_source_nullable"), ("customers", "0002_customer_user")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
