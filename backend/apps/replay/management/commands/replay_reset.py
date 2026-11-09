from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.events.streams import redis_client
from apps.replay import services
from apps.replay.models import ReplayRun


class Command(BaseCommand):
    help = "Delete replayed orders (all, or one run's) and everything they produced; rebuild their projections."

    def add_arguments(self, parser):
        parser.add_argument("--run", type=int, default=None, help="Only this ReplayRun id")
        parser.add_argument(
            "--force", action="store_true",
            help="Reset even while a run is marked running or consumers still have events to process",
        )

    def handle(self, *args, run, force, **options):
        if not getattr(settings, "ALLOW_DEV_SEED", False):
            raise CommandError("replay_reset only runs with dev/test settings (ALLOW_DEV_SEED).")
        if run is not None and not ReplayRun.objects.filter(pk=run).exists():
            raise CommandError(f"No replay run #{run}.")
        if not force:
            try:
                with transaction.atomic():
                    taken_over = services.take_over_stale()  # a dead run (no heartbeat) is marked failed
            except services.ReplayAlreadyRunning as exc:
                raise CommandError(f"{exc}: stop it first (Ctrl-C), or rerun with --force.") from None
            if taken_over:
                self.stdout.write(f"Replay #{taken_over.pk} had no heartbeat since {taken_over.heartbeat_at:%H:%M:%S %Z}: marked failed.")
            # Events still in flight would be logged again by event_log after their orders are gone
            backlog = services.order_stream_backlog(redis_client())
            if backlog:
                raise CommandError(
                    f"Consumers still have {backlog} order event(s) to process: wait until "
                    "/staff/health shows no lag, or rerun with --force."
                )
        result = services.reset(run)
        self.stdout.write(self.style.SUCCESS(
            f"Removed {result.orders} replayed orders, {result.events} outbox events, "
            f"{result.event_logs} event log rows, {result.processed} processed-event rows and "
            f"{result.runs} run(s); rebuilt {result.days} day(s) of replay analytics."
        ))
