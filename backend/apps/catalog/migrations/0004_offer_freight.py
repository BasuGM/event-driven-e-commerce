"""Add Offer.freight (nullable) and backfill it from Olist order items.

Frozen backfill: plain SQL, no app imports. Same exact-decimal median as the offer price.
0005 makes the column required.
"""

from django.db import migrations, models

BACKFILL = """
UPDATE catalog_offer ofr
SET freight = v.freight
FROM (
    SELECT oi.product_id, oi.seller_id,
           round(
               (percentile_disc(0.5) WITHIN GROUP (ORDER BY oi.freight_value)
                + percentile_disc(0.5) WITHIN GROUP (ORDER BY oi.freight_value DESC)) / 2,
               2
           ) AS freight
    FROM orders_orderitem oi
    GROUP BY oi.product_id, oi.seller_id
) v
WHERE ofr.product_id = v.product_id AND ofr.seller_id = v.seller_id
"""


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_enforce_slugs_and_indexes"), ("orders", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="freight",
            field=models.DecimalField(
                decimal_places=2, help_text="Median Olist freight per unit for this pair",
                max_digits=12, null=True,
            ),
        ),
        migrations.RunSQL(BACKFILL, migrations.RunSQL.noop),
        # Offers always come from order items, but be safe for any orphan row
        migrations.RunSQL("UPDATE catalog_offer SET freight = 0 WHERE freight IS NULL", migrations.RunSQL.noop),
    ]
