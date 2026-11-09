import signal
import threading
import time
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max, Min

from apps.orders.models import Order
from apps.replay import services
from apps.replay.models import ReplayRun


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"Not a date (YYYY-MM-DD): {value!r}") from exc


class Command(BaseCommand):
    help = (
        "Replay imported Olist orders through the real order lifecycle as live events "
        "(copies tagged source=replay, owned by replay@example.com). Ctrl-C stops cleanly; "
        "re-running the same range resumes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="date_from", required=True, help="First purchase day (Sao Paulo), YYYY-MM-DD")
        parser.add_argument("--to", dest="date_to", required=True, help="Last purchase day (inclusive)")
        parser.add_argument("--limit", type=int, default=None, help="At most this many orders (oldest first)")
        parser.add_argument(
            "--speed", type=float, default=10.0,
            help=f"Real seconds per simulated day (0 = as fast as possible; one gap waits at most {services.MAX_SLEEP:g} s)",
        )
        parser.add_argument("--dry-run", action="store_true", help="Print the plan, write nothing")

    def handle(self, *args, date_from, date_to, limit, speed, dry_run, **options):
        if not getattr(settings, "ALLOW_DEV_SEED", False):
            raise CommandError("replay_orders only runs with dev/test settings (ALLOW_DEV_SEED).")
        start, end = parse_date(date_from), parse_date(date_to)
        if end < start:
            raise CommandError("--to is before --from.")
        if speed < 0 or (limit is not None and limit < 1):
            raise CommandError("--speed must be >= 0 and --limit >= 1.")

        sources = services.select_orders(start, end, limit)
        if not sources:
            bounds = Order.objects.filter(source=Order.Source.OLIST).aggregate(first=Min("purchased_at"), last=Max("purchased_at"))
            raise CommandError(
                f"No imported orders purchased {start}..{end}. Imported orders span "
                f"{bounds['first']:%Y-%m-%d}..{bounds['last']:%Y-%m-%d}." if bounds["first"] else
                "No imported orders at all: run `make seed` first."
            )
        plan = services.build_plan(sources)
        existing = Order.objects.filter(source=Order.Source.REPLAY, replay_of__in=list(plan.sources)).count()
        self.describe(plan, speed, existing)
        if dry_run:
            self.stdout.write("Dry run: nothing written.")
            return

        try:
            run, taken_over = services.start_run(
                date_from=start, date_to=end, speed=speed, limit=limit, orders_selected=len(sources)
            )
        except services.ReplayAlreadyRunning as exc:
            since = f" (last heartbeat {exc.run.heartbeat_at:%H:%M:%S %Z})" if exc.run else ""
            raise CommandError(
                f"{exc}{since}: one replay at a time. Stop it first (Ctrl-C). A run with no heartbeat "
                f"for {services.STALE_AFTER.seconds // 60} min (its process died) is taken over automatically."
            ) from None
        if taken_over:
            self.stdout.write(f"Replay #{taken_over.pk} had no heartbeat since {taken_over.heartbeat_at:%H:%M:%S %Z}: marked failed.")
        stop = threading.Event()

        def request_stop(signum, frame):
            self.stdout.write("\nStopping after the current step (Ctrl-C again to abort hard)...")
            stop.set()
            signal.signal(signal.SIGINT, signal.default_int_handler)

        previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
        began = time.monotonic()
        last_print = [began]

        def progress(step, run):
            now = time.monotonic()
            if now - last_print[0] >= 2:
                last_print[0] = now
                local = step.at.astimezone(services.OLIST_TZ)
                self.stdout.write(
                    f"  {local:%Y-%m-%d %H:%M} (simulated)  {run.steps_applied} steps applied, "
                    f"{run.orders_created} orders created"
                )

        self.stdout.write(f"Replay #{run.pk} started.")
        try:
            runner = services.Runner(run, plan, stop=stop, on_step=progress)
            run = runner.execute()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        if runner.taken_over:
            raise CommandError(
                f"Replay #{run.pk} was taken over by another process (now '{run.status}': {run.error or 'no reason'}). "
                f"Stopped without applying further steps; {run.steps_applied} were applied before that. "
                "Re-run the range to resume."
            )
        elapsed = time.monotonic() - began
        rate = run.steps_applied / elapsed if elapsed else 0
        self.stdout.write(
            f"Replay #{run.pk} {run.status}: {run.orders_created} orders created, "
            f"{run.steps_applied} steps applied (= events), {run.steps_skipped} already applied, "
            f"{elapsed:.1f} s ({rate:.0f} events/s written)."
        )
        if run.status == ReplayRun.Status.INTERRUPTED:
            self.stdout.write(f"Resume with the same range: --from {start} --to {end}" + (f" --limit {limit}" if limit else ""))

    def describe(self, plan, speed, existing):
        first, last = plan.steps[0].at, plan.steps[-1].at
        finals = ", ".join(f"{status} {count}" for status, count in plan.final.most_common())
        self.stdout.write(
            f"{len(plan.sources)} orders, {len(plan.steps)} steps/events, simulated "
            f"{first.astimezone(services.OLIST_TZ):%Y-%m-%d %H:%M} .. {last.astimezone(services.OLIST_TZ):%Y-%m-%d %H:%M}"
        )
        self.stdout.write(f"Final statuses: {finals}")
        if plan.adjusted:
            self.stdout.write(
                f"{plan.adjusted} order(s) canceled after shipping in Olist: replayed as canceled right "
                "after approval (shipped -> canceled is illegal)."
            )
        if existing:
            self.stdout.write(f"{existing} of them already have a replay copy: those resume where they stopped.")
        self.stdout.write(f"Estimated duration at --speed {speed:g}: {services.estimate_seconds(plan.steps, speed):.0f} s (plus processing)")
