from django.db import models
from django.utils import timezone


class ReplayRun(models.Model):
    """One invocation of ``replay_orders``. Copies it creates point here (``Order.replay_run``);
    a later run that resumes them advances them but leaves them on their original run."""

    class Status(models.TextChoices):
        RUNNING = "running"
        COMPLETED = "completed"
        INTERRUPTED = "interrupted"  # Ctrl-C / SIGTERM: re-run the same range to resume
        FAILED = "failed"

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RUNNING)
    date_from = models.DateField()
    date_to = models.DateField()
    speed = models.FloatField(help_text="Real seconds per simulated day")
    limit = models.PositiveIntegerField(null=True, blank=True)
    cursor_at = models.DateTimeField(
        null=True, blank=True, help_text="Simulated time of the last step applied"
    )
    orders_selected = models.PositiveIntegerField(default=0)
    orders_created = models.PositiveIntegerField(default=0)
    steps_applied = models.PositiveIntegerField(default=0)
    steps_skipped = models.PositiveIntegerField(default=0, help_text="Already applied (resume)")
    error = models.TextField(blank=True, default="")
    heartbeat_at = models.DateTimeField(
        default=timezone.now, help_text="Last sign of life; a running run silent for long is taken over"
    )

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            # At most one running replay, enforced by the database: two processes starting at
            # once can't both pass a read-then-insert check (services.start_run)
            models.UniqueConstraint(
                fields=["status"], condition=models.Q(status="running"), name="one_running_replay"
            ),
        ]

    def __str__(self) -> str:
        return f"Replay #{self.pk} {self.date_from}..{self.date_to} ({self.status})"
