from django.core.management.base import BaseCommand

from apps.analytics.models import SOURCES
from apps.analytics.projections import rebuild


class Command(BaseCommand):
    help = (
        "Rebuild the analytics projections from orders (all days, per source). The importer emits "
        "no events, so imported orders reach the projections only through this. Safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=[s for s, _ in SOURCES], help="Only this source")

    def handle(self, *args, source=None, **options):
        for name in [source] if source else [s for s, _ in SOURCES]:
            days = rebuild(name)
            self.stdout.write(f"  {name:<7} {days:>5} day(s) rebuilt")
        self.stdout.write(self.style.SUCCESS("Analytics projections rebuilt"))
