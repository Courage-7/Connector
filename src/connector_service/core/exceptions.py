"""Safe domain exceptions exposed through the HTTP error envelope."""

from collections.abc import Mapping
from typing import Any


class ServiceError(Exception):
    """Base exception containing only client-safe fields."""

    code = "service_error"
    status_code = 500
    message = "The service could not complete the request."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.message)
        self.safe_message = message or self.message
        self.details = dict(details or {})


class AuthenticationError(ServiceError):
    code = "authentication_failed"
    status_code = 401
    message = "Valid authentication is required."


class AuthorizationError(ServiceError):
    code = "action_not_allowed"
    status_code = 403
    message = "This project is not allowed to perform the requested action."


class NotFoundError(ServiceError):
    code = "not_found"
    status_code = 404
    message = "The requested object was not found."


class ConflictError(ServiceError):
    code = "conflict"
    status_code = 409
    message = "The request conflicts with existing state."


class InvalidRequestError(ServiceError):
    code = "invalid_request"
    status_code = 422
    message = "The request is invalid."


class InvalidCursorError(InvalidRequestError):
    code = "invalid_cursor"
    message = "The pagination cursor is invalid or does not match this query."


class ProviderAccessError(ServiceError):
    code = "provider_access_denied"
    status_code = 502
    message = "The provider rejected the configured credentials or access policy."


class ProviderRequestError(ServiceError):
    code = "provider_request_failed"
    status_code = 502
    message = "The provider could not complete the approved request."


class ProviderUnavailableError(ServiceError):
    code = "provider_unavailable"
    status_code = 503
    message = "The provider is temporarily unavailable."
