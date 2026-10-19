# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0
"""Asynchronous client for the Netz OÖ eService API."""

import asyncio
from collections.abc import Iterable
from contextlib import suppress
from enum import Enum
from http import HTTPStatus
from json.decoder import JSONDecodeError
from typing import Any
from typing import Literal
from typing import NotRequired
from typing import TypedDict
from urllib.parse import quote

from aiohttp import ClientError
from aiohttp import ClientSession
from aiohttp import ContentTypeError

from netzooe_eservice_api.constants import COMMON_HEADERS
from netzooe_eservice_api.constants import ESERVICE_PORTAL
from netzooe_eservice_api.constants import ESERVICE_PORTAL_API
from netzooe_eservice_api.constants import ConsentRequestsStatus
from netzooe_eservice_api.constants import ConsentsStatus
from netzooe_eservice_api.constants import ConsumptionsDimension
from netzooe_eservice_api.constants import ConsumptionsProfilesBranch
from netzooe_eservice_api.constants import Granularity
from netzooe_eservice_api.constants import ProfileType
from netzooe_eservice_api.error import APIError
from netzooe_eservice_api.error import AuthenticationError
from netzooe_eservice_api.error import InvalidJsonError

# Shapes of the JSON responses, `_request()` checks the response against the expected one.
type _JSONResponse = dict[str, Any] | list[dict[str, Any]]


class Pod(TypedDict):
    """Point of delivery (POD) used to request a consumption profile.

    Attributes
    ----------
    contract_account_number
        Contract account number of the point of delivery.
    energy_community_id
        Optional ID of the energy community. Only sent if it is set.
    profile_type
        Profile type, e.g. from `consumptions_profiles()`. A `ProfileType` member or its string value.
    best_available_granularity
        Best available granularity of the measured values, e.g. from `consumptions_profiles()`.
        A `Granularity` member or its string value.
    meter_point_administration_number
        Meter point administration number (Zählpunktnummer).
    date_from
        Start of the time range.
    date_to
        End of the time range.

    """

    contract_account_number: str
    energy_community_id: NotRequired[str | None]
    profile_type: ProfileType | str
    best_available_granularity: Granularity | str
    meter_point_administration_number: str
    date_from: str
    date_to: str


class NetzOOEeServiceAPI:
    """Asynchronous client for the Netz OÖ eService API.

    The client logs in automatically on the first request and again once if the session has expired.

    """

    def __init__(
        self,
        username: str,
        password: str,
        *,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize the API client.

        Parameters
        ----------
        username
            Username of the eService portal.
        password
            Password of the eService portal.
        session
            Optional aiohttp client session. A passed session is never closed by the client.
            If no session is passed, the client creates its own and closes it on `logout()` and if a login fails.

        Examples
        --------
        >>> async with ClientSession() as session:
        ...     client = NetzOOEeServiceAPI(
        ...         username="test",
        ...         password="test",
        ...         session=session,
        ...     )

        """
        self._username = username
        self._password = password

        self._session: ClientSession | None = session
        self._custom_session: bool = session is None

        self.xsrf_token: str = ""
        self._login_task: asyncio.Task[None] | None = None

    async def _get_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            # Also for a passed session that is already closed. The new session is owned by the client.
            self._session = ClientSession()
            self._custom_session = True
            # The new session has none of the login cookies the token belongs to.
            self.xsrf_token = ""

        return self._session

    async def _close_session(self) -> None:
        # The token belongs to the closed session, the next request has to log in again.
        self.xsrf_token = ""

        if self._custom_session and self._session and not self._session.closed:
            await self._session.close()

    @property
    def headers(self) -> dict[str, str]:
        """Headers for all API requests, including the current XSRF token."""
        return {
            **COMMON_HEADERS,
            "Content-Type": "application/json",
            "x-xsrf-token": self.xsrf_token,
        }

    @classmethod
    def _query(
        cls,
        name: str,
        value: object,
        enum_type: type[Enum],
        /,
        *,
        active_only: object = None,
        all_is_no_filter: bool = False,
    ) -> str:
        """Build a query string like ``?name=A,B&activeOnly=true`` from the filters that are not `None`, or ``""``.

        `value` is a member of `enum_type` or an iterable of members, an empty one is no filter like `None`, the
        portal answers e.g. ``?branch=`` with 404. Any other value, or an `active_only` that is no bool, raises an
        `APIError`. With `all_is_no_filter`, all members are no filter either, for filters that the portal only
        takes with one value.
        """
        parts: list[str] = []

        if value is not None:
            # A string is iterable too, but of characters, not of members.
            values: Iterable[object] = (
                value if isinstance(value, Iterable) and not isinstance(value, (Enum, str)) else [value]
            )

            # Without duplicates, e.g. a list with the same member twice.
            unique: list[str] = list(dict.fromkeys(cls._enum_value(name, member, enum_type) for member in values))

            if all_is_no_filter and len(unique) == len(enum_type):
                unique = []

            if unique:
                parts.append(f"{name}={','.join(unique)}")

        if active_only is not None:
            flag: str = "activeOnly"

            if not isinstance(active_only, bool):
                raise cls._invalid_value(flag, active_only)

            parts.append(f"{flag}={str(active_only).lower()}")

        return f"?{'&'.join(parts)}" if parts else ""

    @classmethod
    def _enum_value(cls, name: str, value: object, enum_type: type[Enum], /, *, allow_str: bool = False) -> str:
        """Return the value of a member of `enum_type`, or with `allow_str` a string itself.

        Any other value, also a member of another enum, raises an `APIError`.
        """
        if isinstance(value, enum_type):
            return value.value
        if allow_str and isinstance(value, str):
            return value

        raise cls._invalid_value(name, value)

    @staticmethod
    def _invalid_value(name: str, value: object, /) -> APIError:
        """Return the `APIError` for an invalid value of the parameter `name`."""
        return APIError(f"Invalid value for {name}: {value!r}")

    @staticmethod
    def _client_error(error: ClientError | TimeoutError | RuntimeError, /) -> APIError:
        """Map an aiohttp client error, a timeout or a request on a closed session to an `APIError`."""
        return APIError(str(error) or type(error).__name__)

    async def _request[T: _JSONResponse](
        self,
        method: Literal["GET", "POST"],
        url: str,
        response_type: type[T],
        *,
        json: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> T:
        # Resets the token if the session has to be replaced, so the request logs in on the new session.
        session: ClientSession = await self._get_session()

        # The login maps its own errors, the try below only covers the request itself.
        if not self.xsrf_token:
            await self.login()

        # The headers are read after the login, the portal rejects POST requests without a valid XSRF token.
        used_token: str = self.xsrf_token

        try:
            async with session.request(method, url, headers=self.headers, json=json) as resp:
                if resp.status == HTTPStatus.OK:
                    data: Any = None

                    with suppress(JSONDecodeError, ContentTypeError, UnicodeDecodeError):
                        data = await resp.json()

                    # Not JSON, not the expected object or array, or e.g. an empty body, which aiohttp returns as None.
                    if not isinstance(data, response_type):
                        raise InvalidJsonError(await resp.text(errors="replace"), status=resp.status)

                    return data
                if resp.status != HTTPStatus.UNAUTHORIZED:
                    raise APIError(await resp.text(errors="replace"), status=resp.status)
        except (ClientError, TimeoutError) as error:
            # The session and its login stay valid, closing it would also abort concurrent requests.
            raise self._client_error(error) from error
        except RuntimeError as error:
            # aiohttp raises a RuntimeError for a request on a closed session, e.g. after a `logout()` meanwhile.
            # Any other RuntimeError is no connection error and is not hidden.
            if not session.closed:
                raise

            raise self._client_error(error) from error

        if not retry:
            self.xsrf_token = ""
            raise AuthenticationError(status=HTTPStatus.UNAUTHORIZED)

        # Log in again after the 401 response is released, so it does not hold a connection of the session.
        # Skip the login if another request already got a new token.
        if self.xsrf_token == used_token:
            await self.login()

        return await self._request(method, url, response_type, json=json, retry=False)

    async def _get[T: _JSONResponse](self, url: str, response_type: type[T], /) -> T:
        return await self._request("GET", url, response_type)

    async def _post[T: _JSONResponse](
        self,
        url: str,
        response_type: type[T],
        /,
        *,
        json: dict[str, Any],
    ) -> T:
        return await self._request("POST", url, response_type, json=json)

    async def login(self) -> None:
        """Log in to the eService portal and get a new XSRF token.

        Calling this method is optional, the client logs in automatically on the first request.
        Concurrent calls and automatic logins share one login and its result.
        If the session is still logged in, the client logs out and logs in again.

        Raises
        ------
        AuthenticationError
            The credentials were rejected (HTTP 401).
        APIError
            Any other HTTP or connection error, or the session response contains no XSRF token.

        """
        if self._login_task is None or self._login_task.done():
            self._login_task = asyncio.create_task(self._login())

        login_task: asyncio.Task[None] = self._login_task

        try:
            # Shielded, so a cancelled caller does not cancel the login of the other callers.
            await asyncio.shield(login_task)
        except asyncio.CancelledError:
            current_task: asyncio.Task[Any] | None = asyncio.current_task()

            # Only `logout()` cancels the login task, a caller that is cancelled itself stays cancelled.
            if not login_task.cancelled() or (current_task is not None and current_task.cancelling()):
                raise

            message: str = "Logged out during the login"
            raise APIError(message) from None

    async def _login(self) -> None:
        session: ClientSession = await self._get_session()

        try:
            await self._authenticate(session)
        except (ClientError, TimeoutError) as error:
            await self._close_session()
            raise self._client_error(error) from error
        except RuntimeError as error:
            # aiohttp raises a RuntimeError if the session was closed during the login, e.g. a passed session.
            # Any other RuntimeError is no connection error and is not hidden.
            closed: bool = session.closed
            await self._close_session()

            if not closed:
                raise

            raise self._client_error(error) from error
        except APIError:
            await self._close_session()
            raise

    async def _authenticate(self, session: ClientSession, /) -> None:
        status: int = await self._post_credentials(session)

        # The portal answers 404 if the session is still logged in.
        if status == HTTPStatus.NOT_FOUND:
            async with session.get(f"{ESERVICE_PORTAL}/service/logout", headers=COMMON_HEADERS):
                pass

            status = await self._post_credentials(session)

        if status == HTTPStatus.UNAUTHORIZED:
            raise AuthenticationError(status=HTTPStatus.UNAUTHORIZED)
        if status != HTTPStatus.OK:
            raise APIError(status=status)

        async with session.get(f"{ESERVICE_PORTAL_API}/session", headers=COMMON_HEADERS) as resp:
            if resp.status != HTTPStatus.OK:
                raise APIError(await resp.text(errors="replace"), status=resp.status)

            if not (cookie := resp.cookies.get("XSRF-TOKEN")) or not cookie.value:
                message: str = "The session response contains no XSRF token"
                raise APIError(message)

            self.xsrf_token = cookie.value

    async def _post_credentials(self, session: ClientSession, /) -> int:
        async with session.post(
            f"{ESERVICE_PORTAL}/service/j_security_check",
            json={
                "j_username": self._username,
                "j_password": self._password,
            },
            headers={
                **COMMON_HEADERS,
                "Content-Type": "application/json",
            },
        ) as resp:
            return resp.status

    async def logout(self) -> None:
        """Log out from the eService portal and reset the XSRF token.

        If the client created its own session, the session is closed. The XSRF token is reset and the session
        is closed even if the logout request fails. A running login is cancelled and raises an `APIError`.

        Raises
        ------
        APIError
            The logout request failed with an HTTP or connection error.

        """
        try:
            login_task: asyncio.Task[None] | None = self._login_task

            # Otherwise the login would set a new token after the logout, e.g. on a passed session.
            if login_task is not None and not login_task.done():
                login_task.cancel()
                # Waits for the cancelled login without raising its CancelledError.
                await asyncio.wait([login_task])

            if self._session is not None and not self._session.closed:
                async with self._session.get(f"{ESERVICE_PORTAL}/service/logout", headers=COMMON_HEADERS) as resp:
                    if not resp.ok:
                        raise APIError(await resp.text(errors="replace"), status=resp.status)
        except (ClientError, TimeoutError) as error:
            raise self._client_error(error) from error
        finally:
            await self._close_session()

    async def dashboard(self) -> dict[str, Any]:
        """Get the dashboard data, e.g. business partners and contract accounts.

        Returns
        -------
        dict[str, Any]
            Raw JSON response of the dashboard.

        Raises
        ------
        AuthenticationError
            The credentials were rejected (HTTP 401), also after a new login.
        InvalidJsonError
            The response is not valid JSON, e.g. the maintenance page ("Wartungsseite").
        APIError
            Any other HTTP or connection error.

        Examples
        --------
        >>> dashboard = await client.dashboard()
        >>> dashboard["contractAccounts"]

        """
        return await self._get(f"{ESERVICE_PORTAL_API}/dashboard", dict)

    async def dashboard_headers(
        self,
        branch: Iterable[ConsumptionsProfilesBranch] | ConsumptionsProfilesBranch | None = None,
        *,
        active_only: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Get a short overview of the contract accounts with their contracts and points of delivery.

        Parameters
        ----------
        branch
            Only return contract accounts of this branch or these branches. Returns all contract accounts if `None`,
            empty or both branches.
        active_only
            Only return active (`True`) contract accounts. Returns all contract accounts if `None`.

        Returns
        -------
        list[dict[str, Any]]
            Raw JSON response of the dashboard headers.

        Raises
        ------
        AuthenticationError
            The credentials were rejected (HTTP 401), also after a new login.
        InvalidJsonError
            The response is not valid JSON, e.g. the maintenance page ("Wartungsseite").
        APIError
            Any other HTTP or connection error, or a filter value that is no member of the filter's enum.

        Examples
        --------
        >>> headers = await client.dashboard_headers(active_only=True)
        >>> headers[0]["contracts"][0]["meterPointAdministrationNumber"]

        """
        query: str = self._query(
            "branch",
            branch,
            ConsumptionsProfilesBranch,
            active_only=active_only,
            # The portal answers ``?branch=STROM,GAS`` with 404, both branches are all.
            all_is_no_filter=True,
        )
        return await self._get(f"{ESERVICE_PORTAL_API}/dashboard/headers{query}", list)

    async def consents(
        self, status: Iterable[ConsentsStatus] | ConsentsStatus | None = None, /
    ) -> list[dict[str, Any]]:
        """Get the data sharing consents.

        Parameters
        ----------
        status
            Only return consents with this status or one of these statuses. Returns all consents if `None` or
            empty.

        Returns
        -------
        list[dict[str, Any]]
            Raw JSON response of the consents.

        Raises
        ------
        AuthenticationError
            The credentials were rejected (HTTP 401), also after a new login.
        InvalidJsonError
            The response is not valid JSON, e.g. the maintenance page ("Wartungsseite").
        APIError
            Any other HTTP or connection error, or a filter value that is no member of the filter's enum.

        Examples
        --------
        >>> await client.consents([ConsentsStatus.ACTIVE, ConsentsStatus.ACTIVE_UNCHANGEABLE])

        """
        return await self._get(f"{ESERVICE_PORTAL_API}/consents{self._query('status', status, ConsentsStatus)}", list)

    async def consent_requests(
        self,
        status: Iterable[ConsentRequestsStatus] | ConsentRequestsStatus | None = None,
        /,
    ) -> list[dict[str, Any]]:
        """Get the data sharing consent requests, e.g. of energy communities.

        Parameters
        ----------
        status
            Only return consent requests with this status or one of these statuses. Returns all consent requests
            if `None` or empty.

        Returns
        -------
        list[dict[str, Any]]
            Raw JSON response of the consent requests.

        Raises
        ------
        AuthenticationError
            The credentials were rejected (HTTP 401), also after a new login.
        InvalidJsonError
            The response is not valid JSON, e.g. the maintenance page ("Wartungsseite").
        APIError
            Any other HTTP or connection error, or a filter value that is no member of the filter's enum.

        Examples
        --------
        >>> await client.consent_requests(ConsentRequestsStatus.CONFIRMED)

        """
        return await self._get(
            f"{ESERVICE_PORTAL_API}/consent-requests{self._query('status', status, ConsentRequestsStatus)}", list
        )

    async def consumptions_profiles(
        self,
        branch: Iterable[ConsumptionsProfilesBranch] | ConsumptionsProfilesBranch | None = None,
        *,
        active_only: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Get the consumption profiles of all points of delivery.

        Parameters
        ----------
        branch
            Only return profiles of this branch or these branches. Returns all profiles if `None`, empty or both
            branches.
        active_only
            Only return profiles of active (`True`) points of delivery. Returns all profiles if `None`.

        Returns
        -------
        list[dict[str, Any]]
            Raw JSON response of the consumption profiles.

        Raises
        ------
        AuthenticationError
            The credentials were rejected (HTTP 401), also after a new login.
        InvalidJsonError
            The response is not valid JSON, e.g. the maintenance page ("Wartungsseite").
        APIError
            Any other HTTP or connection error, or a filter value that is no member of the filter's enum.

        Examples
        --------
        >>> await client.consumptions_profiles(ConsumptionsProfilesBranch.ELECTRICITY, active_only=True)

        """
        query: str = self._query(
            "branch",
            branch,
            ConsumptionsProfilesBranch,
            active_only=active_only,
            # The portal answers ``?branch=STROM,GAS`` with 404, both branches are all.
            all_is_no_filter=True,
        )
        return await self._get(f"{ESERVICE_PORTAL_API}/consumptions/profiles{query}", list)

    async def contract_accounts(self, business_partner_number: str, contract_account_number: str) -> dict[str, Any]:
        """Get the data of a contract account.

        Parameters
        ----------
        business_partner_number
            Business partner number, e.g. from `dashboard()`.
        contract_account_number
            Contract account number, e.g. from `dashboard()`.

        Returns
        -------
        dict[str, Any]
            Raw JSON response of the contract account.

        Raises
        ------
        AuthenticationError
            The credentials were rejected (HTTP 401), also after a new login.
        InvalidJsonError
            The response is not valid JSON, e.g. the maintenance page ("Wartungsseite").
        APIError
            Any other HTTP or connection error.

        Examples
        --------
        >>> await client.contract_accounts(
        ...     business_partner_number="1234567890",
        ...     contract_account_number="123456789012",
        ... )

        """
        return await self._get(
            f"{ESERVICE_PORTAL_API}/contract-accounts/"
            f"{quote(str(business_partner_number), safe='')}/{quote(str(contract_account_number), safe='')}",
            dict,
        )

    async def consumptions_profile(
        self,
        pods: list[Pod],
        dimension: ConsumptionsDimension = ConsumptionsDimension.ENERGY,
    ) -> list[dict[str, Any]]:
        """Get the consumption profile of one or more points of delivery.

        Parameters
        ----------
        pods
            Points of delivery and the time range to request.
        dimension
            Measurement dimension of the values.

        Returns
        -------
        list[dict[str, Any]]
            Raw JSON response of the consumption profile.

        Raises
        ------
        AuthenticationError
            The credentials were rejected (HTTP 401), also after a new login.
        InvalidJsonError
            The response is not valid JSON, e.g. the maintenance page ("Wartungsseite").
        APIError
            Any other HTTP or connection error, a `dimension` that is no `ConsumptionsDimension` member, or a
            `Pod` value that is neither a member of its enum nor a string.

        Examples
        --------
        >>> await client.consumptions_profile(
        ...     pods=[
        ...         Pod(
        ...             contract_account_number="123456789012",
        ...             profile_type=ProfileType.ACTIVE_CURRENT,
        ...             best_available_granularity=Granularity.QUARTER_OF_AN_HOUR,
        ...             meter_point_administration_number="AT0031000000000000000000000000000",
        ...             date_from="...",
        ...             date_to="...",
        ...         ),
        ...     ],
        ...     dimension=ConsumptionsDimension.ENERGY,
        ... )

        """
        return await self._post(
            f"{ESERVICE_PORTAL_API}/consumptions/profile/active",
            list,
            json={
                "pods": [
                    {
                        "contractAccountNumber": pod["contract_account_number"],
                        **(
                            {"energyCommunityId": pod["energy_community_id"]}
                            if pod.get("energy_community_id") is not None
                            else {}
                        ),
                        "type": self._enum_value("profile_type", pod["profile_type"], ProfileType, allow_str=True),
                        "bestAvailableGranularity": self._enum_value(
                            "best_available_granularity",
                            pod["best_available_granularity"],
                            Granularity,
                            allow_str=True,
                        ),
                        "meterPointAdministrationNumber": pod["meter_point_administration_number"],
                        "timerange": {
                            "from": pod["date_from"],
                            "to": pod["date_to"],
                        },
                    }
                    for pod in pods
                ],
                "dimension": self._enum_value("dimension", dimension, ConsumptionsDimension),
            },
        )
