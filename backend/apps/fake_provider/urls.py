from django.urls import path

from .views import hosted_page

urlpatterns = [path("pay/<str:intent_id>/", hosted_page, name="fake-provider-pay")]
