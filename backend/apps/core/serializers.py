from rest_framework import serializers

HEALTH_CHOICES = ["ok", "error"]


class OutboxBacklogSerializer(serializers.Serializer):
    unpublished = serializers.IntegerField(help_text="Outbox events the relay hasn't published yet")
    oldest_unpublished_age_seconds = serializers.IntegerField(
        allow_null=True, help_text="Age of the oldest unpublished event (null when none)"
    )


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(HEALTH_CHOICES, help_text="'ok' only if every dependency is ok")
    db = serializers.ChoiceField(HEALTH_CHOICES)
    redis = serializers.ChoiceField(HEALTH_CHOICES)
    outbox = OutboxBacklogSerializer(
        allow_null=True,
        help_text="Informational (doesn't affect status): a growing backlog means the relay is stuck. "
        "Null when the database is down.",
    )


class StatsSerializer(serializers.Serializer):
    products = serializers.IntegerField()
    orders = serializers.IntegerField()
    customers = serializers.IntegerField()
    sellers = serializers.IntegerField()
