import re
from http import HTTPStatus
from typing import Any
from typing import Literal

import aiohttp
from aiohttp import ClientError
from aiohttp import ClientResponse
from aiohttp import ClientSession

from netzooe_eservice_api.constants import COMMON_HEADERS
from netzooe_eservice_api.constants import ConsentsStatus
from netzooe_eservice_api.constants import ConsumptionsProfilesBranch
from netzooe_eservice_api.constants import ESERVICE_PORTAL
from netzooe_eservice_api.constants import ESERVICE_PORTAL_API
from netzooe_eservice_api.error import APIError
from netzooe_eservice_api.error import AuthenticationError


class NetzOOEeServiceAPI:
    """An asynchronous client to interact with the Netz OÖ eService API."""

    def __init__(
        self,
        username: str,
        password: str,
        *,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize API with username and password.

        Parameters
        ----------
        username
            eService username
        password
            eService password
        session
            Add an aiohttp client session

        Examples
        --------
        >>> async with ClientSession() as session:
        >>>     client = NetzOOEeServiceAPI(
        >>>         username="test",
        >>>         password="test",
        >>>         session=session,
        >>>     )

        """
        self._username = username
        self._password = password
        self._session: ClientSession = session
        self.xsrf_token: str = ""

    @property
    def headers(self) -> dict[str, str]:
        """Default headers all API calls."""
        return {
            **COMMON_HEADERS,
            "Content-Type": "application/json",
            "x-xsrf-token": self.xsrf_token,
        }

    async def _get_session(self) -> ClientResponse:
        async with self._session.get(f"{ESERVICE_PORTAL_API}/session", headers={**COMMON_HEADERS}) as resp:
            if resp.status != HTTPStatus.OK:
                await self._session.close()
                raise APIError(status=HTTPStatus(resp.status))

            return resp

    def _set_xsrf_token(self, headers) -> None:  # type: ignore[no-untyped-def]  # noqa: ANN001
        cookies: list[str] = headers.getall("Set-Cookie", [])
        cookie_string: str = ";".join(cookies)

        if match := re.search(r"XSRF-TOKEN=([^;]+)", cookie_string):
            self.xsrf_token = match.group(1)

    async def _request(
        self,
        method: Literal["GET", "POST"],
        url: str,
        *,
        json: Any | None = None,  # noqa: ANN401
        retry: bool = True,
    ) -> Any:  # noqa: ANN401
        if not self.xsrf_token:
            await self.login()

        headers: dict[str, str] = self.headers.copy()

        if json is not None:
            headers["Content-Type"] = "application/json"

        try:
            async with self._session.request(method, url, headers=headers, json=json) as resp:
                if resp.status == HTTPStatus.OK:
                    return await resp.json()
                if resp.status == HTTPStatus.UNAUTHORIZED:
                    if retry:
                        await self.login()
                        return await self._request(method, url, json=json, retry=False)

                    await self._session.close()
                    raise AuthenticationError(status=HTTPStatus.UNAUTHORIZED)

                message = await resp.text()
                raise APIError(message, status=HTTPStatus(resp.status))
        except ClientError as error:
            await self._session.close()
            raise APIError(str(error)) from error

    async def _get(self, url: str) -> Any:  # noqa: ANN401
        return await self._request("GET", url)

    async def _post(self, url: str, /, *, json: Any) -> Any:  # noqa: ANN401
        return await self._request("POST", url, json=json)

    async def login(self) -> None:
        """Authenticate to the Netz OÖ eService portal."""
        async with await self._session.post(
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
                await self._session.close()

                if resp.status == HTTPStatus.UNAUTHORIZED:
                    raise AuthenticationError(status=HTTPStatus.UNAUTHORIZED)

                raise APIError(status=HTTPStatus(resp.status))

            _session: ClientResponse = await self._get_session()
            self._set_xsrf_token(_session.headers)

    async def logout(self) -> None:
        """Logout from the Netz OÖ eService portal."""
        await self._session.get(
            f"{ESERVICE_PORTAL}/service/logout",
            headers={
                **COMMON_HEADERS,
            },
        )

        if not self._session.closed:
            await self._session.close()

    async def dashboard(self) -> dict[str, Any]:
        """Get data from the eService dashboard."""
        data: dict[str, Any] = await self._get(f"{ESERVICE_PORTAL_API}/dashboard")
        return data

    async def consents(self, status: list[ConsentsStatus] | ConsentsStatus | None = None, /) -> list[dict[str, Any]]:
        """Get data from the eService data sharing."""
        _status: str = ""

        if status is not None and not isinstance(status, list):
            status = [status]

        if isinstance(status, list):
            _status = ",".join([_.value for _ in status])
            _status = f"?status={_status}"

        data: list[dict[str, Any]] = await self._get(f"{ESERVICE_PORTAL_API}/consents{_status}")
        return data

    async def consumptions_profiles(
        self, branch: list[ConsumptionsProfilesBranch] | ConsumptionsProfilesBranch | None
    ) -> list[dict[str, Any]]:
        """Get data from the eService profiles."""
        _branch: str = ""

        if branch is not None and not isinstance(branch, list):
            branch = [branch]

        if isinstance(branch, list):
            _branch = ",".join([_.value for _ in branch])
            _branch = f"?branch={_branch}"

        data: list[dict[str, Any]] = await self._get(f"{ESERVICE_PORTAL_API}/consumptions/profiles{_branch}")
        return data

    async def contract_accounts(self, business_partner_number: str, contract_account_number: str) -> dict[str, Any]:
        """Get data from the eService contract accounts."""
        data: dict[str, Any] = await self._get(
            f"{ESERVICE_PORTAL_API}/contract-accounts/{business_partner_number}/{contract_account_number}"
        )
        return data

    async def consumptions_profile(
        self,
        contract_account_number: str,
        energy_community_id: str,
        profile_type: str,
        best_available_granularity: str,
        meter_point_administration_number: str,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, Any]]:
        """Get data from the eService consumptions profile."""
        data: list[dict[str, Any]] = await self._post(
            f"{ESERVICE_PORTAL_API}/consumptions/profile/active",
            json={
                "pods": [
                    {
                        "energyCommunityId": energy_community_id,
                        "type": profile_type,
                        "bestAvailableGranularity": best_available_granularity,
                        "meterPointAdministrationNumber": meter_point_administration_number,
                        "contractAccountNumber": contract_account_number,
                        "timerange": {"from": date_from, "to": date_to},
                    }
                ],
                "dimension": "ENERGY",
            },
        )
        return data
