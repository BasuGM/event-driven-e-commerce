"""0004 backfilled every offer, so freight can become required."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0004_offer_freight")]

    operations = [
        migrations.AlterField(
            model_name="offer",
            name="freight",
            field=models.DecimalField(
                decimal_places=2, help_text="Median Olist freight per unit for this pair", max_digits=12
            ),
        ),
    ]
