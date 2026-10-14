from drf_spectacular.authentication import SessionScheme


class ProjectSessionScheme(SessionScheme):
    """Document our 401-returning SessionAuthentication subclass as cookie (session) auth."""

    target_class = "apps.accounts.authentication.SessionAuthentication"
