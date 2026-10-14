from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .errors import DomainError


def exception_handler(exc, context):
    """DRF's handler, plus DomainError -> {code, detail, ...} with the error's status code."""
    if isinstance(exc, DomainError):
        return Response(exc.payload(), status=exc.status_code)
    return drf_exception_handler(exc, context)
