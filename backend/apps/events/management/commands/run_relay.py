from django.core.management.base import BaseCommand

from apps.events.relay import run_relay

from ._signals import stop_on_signals


class Command(BaseCommand):
    help = "Publish outbox events to Redis Streams until stopped (SIGTERM/SIGINT)."

    def handle(self, *args, **options):
        run_relay(stop_on_signals())
