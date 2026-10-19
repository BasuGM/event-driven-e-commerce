"""Deterministic, category-aware product names, slugs and descriptions.

Olist products have no name or description, so we generate them. The output is a pure function
of the product's external_id and category, seeded through sha256 (never the global ``random``),
so the same product always gets the same text regardless of import order or batch size.

Changing anything here renames products and changes slugs (= URLs). Treat edits like a data
migration: the determinism tests pin example outputs and will fail on purpose.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from django.utils.text import slugify


@dataclass(frozen=True)
class Vocabulary:
    adjectives: tuple[str, ...]
    materials: tuple[str, ...]
    nouns: tuple[str, ...]
    selling_points: tuple[str, ...]


GROUPS: dict[str, Vocabulary] = {
    "textiles": Vocabulary(
        ("Soft", "Plush", "Breathable", "Luxe", "Cozy", "Classic", "Hotel-Style", "Lightweight"),
        ("Percale", "Cotton", "Microfiber", "Linen", "Satin", "Flannel", "Bamboo", "Jacquard"),
        ("Duvet Cover Set", "Sheet Set", "Bath Towel", "Pillowcase Pair", "Quilt", "Table Runner",
         "Throw Blanket", "Bath Mat", "Comforter", "Curtain Panel"),
        ("stays soft wash after wash", "is woven for everyday comfort",
         "resists pilling and fading", "brings a calm, hotel-like feel to the room"),
    ),
    "furniture": Vocabulary(
        ("Modern", "Rustic", "Compact", "Scandinavian", "Industrial", "Elegant", "Minimalist"),
        ("Oak", "Walnut", "Pine", "Steel-Frame", "Rattan", "Lacquered", "MDF"),
        ("Side Table", "Bookshelf", "Armchair", "TV Stand", "Nightstand", "Wall Shelf",
         "Dining Chair", "Mattress", "Wardrobe", "Desk", "Coffee Table", "Mirror Frame"),
        ("assembles in minutes", "is built for daily use", "fits small spaces",
         "adds warmth to any room"),
    ),
    "housewares": Vocabulary(
        ("Everyday", "Stackable", "Premium", "Space-Saving", "Durable", "Festive", "Handy"),
        ("Stainless", "Ceramic", "Glass", "Bamboo", "Silicone", "Enamel"),
        ("Storage Jar Set", "Cookware Set", "Utensil Holder", "Serving Bowl", "Dish Rack",
         "Cutting Board", "Thermal Bottle", "Decor Ornament", "Party Kit", "Vase"),
        ("is dishwasher safe", "keeps the kitchen organised", "makes a thoughtful gift",
         "is easy to clean"),
    ),
    "appliances": Vocabulary(
        ("Compact", "Digital", "Quiet", "Energy-Saving", "Turbo", "Smart", "Pro"),
        ("110V", "220V", "Bivolt", "Inox", "Multi-Speed", "1200W"),
        ("Blender", "Coffee Maker", "Air Fryer", "Electric Kettle", "Toaster", "Mixer",
         "Fan", "Vacuum Cleaner", "Microwave", "Steam Iron", "Air Conditioner"),
        ("heats up in seconds", "saves energy every day", "is simple to operate",
         "comes with a 12-month warranty"),
    ),
    "electronics": Vocabulary(
        ("Wireless", "Portable", "Ultra", "Smart", "Gaming", "HD", "Fast-Charge"),
        ("Bluetooth", "USB-C", "Wi-Fi", "4K", "Noise-Cancelling", "RGB"),
        ("Headphones", "Speaker", "Phone Case", "Charger", "Keyboard", "Mouse", "Webcam",
         "Router", "Controller", "Power Bank", "Tablet Stand", "Printer Cartridge"),
        ("pairs instantly with your devices", "delivers crisp, reliable performance",
         "is built to last", "works out of the box"),
    ),
    "beauty": Vocabulary(
        ("Nourishing", "Gentle", "Radiant", "Hydrating", "Fresh", "Intense", "Daily"),
        ("Argan", "Vitamin C", "Aloe", "Rosewater", "Shea", "Hyaluronic", "Floral"),
        ("Face Serum", "Moisturiser", "Shampoo", "Eau de Parfum", "Body Lotion", "Hair Mask",
         "Lip Balm", "Sunscreen", "Conditioner", "Baby Wipes"),
        ("is dermatologically tested", "absorbs quickly without residue",
         "leaves a light, lasting scent", "suits all skin types"),
    ),
    "fashion": Vocabulary(
        ("Classic", "Slim-Fit", "Casual", "Vintage", "Sporty", "Everyday", "Elegant"),
        ("Denim", "Leather", "Cotton", "Knit", "Canvas", "Suede", "Linen"),
        ("T-Shirt", "Sneakers", "Backpack", "Wallet", "Watch", "Dress", "Jacket", "Sandals",
         "Handbag", "Swimsuit", "Suitcase", "Belt"),
        ("is comfortable all day", "pairs with almost anything", "keeps its shape",
         "is made to be worn often"),
    ),
    "sports": Vocabulary(
        ("Pro", "Lightweight", "Training", "Outdoor", "Performance", "All-Terrain", "Grip"),
        ("Neoprene", "Carbon", "Aluminium", "Mesh", "EVA Foam", "Rubber"),
        ("Yoga Mat", "Dumbbell Set", "Cycling Gloves", "Water Bottle", "Camping Lantern",
         "Football", "Resistance Bands", "Fishing Rod", "Skipping Rope", "Tent"),
        ("is ready for your next workout", "handles tough conditions", "packs down small",
         "helps you train consistently"),
    ),
    "toys": Vocabulary(
        ("Colourful", "Educational", "Interactive", "Cuddly", "Creative", "Safe", "Musical"),
        ("Wooden", "Plush", "BPA-Free", "Magnetic", "Foam"),
        ("Building Blocks", "Puzzle", "Teddy Bear", "Activity Gym", "Baby Bottle", "Toy Car",
         "Stroller Organiser", "Board Game", "Doll", "Teether"),
        ("sparks curiosity and play", "is tested for little hands", "grows with your child",
         "makes playtime easy"),
    ),
    "auto": Vocabulary(
        ("Heavy-Duty", "Universal", "Premium", "Quick-Fit", "Weatherproof", "Sport"),
        ("Rubber", "Leather", "Chrome", "LED", "Carbon-Look"),
        ("Floor Mat Set", "Seat Cover", "Phone Mount", "Wiper Blades", "Headlight Bulb",
         "Steering Wheel Cover", "Car Charger", "Tyre Inflator", "Organiser"),
        ("fits most vehicles", "installs without tools", "handles daily driving",
         "keeps the car tidy"),
    ),
    "tools": Vocabulary(
        ("Heavy-Duty", "Professional", "Cordless", "Precision", "Compact", "Industrial"),
        ("Steel", "Brass", "Fibreglass", "LED", "Galvanised", "18V"),
        ("Drill", "Tool Kit", "Garden Hose", "Work Light", "Safety Gloves", "Padlock",
         "Ladder", "Pruning Shears", "Spirit Level", "Light Fixture", "Security Camera"),
        ("is made for serious jobs", "is easy to handle", "resists rust and wear",
         "meets safety standards"),
    ),
    "food": Vocabulary(
        ("Artisan", "Organic", "Gourmet", "Classic", "Premium", "Natural"),
        ("Brazilian", "Roasted", "Spiced", "Cold-Pressed", "Aged"),
        ("Coffee Beans", "Olive Oil", "Chocolate Box", "Tea Selection", "Craft Beer Pack",
         "Honey Jar", "Spice Kit", "Wine Bottle"),
        ("is sourced from trusted producers", "is packed fresh", "makes a great gift",
         "brings real flavour to the table"),
    ),
    "media": Vocabulary(
        ("Illustrated", "Collector's", "Classic", "Essential", "Complete", "Deluxe"),
        ("Hardcover", "Paperback", "Spiral", "Vinyl", "Acoustic", "Watercolour"),
        ("Notebook Set", "Novel", "Technical Guide", "Art Supplies Kit", "Guitar", "Album",
         "Blu-ray Box", "Pen Set", "Sketchbook", "Keyboard Stand"),
        ("is a favourite with readers", "inspires daily creativity",
         "is beautifully produced", "rewards repeat use"),
    ),
    "pets": Vocabulary(
        ("Comfy", "Durable", "Washable", "Interactive", "Natural", "Adjustable"),
        ("Plush", "Nylon", "Rubber", "Orthopaedic"),
        ("Dog Bed", "Cat Scratcher", "Leash", "Chew Toy", "Feeding Bowl", "Pet Carrier",
         "Grooming Brush"),
        ("pets love it", "is easy to clean", "is built for daily play", "keeps pets comfy"),
    ),
    "general": Vocabulary(
        ("Essential", "Premium", "Classic", "Practical", "Versatile", "Modern"),
        ("Multi-Use", "Compact", "Deluxe", "Signature"),
        ("Gift Set", "Organiser", "Accessory Kit", "Bundle", "Collection"),
        ("is ready to use", "is well made", "makes a great gift", "is great value"),
    ),
}

# Ordered (needle, group) rules over the English category name; first match wins. A needle with
# an underscore matches as a substring; a single word matches the start of any word, so "art"
# matches "arts_and_craftmanship" but not "party_supplies".
_GROUP_RULES: tuple[tuple[str, str], ...] = (
    ("bed_bath", "textiles"), ("home_confort", "textiles"), ("home_comfort", "textiles"),
    ("furniture", "furniture"),
    ("appliances", "appliances"), ("air_conditioning", "appliances"),
    ("computers", "electronics"), ("electronics", "electronics"), ("telephony", "electronics"),
    ("tablets", "electronics"), ("audio", "electronics"), ("consoles", "electronics"),
    ("cine_photo", "electronics"), ("pc_gamer", "electronics"),
    ("health_beauty", "beauty"), ("perfumery", "beauty"), ("diapers", "beauty"),
    ("fashio", "fashion"), ("luggage", "fashion"), ("watches", "fashion"),
    ("sports", "sports"),
    ("toys", "toys"), ("baby", "toys"),
    ("auto", "auto"),
    ("construction", "tools"), ("costruction", "tools"), ("garden_tools", "tools"),
    ("agro", "tools"), ("industry", "tools"), ("security", "tools"),
    ("food", "food"), ("drink", "food"),
    ("book", "media"), ("stationery", "media"), ("music", "media"), ("cds_dvds", "media"),
    ("dvds", "media"), ("art", "media"),
    ("pet", "pets"),
    ("housewares", "housewares"), ("la_cuisine", "housewares"), ("christmas", "housewares"),
    ("party", "housewares"), ("flowers", "housewares"),
    ("cozinha", "housewares"),  # untranslated "portateis_cozinha_e_preparadores_de_alimentos"
)


def category_group(name_english: str | None) -> str:
    """Map an Olist English category name to one of ``GROUPS`` (``general`` if unknown)."""
    name = (name_english or "").lower()
    words = name.split("_")
    for needle, group in _GROUP_RULES:
        if needle in name if "_" in needle else any(w.startswith(needle) for w in words):
            return group
    return "general"


# Typos in Olist's category names. Fixed only in the label: slugs (= URLs) keep the raw name.
_LABEL_WORD_FIXES = {"fashio": "fashion", "costruction": "construction", "confort": "comfort"}


def category_label(name_english: str) -> str:
    words = name_english.replace("_", " ").split()
    return " ".join(_LABEL_WORD_FIXES.get(w.lower(), w) for w in words).title()


def _article(word: str) -> str:
    """'a' or 'an' by sound for our adjectives: "an elegant", "an ultra", but "a universal"."""
    lower = word.lower()
    if lower.startswith(("uni", "use", "eu", "one")):
        return "a"
    return "an" if lower[:1] in "aeiou" else "a"


def category_slug(name_english: str) -> str:
    return slugify(name_english.replace("_", "-"))


def _rng(external_id: str) -> random.Random:
    # random.Random(int) is stable across Python versions; sha256 spreads similar IDs apart.
    digest = hashlib.sha256(external_id.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


@dataclass(frozen=True)
class ProductText:
    name: str
    slug: str
    description: str


def _dimensions_sentence(dims: dict[str, int | None]) -> str | None:
    length, width, height = dims.get("length_cm"), dims.get("width_cm"), dims.get("height_cm")
    weight = dims.get("weight_g")
    parts = []
    if length and width and height:
        parts.append(f"measures {length} × {width} × {height} cm")
    if weight:
        parts.append(f"weighs {weight / 1000:.1f} kg" if weight >= 1000 else f"weighs {weight} g")
    if not parts:
        return None
    return "It " + " and ".join(parts) + "."


def generate_product_text(
    external_id: str,
    category_name_english: str | None,
    *,
    description_length: int | None = None,
    dims: dict[str, int | None] | None = None,
) -> ProductText:
    rng = _rng(external_id)
    vocab = GROUPS[category_group(category_name_english)]
    adjective = rng.choice(vocab.adjectives)
    material = rng.choice(vocab.materials)
    noun = rng.choice(vocab.nouns)
    name = f"{adjective} {material} {noun}"
    slug = f"{slugify(name)}-{external_id[:8]}"

    category = category_label(category_name_english) if category_name_english else "everyday"
    points = list(vocab.selling_points)
    rng.shuffle(points)
    sentences = [
        f"The {name} is {_article(adjective)} {adjective.lower()} pick from our {category} range.",
        f"Its {material} design {points[0]}.",
    ]
    if dimension_text := _dimensions_sentence(dims or {}):
        sentences.append(dimension_text)
    # Follow Olist's description length loosely (clamped) so some descriptions are longer.
    target = min(max(description_length or 0, 160), 700)
    for point in points[1:]:
        if len(" ".join(sentences)) >= target:
            break
        sentences.append(f"Customers like that it {point}.")
    return ProductText(name=name, slug=slug, description=" ".join(sentences))
