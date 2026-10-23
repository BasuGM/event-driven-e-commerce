from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.events.streams import redis_client


class Command(BaseCommand):
    help = (
        "Delete the event streams (<EVENTS_STREAM_PREFIX>:*, with their consumer groups and the "
        "dead-letter stream). Only those keys: Celery shares the Redis DB. Dev/test only; used by "
        "`make reset` so consumers don't replay old events against a fresh database."
    )

    def handle(self, *args, **options):
        if not getattr(settings, "ALLOW_DEV_SEED", False):
            raise CommandError("clear_event_streams only runs with dev/test settings (ALLOW_DEV_SEED).")
        client = redis_client()
        keys = list(client.scan_iter(match=f"{settings.EVENTS_STREAM_PREFIX}:*", _type="stream"))
        if keys:
            client.delete(*keys)
        self.stdout.write(self.style.SUCCESS(f"Deleted {len(keys)} event stream(s)"))
