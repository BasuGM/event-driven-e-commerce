"""Step 1 of 2 for the enriched catalog: add columns as nullable, create Offer, backfill.

The backfill is frozen on purpose: it imports no app code, so later edits to
apps.catalog.enrichment cannot change what this migration does. Products get placeholder
names/slugs here; ``import_olist`` writes the real generated values on the next seed.
"""

import django.contrib.postgres.search
import django.db.models.deletion
from django.db import migrations, models
from django.utils.text import slugify


def backfill(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")

    categories = list(Category.objects.all())
    for category in categories:
        category.slug = slugify(category.name_english.replace("_", "-"))
    Category.objects.bulk_update(categories, ["slug"], batch_size=1000)

    products = list(Product.objects.only("pk", "external_id"))
    for product in products:
        product.name = f"Product {product.external_id[:8]}"
        product.slug = f"product-{product.external_id}"
    Product.objects.bulk_update(products, ["name", "slug"], batch_size=2000)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="category",
            name="slug",
            field=models.SlugField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="name",
            field=models.CharField(max_length=200, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="slug",
            field=models.SlugField(max_length=220, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="description",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="product",
            name="image_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="min_price",
            field=models.DecimalField(
                blank=True, decimal_places=2, help_text="Lowest price among in-stock offers",
                max_digits=12, null=True,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="rating_avg",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=3, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="rating_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="product",
            name="sales_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="product",
            name="first_sold_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(editable=False, null=True),
        ),
        migrations.CreateModel(
            name="Offer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("price", models.DecimalField(decimal_places=2, help_text="Median Olist item price for this pair", max_digits=12)),
                ("stock", models.PositiveIntegerField()),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="catalog.product")),
                ("seller", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="offers", to="catalog.seller")),
            ],
            options={
                "ordering": ["price"],
                "indexes": [models.Index(fields=["product", "price"], name="offer_product_price_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("product", "seller"), name="uniq_offer_product_seller")
                ],
            },
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
