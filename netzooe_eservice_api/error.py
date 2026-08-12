"""KEBA KeEnergy API error classes."""

from http import HTTPStatus


class APIError(Exception):
    """API error."""

    def __init__(
        self,
        message: str = "",
        /,
        *,
        status: HTTPStatus | None = None,
    ) -> None:
        """Initialize an API error with an optional HTTP status."""
        _message: str = message

        if status:
            _message = f"{status} {status.phrase}: {status.description}"

        self.message: str = _message
        self.status: int | None = status

    def __str__(self) -> str:
        """Return the error message."""
        return self.message


class InvalidJsonError(APIError):
    """Invalid JSON data error."""


class AuthenticationError(APIError):
    """Invalid credentials error."""
