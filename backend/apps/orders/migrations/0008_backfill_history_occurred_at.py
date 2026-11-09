"""Backfill OrderStatusHistory.occurred_at. Replay copies take the historical time from their
logged event's payload (one transition per (status, reason) per order); everything else, and
any replay row whose event was already purged, takes created_at (the real time, which is the
domain time for app and imported orders). Frozen: raw SQL, no app imports."""

from django.db import migrations

FROM_EVENTS = """
UPDATE orders_orderstatushistory h
SET occurred_at = (e.payload->>'occurred_at')::timestamptz
FROM orders_order o, events_eventlog e
WHERE o.id = h.order_id AND o.source = 'replay' AND h.occurred_at IS NULL
  AND e.aggregate_type = 'order' AND e.aggregate_id = o.external_id
  AND e.payload->>'status' = h.to_status AND e.payload->>'reason' = h.reason
  AND e.payload ? 'occurred_at'
"""
REST = "UPDATE orders_orderstatushistory SET occurred_at = created_at WHERE occurred_at IS NULL"


def backfill(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(FROM_EVENTS)
        cursor.execute(REST)


class Migration(migrations.Migration):
    dependencies = [("orders", "0007_history_occurred_at_nullable"), ("events", "0002_deadletterretry_eventlog")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
