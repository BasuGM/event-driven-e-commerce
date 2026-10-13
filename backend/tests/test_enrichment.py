import pytest

from apps.catalog.enrichment import (
    GROUPS,
    category_group,
    category_label,
    category_slug,
    generate_product_text,
)
from apps.catalog.models import Product

DIMS = {"length_cm": 16, "width_cm": 14, "height_cm": 10, "weight_g": 225}


def test_generated_text_is_pinned():
    # If this fails you changed the generator: every product name and slug (= URL) changes.
    text = generate_product_text(
        "1e9e8ef04dbcff4541ed26657ea517e5", "bed_bath_table", description_length=287, dims=DIMS
    )
    assert text.name == "Breathable Percale Throw Blanket"
    assert text.slug == "breathable-percale-throw-blanket-1e9e8ef0"
    assert text.description.startswith(
        "The Breathable Percale Throw Blanket is a breathable pick from our Bed Bath Table range."
    )
    assert "It measures 16 × 14 × 10 cm and weighs 225 g." in text.description


def test_same_input_same_output():
    args = ("0123456789abcdef0123456789abcdef", "furniture_decor")
    assert generate_product_text(*args) == generate_product_text(*args)


def test_category_shapes_vocabulary():
    for external_id in ("a" * 32, "b" * 32, "c" * 32):
        name = generate_product_text(external_id, "bed_bath_table").name
        assert name.split()[-1] in {w.split()[-1] for w in GROUPS["textiles"].nouns}


@pytest.mark.parametrize(
    "name, group",
    [
        ("bed_bath_table", "textiles"),
        ("party_supplies", "housewares"),  # contains "art" but is not media
        ("arts_and_craftmanship", "media"),
        ("fashio_female_clothing", "fashion"),
        ("costruction_tools_garden", "tools"),
        ("pc_gamer", "electronics"),
        ("cool_stuff", "general"),
        (None, "general"),
    ],
)
def test_category_group(name, group):
    assert category_group(name) == group


def test_category_label_and_slug():
    assert category_label("bed_bath_table") == "Bed Bath Table"
    assert category_slug("bed_bath_table") == "bed-bath-table"


def test_uncategorised_product_still_gets_text():
    text = generate_product_text("f" * 32, None)
    assert text.name and text.description and text.slug.endswith("-ffffffff")


@pytest.mark.django_db
def test_import_generates_unique_slugs(olist_dir):
    from django.core.management import call_command

    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=None)

    slugs = list(Product.objects.values_list("slug", flat=True))
    assert len(slugs) == len(set(slugs)) == 4
    assert not Product.objects.filter(name__startswith="Product ").exists()
