"""
Application-specific exception hierarchy.

Services raise these domain exceptions; a single FastAPI handler (registered in
main.py) translates them into the standard error envelope. HTTP status codes
stay out of the service layer entirely, which is what lets services be reused
outside a web context (a Celery task, `scripts/train_model.py`).

CHANGE LOG (v2.0):
  - Every exception now carries a stable, machine-readable `code`. Previously
    clients could only string-match on `detail`, so any copy edit to a message
    was a silent breaking change for the frontend. The UI now branches on
    `error.code` (see stockvision-frontend/src/lib/api.ts).
  - REMOVED InvalidCredentialsException / InvalidTokenException — no auth, no
    credentials.
  - ADDED ValidationException, ConflictException, ExternalServiceException,
    RateLimitException and UnsupportedOperationException, so every failure path
    has a typed home instead of a bare HTTPException.
"""
from typing import Any


class AppException(Exception):
    """Base class for all domain exceptions."""

    status_code: int = 500
    code: str = "internal_error"
    detail: str = "An unexpected error occurred."

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.detail
        self.code = code or self.code
        self.context = context or {}
        super().__init__(self.detail)

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        """The exact JSON body returned to clients — see main.py's handler."""
        payload: dict[str, Any] = {
            "error": {"code": self.code, "message": self.detail, "status": self.status_code}
        }
        if self.context:
            payload["error"]["context"] = self.context
        if request_id:
            payload["error"]["request_id"] = request_id
        return payload


class BadRequestException(AppException):
    status_code = 400
    code = "bad_request"
    detail = "The request was malformed or contained invalid parameters."


class ValidationException(AppException):
    status_code = 422
    code = "validation_error"
    detail = "The request failed validation."


class NotFoundException(AppException):
    status_code = 404
    code = "not_found"
    detail = "The requested resource does not exist."


class AlreadyExistsException(AppException):
    status_code = 409
    code = "already_exists"
    detail = "A resource with these identifying attributes already exists."


class ConflictException(AppException):
    status_code = 409
    code = "conflict"
    detail = "The request conflicts with the current state of the resource."


class ForbiddenException(AppException):
    status_code = 403
    code = "forbidden"
    detail = "This operation is not permitted."


class InsufficientDataException(AppException):
    status_code = 422
    code = "insufficient_data"
    detail = "There is not enough historical data to complete this operation."


class ModelNotTrainedException(AppException):
    status_code = 422
    code = "model_not_trained"
    detail = "No trained model is available for this symbol and task."


class UnsupportedOperationException(AppException):
    status_code = 501
    code = "unsupported_operation"
    detail = "This operation is not supported by the current configuration."


class ExternalServiceException(AppException):
    status_code = 502
    code = "external_service_error"
    detail = "An upstream provider failed to respond successfully."


class RateLimitException(AppException):
    status_code = 429
    code = "rate_limited"
    detail = "Too many requests. Please slow down."
