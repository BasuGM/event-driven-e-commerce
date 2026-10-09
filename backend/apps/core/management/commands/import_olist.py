import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.olist_import import (
    DEFAULT_SEED,
    DEFAULT_SMALL_ORDER_COUNT,
    MissingFilesError,
    OlistImporter,
    format_summary,
)


class Command(BaseCommand):
    help = "Import the Olist Brazilian E-Commerce CSVs (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--size", choices=["small", "large"], default="small")
        parser.add_argument(
            "--data-dir",
            default=None,
            help="Directory containing the Olist CSVs (default: settings.OLIST_DATA_DIR)",
        )
        parser.add_argument(
            "--order-count",
            type=int,
            default=DEFAULT_SMALL_ORDER_COUNT,
            help="Orders to sample in --size small",
        )
        parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Sampling seed")

    def handle(self, *args, **options):
        importer = OlistImporter(
            options["data_dir"] or settings.OLIST_DATA_DIR,
            options["size"],
            order_count=options["order_count"],
            seed=options["seed"],
            stdout=self.stdout,
        )
        started = time.monotonic()
        try:
            results = importer.run()
        except MissingFilesError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write("")
        self.stdout.write(format_summary(results))
        self.stdout.write(
            self.style.SUCCESS(
                f"Olist import ({options['size']}) finished in {time.monotonic() - started:.1f}s"
            )
        )
