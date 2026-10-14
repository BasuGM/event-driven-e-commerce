from django.urls import path

from .views import CsrfView, LoginView, LogoutView, MeView, RegisterView

urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
]
