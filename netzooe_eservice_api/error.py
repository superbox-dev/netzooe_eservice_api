# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0
"""Netz OÖ eService API error classes."""

from http import HTTPStatus


class APIError(Exception):
    """Base error of the Netz OÖ eService API, e.g. for HTTP and connection errors."""

    def __init__(
        self,
        message: str = "",
        /,
        *,
        status: HTTPStatus | None = None,
    ) -> None:
        """Initialize an API error.

        Parameters
        ----------
        message
            Error message. Is replaced by the HTTP status description if a status is given.
        status
            HTTP status associated with the error.

        """
        _message: str = message

        if status:
            _message = f"{status} {status.phrase}: {status.description}"

        self.message: str = _message
        self.status: int | None = status

    def __str__(self) -> str:
        """Return the error message."""
        return self.message


class InvalidJsonError(APIError):
    """The response of the eService portal is not valid JSON, e.g. the maintenance page."""


class AuthenticationError(APIError):
    """The credentials were rejected by the eService portal (HTTP 401)."""
