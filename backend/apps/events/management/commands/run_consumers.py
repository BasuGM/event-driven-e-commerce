import threading

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.events.consumers import CONSUMERS
from apps.events.readiness import wait_for_event_tables

from ._signals import stop_on_signals


class Command(BaseCommand):
    help = "Run the event consumers (one thread each) until stopped (SIGTERM/SIGINT)."

    def add_arguments(self, parser):
        parser.add_argument("--only", nargs="+", choices=sorted(CONSUMERS), help="Run just these consumers")

    def handle(self, *args, only=None, **options):
        names = only or sorted(CONSUMERS)
        stop = stop_on_signals()
        # Not before migrations: a consumer without its tables would fail and dead-letter
        # every event it reads.
        if not wait_for_event_tables(stop, who="Consumers"):
            return
        connection.close()  # the threads open their own connections
        threads = [
            threading.Thread(target=self._run, args=(CONSUMERS[name], stop), name=name, daemon=True)
            for name in names
        ]
        for thread in threads:
            thread.start()
        while any(t.is_alive() for t in threads):
            # Wake up regularly so the main thread can receive signals
            for thread in threads:
                thread.join(timeout=0.5)
            if stop.is_set():
                for thread in threads:
                    thread.join()
        if not stop.is_set():
            raise CommandError("A consumer thread exited unexpectedly")

    @staticmethod
    def _run(consumer_class, stop):
        try:
            consumer_class().run(stop)
        finally:
            connection.close()  # each thread has its own DB connection
