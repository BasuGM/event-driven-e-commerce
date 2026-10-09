from rest_framework import serializers

HEALTH_CHOICES = ["ok", "error"]


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(HEALTH_CHOICES, help_text="'ok' only if every dependency is ok")
    db = serializers.ChoiceField(HEALTH_CHOICES)
    redis = serializers.ChoiceField(HEALTH_CHOICES)


class StatsSerializer(serializers.Serializer):
    products = serializers.IntegerField()
    orders = serializers.IntegerField()
    customers = serializers.IntegerField()
    sellers = serializers.IntegerField()
