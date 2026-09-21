from __future__ import annotations


class DomainError(Exception):
    """Lỗi nghiệp vụ, được map sang HTTP ở tầng router."""

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class ValidationError(DomainError):
    status_code = 422
