"""Domain errors: plain exceptions raised by services, mapped to HTTP by the exception handler.

Services stay framework-agnostic (callable from Celery tasks, commands and tests); views never
need try/except for these.
"""

from __future__ import annotations


class DomainError(Exception):
    status_code = 409
    code = "conflict"

    def __init__(self, detail: str, **extra):
        super().__init__(detail)
        self.detail = detail
        self.extra = extra

    def payload(self) -> dict:
        return {"code": self.code, "detail": self.detail, **self.extra}


class InvalidTransition(DomainError):
    code = "invalid_transition"


class OutOfStock(DomainError):
    code = "out_of_stock"


class ReservationExpired(DomainError):
    code = "reservation_expired"


class IdempotencyConflict(DomainError):
    code = "idempotency_conflict"


class EmptyCart(DomainError):
    status_code = 400
    code = "empty_cart"
