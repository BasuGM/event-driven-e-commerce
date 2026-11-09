from rest_framework import serializers

SOURCE_CHOICES = ["all", "olist", "app", "replay"]
MONEY = {"max_digits": 14, "decimal_places": 2}


class AnalyticsFilterSerializer(serializers.Serializer):
    source = serializers.ChoiceField(SOURCE_CHOICES, default="all")
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, data):
        if data.get("date_from") and data.get("date_to") and data["date_from"] > data["date_to"]:
            raise serializers.ValidationError({"date_to": ["Must not be before date_from."]})
        return data


class KpisSerializer(serializers.Serializer):
    orders = serializers.IntegerField(help_text="Every placed order")
    canceled_orders = serializers.IntegerField(help_text="Canceled or unavailable")
    cancel_rate = serializers.FloatField(allow_null=True)
    paid_orders = serializers.IntegerField(help_text="Reached approved or later")
    gmv = serializers.DecimalField(**MONEY, help_text="Items + freight of paid orders")
    aov = serializers.DecimalField(**MONEY, allow_null=True, help_text="GMV / paid orders")
    delivered = serializers.IntegerField()
    avg_delivery_days = serializers.FloatField(allow_null=True)
    late_share = serializers.FloatField(allow_null=True, help_text="Delivered after the estimated date")


class DailyPointSerializer(serializers.Serializer):
    day = serializers.DateField()
    orders = serializers.IntegerField()
    paid_orders = serializers.IntegerField()
    gmv = serializers.DecimalField(**MONEY)


class CategoryRowSerializer(serializers.Serializer):
    slug = serializers.CharField()
    label = serializers.CharField()
    revenue = serializers.DecimalField(**MONEY)
    units = serializers.IntegerField()


class StateRowSerializer(serializers.Serializer):
    state = serializers.CharField()
    orders = serializers.IntegerField()
    gmv = serializers.DecimalField(**MONEY)


class DeliveryWeekSerializer(serializers.Serializer):
    week = serializers.DateField()
    delivered = serializers.IntegerField()
    avg_days = serializers.FloatField(allow_null=True)
    late_share = serializers.FloatField(allow_null=True)


class DashboardSerializer(serializers.Serializer):
    source = serializers.ChoiceField(SOURCE_CHOICES)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    first_day = serializers.DateField(allow_null=True, help_text="First day with data (for this source)")
    last_day = serializers.DateField(allow_null=True)
    kpis = KpisSerializer()
    daily = DailyPointSerializer(many=True)
    by_category = CategoryRowSerializer(many=True)
    by_state = StateRowSerializer(many=True)
    delivery_by_week = DeliveryWeekSerializer(many=True)
