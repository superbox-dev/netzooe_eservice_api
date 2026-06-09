import re
from http import HTTPStatus
from json.decoder import JSONDecodeError
from typing import Any
from typing import Literal
from typing import TypedDict

from aiohttp import ClientError
from aiohttp import ClientSession
from aiohttp import ContentTypeError

from netzooe_eservice_api.constants import COMMON_HEADERS
from netzooe_eservice_api.constants import ConsentsStatus
from netzooe_eservice_api.constants import ConsumptionsProfilesBranch
from netzooe_eservice_api.constants import ESERVICE_PORTAL
from netzooe_eservice_api.constants import ESERVICE_PORTAL_API
from netzooe_eservice_api.error import APIError
from netzooe_eservice_api.error import AuthenticationError
from netzooe_eservice_api.error import InvalidJsonError


class Pod(TypedDict):
    contract_account_number: str
    energy_community_id: str
    profile_type: str
    best_available_granularity: str
    meter_point_administration_number: str
    date_from: str
    date_to: str


class NetzOOEeServiceAPI:
    """An asynchronous client to interact with the Netz OÖ eService API."""

    def __init__(
        self,
        username: str,
        password: str,
        *,
        session: ClientSession | None = None,
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
        """Default headers all API calls."""
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

    async def _get(self, url: str) -> Any:  # noqa: ANN401
        return await self._request("GET", url)

    async def _post(self, url: str, /, *, json: Any) -> Any:  # noqa: ANN401
        return await self._request("POST", url, json=json)

    async def login(self) -> None:
        """Authenticate to the Netz OÖ eService portal."""
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
        """Logout from the Netz OÖ eService portal."""
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

    async def consumptions_profile(self, pods: list[Pod]) -> list[dict[str, Any]]:
        """Get data from the eService consumptions profile."""
        data: list[dict[str, Any]] = await self._post(
            f"{ESERVICE_PORTAL_API}/consumptions/profile/active",
            json={
                "pods": [
                    {
                        "contractAccountNumber": pod["contract_account_number"],
                        "energyCommunityId": pod["energy_community_id"],
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
                "dimension": "ENERGY",
            },
        )
        return data
