from app.core.exceptions.base import AppError


class BusinessError(AppError):
    status_code = 400
    code = 400


class AuthenticationError(AppError):
    status_code = 401
    code = 401


class AuthorizationError(AppError):
    status_code = 403
    code = 403


class NotFoundError(AppError):
    status_code = 404
    code = 404


class ConflictError(AppError):
    status_code = 409
    code = 409
