# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0
"""Asynchronous client for the Netz OÖ eService API."""

import re
from http import HTTPStatus
from json.decoder import JSONDecodeError
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import NotRequired
from typing import TypedDict
from typing import cast

from aiohttp import ClientError
from aiohttp import ClientSession
from aiohttp import ContentTypeError

from netzooe_eservice_api.constants import COMMON_HEADERS
from netzooe_eservice_api.constants import ESERVICE_PORTAL
from netzooe_eservice_api.constants import ESERVICE_PORTAL_API
from netzooe_eservice_api.constants import ConsentsStatus
from netzooe_eservice_api.constants import ConsumptionsDimension
from netzooe_eservice_api.constants import ConsumptionsProfilesBranch
from netzooe_eservice_api.error import APIError
from netzooe_eservice_api.error import AuthenticationError
from netzooe_eservice_api.error import InvalidJsonError

if TYPE_CHECKING:
    from multidict import CIMultiDictProxy

type JSONResponse = dict[str, Any] | list[dict[str, Any]]


class Pod(TypedDict):
    """Point of delivery (POD) used to request a consumption profile.

    Attributes
    ----------
    contract_account_number
        Contract account number of the point of delivery.
    energy_community_id
        Optional ID of the energy community. Only sent if it is set.
    profile_type
        Profile type, e.g. from `consumptions_profiles()`.
    best_available_granularity
        Best available granularity of the measured values, e.g. from `consumptions_profiles()`.
    meter_point_administration_number
        Meter point administration number (Zählpunktnummer).
    date_from
        Start of the time range.
    date_to
        End of the time range.

    """

    contract_account_number: str
    energy_community_id: NotRequired[str | None]
    profile_type: str
    best_available_granularity: str
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

    async def _get_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession()

        return self._session

    async def _close_session(self) -> None:
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
                raise APIError(status=HTTPStatus(resp.status))

            self._set_xsrf_token(resp.headers)

    def _set_xsrf_token(self, headers: "CIMultiDictProxy[str]") -> None:
        cookies: list[str] = headers.getall("Set-Cookie", [])
        cookie_string: str = ";".join(cookies)

        if match := re.search(r"XSRF-TOKEN=([^;]+)", cookie_string):
            self.xsrf_token = match.group(1)

    async def _request(
        self,
        method: Literal["GET", "POST"],
        url: str,
        *,
        json: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> JSONResponse:
        session: ClientSession = await self._get_session()
        headers: dict[str, str] = self.headers.copy()
        message: str

        try:
            if not self.xsrf_token:
                await self.login()

            async with session.request(method, url, headers=headers, json=json) as resp:
                if resp.status == HTTPStatus.OK:
                    try:
                        return await resp.json()
                    except (JSONDecodeError, ContentTypeError) as error:
                        message = await resp.text()
                        raise InvalidJsonError(message, status=HTTPStatus(resp.status)) from error
                if resp.status == HTTPStatus.UNAUTHORIZED:
                    if retry:
                        await self.login()
                        return await self._request(method, url, json=json, retry=False)

                    await self._close_session()

                    raise AuthenticationError(status=HTTPStatus.UNAUTHORIZED)

                message = await resp.text()
                raise APIError(message, status=HTTPStatus(resp.status))
        except ClientError as error:
            await self._close_session()
            raise APIError(str(error)) from error

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
            Any other HTTP error, e.g. if the session could not be created.

        """
        session: ClientSession = await self._get_session()

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

                raise APIError(status=HTTPStatus(resp.status))

            await self._init_api_session()

    async def logout(self) -> None:
        """Log out from the eService portal and reset the XSRF token.

        If the client created its own session, the session is closed.

        """
        session: ClientSession = await self._get_session()

        await session.get(
            f"{ESERVICE_PORTAL}/service/logout",
            headers={
                **COMMON_HEADERS,
            },
        )

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
        data: dict[str, Any] = cast("dict[str, Any]", await self._get(f"{ESERVICE_PORTAL_API}/dashboard"))
        return data

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
        _status: str = ""

        if status is not None and not isinstance(status, list):
            status = [status]

        if isinstance(status, list):
            _status = ",".join([_.value for _ in status])
            _status = f"?status={_status}"

        data: list[dict[str, Any]] = cast(
            "list[dict[str, Any]]",
            await self._get(f"{ESERVICE_PORTAL_API}/consents{_status}"),
        )
        return data

    async def consumptions_profiles(
        self,
        branch: list[ConsumptionsProfilesBranch] | ConsumptionsProfilesBranch | None,
    ) -> list[dict[str, Any]]:
        """Get the consumption profiles of all points of delivery.

        Parameters
        ----------
        branch
            Only return profiles of this branch or these branches. Returns all profiles if `None`.

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
        >>> await client.consumptions_profiles(ConsumptionsProfilesBranch.ELECTRICITY)

        """
        _branch: str = ""

        if branch is not None and not isinstance(branch, list):
            branch = [branch]

        if isinstance(branch, list):
            _branch = ",".join([_.value for _ in branch])
            _branch = f"?branch={_branch}"

        data: list[dict[str, Any]] = cast(
            "list[dict[str, Any]]",
            await self._get(f"{ESERVICE_PORTAL_API}/consumptions/profiles{_branch}"),
        )
        return data

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
        data: dict[str, Any] = cast(
            "dict[str, Any]",
            await self._get(
                f"{ESERVICE_PORTAL_API}/contract-accounts/{business_partner_number}/{contract_account_number}",
            ),
        )
        return data

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
        ...             profile_type="...",
        ...             best_available_granularity="...",
        ...             meter_point_administration_number="AT0031000000000000000000000000000",
        ...             date_from="...",
        ...             date_to="...",
        ...         ),
        ...     ],
        ...     dimension=ConsumptionsDimension.ENERGY,
        ... )

        """
        data: list[dict[str, Any]] = cast(
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
                            "type": pod["profile_type"],
                            "bestAvailableGranularity": pod["best_available_granularity"],
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
        return data
