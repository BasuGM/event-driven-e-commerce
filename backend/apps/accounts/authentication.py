from rest_framework import authentication


class SessionAuthentication(authentication.SessionAuthentication):
    """DRF session auth that answers unauthenticated requests with 401 instead of 403.

    DRF only sends 401 when the auth class provides a WWW-Authenticate value. With it, the
    frontend can tell "not logged in" (401) from "CSRF / permission failure" (403).
    """

    def authenticate_header(self, request):
        return "Session"
