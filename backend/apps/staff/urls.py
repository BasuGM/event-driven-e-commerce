from django.urls import path

from apps.analytics.views import AnalyticsView

from .views import DeadLetterRetryView, EventListView, EventTypesView, HealthView, OrderTimelineView

urlpatterns = [
    path("events/", EventListView.as_view(), name="staff-events"),
    path("events/types/", EventTypesView.as_view(), name="staff-event-types"),
    path("orders/<str:order_id>/events/", OrderTimelineView.as_view(), name="staff-order-events"),
    path("health/", HealthView.as_view(), name="staff-health"),
    path("analytics/", AnalyticsView.as_view(), name="staff-analytics"),
    path("dead-letters/<str:entry_id>/retry/", DeadLetterRetryView.as_view(), name="staff-dead-letter-retry"),
]
