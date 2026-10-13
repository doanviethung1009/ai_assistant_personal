from __future__ import annotations


class DomainError(Exception):
    """Lỗi nghiệp vụ, được map sang HTTP ở tầng router.

    `code` (tuỳ chọn) là mã máy đọc được, trả kèm `detail` để web phân biệt các lỗi cùng status
    (vd 401 `token_invalid` và `user_inactive`).
    """

    status_code = 400
    code: str | None = None

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class UnauthorizedError(DomainError):
    status_code = 401


class ForbiddenError(DomainError):
    """Có đăng nhập nhưng không đủ quyền. Task ngoài phạm vi nhìn thấy KHÔNG dùng lỗi này:
    phải là NotFoundError (404) để không lộ sự tồn tại."""

    status_code = 403
    code = "forbidden"


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class ValidationError(DomainError):
    status_code = 422


class TooManyRequestsError(DomainError):
    status_code = 429
