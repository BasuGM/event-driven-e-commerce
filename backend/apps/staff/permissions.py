from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission


class IsStaffOr404(BasePermission):
    """Staff tools are invisible to everyone else: anonymous and non-staff both get 404
    (not 401/403, which would reveal that the endpoint exists)."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_staff):
            raise NotFound
        return True
