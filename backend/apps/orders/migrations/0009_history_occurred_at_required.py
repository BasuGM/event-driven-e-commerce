from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0008_backfill_history_occurred_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderstatushistory',
            name='occurred_at',
            field=models.DateTimeField(),
        ),
    ]
