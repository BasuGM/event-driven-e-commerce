from django.urls import path

from .views import HealthView, StatsView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("stats/", StatsView.as_view(), name="stats"),
]
