# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0
"""Asynchronous client for the Netz OÖ eService API."""

import asyncio
import re
from collections.abc import Sequence
from enum import Enum
from http import HTTPStatus
from json.decoder import JSONDecodeError
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import NotRequired
from typing import TypedDict
from typing import cast
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

if TYPE_CHECKING:
    from multidict import CIMultiDictProxy

type JSONResponse = dict[str, Any] | list[dict[str, Any]]


def _query(**params: Sequence[Enum] | Enum | bool | None) -> str:
    """Build a query string like ``?name=A,B&flag=true`` from the parameters that are not `None`, or ``""``."""
    parts: list[str] = []

    for name, value in params.items():
        if value is None:
            continue

        if isinstance(value, bool):
            parts.append(f"{name}={str(value).lower()}")
        else:
            values: Sequence[Enum] = [value] if isinstance(value, Enum) else value
            parts.append(f"{name}={','.join(member.value for member in values)}")

    return f"?{'&'.join(parts)}" if parts else ""


def _enum_value(value: Enum | str, /) -> str:
    """Return the value of an enum member, or the string itself."""
    return value.value if isinstance(value, Enum) else value


def _client_error(error: ClientError | TimeoutError, /) -> APIError:
    """Map an aiohttp client error or a timeout to an `APIError`."""
    return APIError(str(error) or type(error).__name__)


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
            If no session is passed, the client creates its own and closes it on `logout()` and on errors.

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
        self._login_lock: asyncio.Lock = asyncio.Lock()

    async def _get_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            # Also for a passed session that is already closed. The new session is owned by the client.
            self._session = ClientSession()
            self._custom_session = True

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

    async def _init_api_session(self) -> None:
        session: ClientSession = await self._get_session()

        async with session.get(f"{ESERVICE_PORTAL_API}/session", headers=COMMON_HEADERS) as resp:
            if resp.status != HTTPStatus.OK:
                await self._close_session()
                raise APIError(status=resp.status)

            if not self._set_xsrf_token(resp.headers):
                await self._close_session()
                message: str = "The session response contains no XSRF token"
                raise APIError(message)

    def _set_xsrf_token(self, headers: "CIMultiDictProxy[str]") -> bool:
        cookies: list[str] = headers.getall("Set-Cookie", [])
        cookie_string: str = ";".join(cookies)

        if match := re.search(r"XSRF-TOKEN=([^;]+)", cookie_string):
            self.xsrf_token = match.group(1)
            return True

        return False

    async def _request(
        self,
        method: Literal["GET", "POST"],
        url: str,
        *,
        json: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> JSONResponse:
        message: str

        try:
            if not self.xsrf_token:
                await self._relogin(expired_token="")

            # Read session and headers after the login, the portal rejects POST requests without a valid XSRF token.
            session: ClientSession = await self._get_session()
            used_token: str = self.xsrf_token

            async with session.request(method, url, headers=self.headers, json=json) as resp:
                if resp.status == HTTPStatus.OK:
                    try:
                        return await resp.json()
                    except (JSONDecodeError, ContentTypeError) as error:
                        message = await resp.text()
                        raise InvalidJsonError(message, status=resp.status) from error
                if resp.status != HTTPStatus.UNAUTHORIZED:
                    message = await resp.text()
                    raise APIError(message, status=resp.status)

            # Log in again after the 401 response is released, so it does not hold a connection of the session.
            if retry:
                await self._relogin(expired_token=used_token)
                return await self._request(method, url, json=json, retry=False)

            await self._close_session()

            raise AuthenticationError(status=HTTPStatus.UNAUTHORIZED)
        except (ClientError, TimeoutError) as error:
            await self._close_session()
            raise _client_error(error) from error

    async def _relogin(self, *, expired_token: str) -> None:
        # Concurrent requests share one login. Skip it if another request already got a new token.
        async with self._login_lock:
            if self.xsrf_token == expired_token:
                await self.login()

    async def _get(self, url: str) -> JSONResponse:
        return await self._request("GET", url)

    async def _post(self, url: str, /, *, json: dict[str, Any]) -> JSONResponse:
        return await self._request("POST", url, json=json)

    async def login(self) -> None:
        """Log in to the eService portal and get a new XSRF token.

        Calling this method is optional, the client logs in automatically on the first request.

        Raises
        ------
        AuthenticationError
            The credentials were rejected (HTTP 401).
        APIError
            Any other HTTP or connection error, or the session response contains no XSRF token.

        """
        session: ClientSession = await self._get_session()

        try:
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
                if resp.status != HTTPStatus.OK:
                    await self._close_session()

                    if resp.status == HTTPStatus.UNAUTHORIZED:
                        raise AuthenticationError(status=HTTPStatus.UNAUTHORIZED)

                    raise APIError(status=resp.status)

                await self._init_api_session()
        except (ClientError, TimeoutError) as error:
            await self._close_session()
            raise _client_error(error) from error

    async def logout(self) -> None:
        """Log out from the eService portal and reset the XSRF token.

        If the client created its own session, the session is closed. The XSRF token is reset and the session
        is closed even if the logout request fails.

        Raises
        ------
        APIError
            The logout request failed with an HTTP or connection error.

        """
        try:
            if self._session is not None and not self._session.closed:
                async with self._session.get(
                    f"{ESERVICE_PORTAL}/service/logout",
                    headers={
                        **COMMON_HEADERS,
                    },
                ) as resp:
                    if not resp.ok:
                        message: str = await resp.text()
                        raise APIError(message, status=resp.status)
        except (ClientError, TimeoutError) as error:
            raise _client_error(error) from error
        finally:
            self.xsrf_token = ""
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
        return cast("dict[str, Any]", await self._get(f"{ESERVICE_PORTAL_API}/dashboard"))

    async def dashboard_headers(
        self,
        branch: list[ConsumptionsProfilesBranch] | ConsumptionsProfilesBranch | None = None,
        *,
        active_only: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Get a short overview of the contract accounts with their contracts and points of delivery.

        Parameters
        ----------
        branch
            Only return contract accounts of this branch or these branches. Returns all contract accounts if `None`.
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
            Any other HTTP or connection error.

        Examples
        --------
        >>> headers = await client.dashboard_headers(active_only=True)
        >>> headers[0]["contracts"][0]["meterPointAdministrationNumber"]

        """
        return cast(
            "list[dict[str, Any]]",
            await self._get(f"{ESERVICE_PORTAL_API}/dashboard/headers{_query(branch=branch, activeOnly=active_only)}"),
        )

    async def consents(self, status: list[ConsentsStatus] | ConsentsStatus | None = None, /) -> list[dict[str, Any]]:
        """Get the data sharing consents.

        Parameters
        ----------
        status
            Only return consents with this status or one of these statuses. Returns all consents if `None`.

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
            Any other HTTP or connection error.

        Examples
        --------
        >>> await client.consents([ConsentsStatus.ACTIVE, ConsentsStatus.ACTIVE_UNCHANGEABLE])

        """
        return cast(
            "list[dict[str, Any]]",
            await self._get(f"{ESERVICE_PORTAL_API}/consents{_query(status=status)}"),
        )

    async def consent_requests(
        self,
        status: list[ConsentRequestsStatus] | ConsentRequestsStatus | None = None,
        /,
    ) -> list[dict[str, Any]]:
        """Get the data sharing consent requests, e.g. of energy communities.

        Parameters
        ----------
        status
            Only return consent requests with this status or one of these statuses. Returns all consent requests
            if `None`.

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
            Any other HTTP or connection error.

        Examples
        --------
        >>> await client.consent_requests(ConsentRequestsStatus.CONFIRMED)

        """
        return cast(
            "list[dict[str, Any]]",
            await self._get(f"{ESERVICE_PORTAL_API}/consent-requests{_query(status=status)}"),
        )

    async def consumptions_profiles(
        self,
        branch: list[ConsumptionsProfilesBranch] | ConsumptionsProfilesBranch | None = None,
        *,
        active_only: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Get the consumption profiles of all points of delivery.

        Parameters
        ----------
        branch
            Only return profiles of this branch or these branches. Returns all profiles if `None`.
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
            Any other HTTP or connection error.

        Examples
        --------
        >>> await client.consumptions_profiles(ConsumptionsProfilesBranch.ELECTRICITY, active_only=True)

        """
        return cast(
            "list[dict[str, Any]]",
            await self._get(
                f"{ESERVICE_PORTAL_API}/consumptions/profiles{_query(branch=branch, activeOnly=active_only)}",
            ),
        )

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
        return cast(
            "dict[str, Any]",
            await self._get(
                f"{ESERVICE_PORTAL_API}/contract-accounts/"
                f"{quote(str(business_partner_number), safe='')}/{quote(str(contract_account_number), safe='')}",
            ),
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
            Any other HTTP or connection error.

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
        return cast(
            "list[dict[str, Any]]",
            await self._post(
                f"{ESERVICE_PORTAL_API}/consumptions/profile/active",
                json={
                    "pods": [
                        {
                            "contractAccountNumber": pod["contract_account_number"],
                            **(
                                {"energyCommunityId": pod["energy_community_id"]}
                                if pod.get("energy_community_id") is not None
                                else {}
                            ),
                            "type": _enum_value(pod["profile_type"]),
                            "bestAvailableGranularity": _enum_value(pod["best_available_granularity"]),
                            "meterPointAdministrationNumber": pod["meter_point_administration_number"],
                            "timerange": {
                                "from": pod["date_from"],
                                "to": pod["date_to"],
                            },
                        }
                        for pod in pods
                    ],
                    "dimension": dimension.value,
                },
            ),
        )
