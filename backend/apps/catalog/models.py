from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Olist (Portuguese) name")
    name_english = models.CharField(max_length=100)

    class Meta:
        ordering = ["name_english"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name_english


class Seller(models.Model):
    external_id = models.CharField(max_length=32, unique=True)
    zip_code_prefix = models.CharField(max_length=5)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, db_index=True)

    def __str__(self) -> str:
        return f"{self.external_id[:8]} ({self.city}/{self.state})"


class Product(models.Model):
    external_id = models.CharField(max_length=32, unique=True)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    name_length = models.PositiveIntegerField(null=True, blank=True)
    description_length = models.PositiveIntegerField(null=True, blank=True)
    photos_qty = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_g = models.PositiveIntegerField(null=True, blank=True)
    length_cm = models.PositiveIntegerField(null=True, blank=True)
    height_cm = models.PositiveIntegerField(null=True, blank=True)
    width_cm = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self) -> str:
        return self.external_id
