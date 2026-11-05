from rest_framework import serializers

from apps.events.models import DeadLetterRetry, EventLog


class EventLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventLog
        fields = ["event_id", "type", "aggregate_type", "aggregate_id", "stream", "schema_version",
                  "payload", "occurred_at", "received_at"]
        read_only_fields = fields


class EventFilterSerializer(serializers.Serializer):
    type = serializers.CharField(required=False, max_length=64)
    aggregate_id = serializers.CharField(required=False, max_length=64)
    date_from = serializers.DateField(required=False, help_text="occurred_at on/after this day (UTC)")
    date_to = serializers.DateField(required=False, help_text="occurred_at on/before this day (UTC)")

    def validate(self, data):
        if data.get("date_from") and data.get("date_to") and data["date_from"] > data["date_to"]:
            raise serializers.ValidationError({"date_to": ["Must not be before date_from."]})
        return data


class ConsumerStatusSerializer(serializers.Serializer):
    name = serializers.CharField()
    processed_at = serializers.DateTimeField(allow_null=True, help_text="null = not processed (yet)")


class TimelineEventSerializer(EventLogSerializer):
    consumers = ConsumerStatusSerializer(many=True)

    class Meta(EventLogSerializer.Meta):
        fields = [*EventLogSerializer.Meta.fields, "consumers"]
        read_only_fields = fields


class StaffGroupHealthSerializer(serializers.Serializer):
    stream = serializers.CharField()
    group = serializers.CharField()
    exists = serializers.BooleanField(help_text="false = the consumer hasn't created its group yet")
    consumers = serializers.IntegerField(help_text="Active consumers (read attempt within the last minute)")
    inactive_consumers = serializers.IntegerField(help_text="Names left from restarts (pruned when idle with nothing pending)")
    pending = serializers.IntegerField(help_text="Delivered, not acked yet (XPENDING)")
    lag = serializers.IntegerField(allow_null=True, help_text="Entries not delivered to the group yet")
    last_delivered_id = serializers.CharField(allow_null=True)


class StaffOutboxBacklogSerializer(serializers.Serializer):
    unpublished = serializers.IntegerField()
    oldest_unpublished_age_seconds = serializers.IntegerField(allow_null=True)


class StaffDeadLetterSerializer(serializers.Serializer):
    entry_id = serializers.CharField()
    event_id = serializers.CharField(allow_null=True)
    type = serializers.CharField(allow_null=True)
    aggregate_id = serializers.CharField(allow_null=True)
    consumer = serializers.CharField(allow_null=True)
    stream = serializers.CharField(allow_null=True)
    deliveries = serializers.IntegerField(allow_null=True)
    error = serializers.CharField(allow_null=True)
    retried_at = serializers.DateTimeField(allow_null=True)


class StaffHealthSerializer(serializers.Serializer):
    groups = StaffGroupHealthSerializer(many=True)
    outbox = StaffOutboxBacklogSerializer()
    dead_letters = StaffDeadLetterSerializer(many=True)


class DeadLetterRetrySerializer(serializers.ModelSerializer):
    retried_by = serializers.EmailField(source="retried_by.email", allow_null=True, read_only=True)
    created = serializers.BooleanField(help_text="false = this entry had already been retried (no new delivery)")

    class Meta:
        model = DeadLetterRetry
        fields = ["dlq_entry_id", "event_id", "consumer", "stream", "new_entry_id", "retried_by", "retried_at", "created"]
        read_only_fields = fields
