from typing import Any
from typing import Final

import pytest
from aiohttp import ClientError
from aiohttp import ClientSession
from aioresponses import aioresponses
from yarl import URL

from netzooe_eservice_api.api import NetzOOEeServiceAPI
from netzooe_eservice_api.api import Pod
from netzooe_eservice_api.constants import ConsentsStatus
from netzooe_eservice_api.constants import ConsumptionsProfilesBranch
from netzooe_eservice_api.error import APIError
from netzooe_eservice_api.error import AuthenticationError

LOGIN_AND_LOGOUT_API_CALLS: Final[int] = 3


async def create_client(mock_api: aioresponses, /, *, repeat: bool | int = False) -> NetzOOEeServiceAPI:
    session: ClientSession = ClientSession()

    mock_api.post(
        "https://eservice.netzooe.at/service/j_security_check",
        status=200,
        repeat=repeat,
    )

    mock_api.get(
        "https://eservice.netzooe.at/service/v1.0/session",
        headers={
            "Set-Cookie": "XSRF-TOKEN=mocked-token-value; Path=/; Secure",
        },
        status=200,
        repeat=repeat,
    )

    mock_api.get(
        "https://eservice.netzooe.at/service/logout",
        status=200,
        repeat=False,
    )

    client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
        username="test",
        password="test",  # noqa: S106
        session=session,
    )

    return client


async def create_logged_in_client(mock_api: aioresponses, /, *, repeat: bool | int = False) -> NetzOOEeServiceAPI:
    client: NetzOOEeServiceAPI = await create_client(mock_api, repeat=repeat)

    await client.login()
    return client


class TestHappyPathNetzOOEeServiceAPI:
    @pytest.mark.asyncio
    async def test_login(self) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)
            await client.logout()

            assert client.xsrf_token == "mocked-token-value"  # noqa: S105

            login_key = ("POST", URL("https://eservice.netzooe.at/service/j_security_check"))
            session_key = ("GET", URL("https://eservice.netzooe.at/service/v1.0/session"))

            assert login_key in mock_api.requests
            assert session_key in mock_api.requests

            assert len(mock_api.requests) == LOGIN_AND_LOGOUT_API_CALLS
            assert len(mock_api.requests[login_key]) == 1
            assert len(mock_api.requests[session_key]) == 1

            login_call = mock_api.requests[login_key][0]

            assert login_call.kwargs["json"] == {
                "j_username": "test",
                "j_password": "test",
            }

            assert login_call.kwargs["headers"] == {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
                "client-id": "netzonline",
                "Content-Type": "application/json",
            }

            session_call = mock_api.requests[session_key][0]

            assert session_call.kwargs["headers"] == {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
                "client-id": "netzonline",
            }

    @pytest.mark.asyncio
    async def test_reconnect(self) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=401, payload={})
            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            result = await client.dashboard()
            assert result == {}

            await client.logout()

            dashboard_key = ("GET", URL("https://eservice.netzooe.at/service/v1.0/dashboard"))
            assert dashboard_key in mock_api.requests

            assert len(mock_api.requests) == LOGIN_AND_LOGOUT_API_CALLS + 1
            assert len(mock_api.requests[dashboard_key]) == 2  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_dashboard(self) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            result = await client.dashboard()
            assert result == {}

            await client.logout()

            dashboard_key = ("GET", URL("https://eservice.netzooe.at/service/v1.0/dashboard"))
            assert dashboard_key in mock_api.requests

            assert len(mock_api.requests) == LOGIN_AND_LOGOUT_API_CALLS + 1
            assert len(mock_api.requests[dashboard_key]) == 1

    @pytest.mark.asyncio
    async def test_dashboard_without_login(self) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            result = await client.dashboard()
            assert result == {}

            await client.logout()

            dashboard_key = ("GET", URL("https://eservice.netzooe.at/service/v1.0/dashboard"))
            assert dashboard_key in mock_api.requests

            assert len(mock_api.requests) == LOGIN_AND_LOGOUT_API_CALLS + 1
            assert len(mock_api.requests[dashboard_key]) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "url"),
        [
            (
                [
                    ConsentsStatus.ACTIVE,
                    ConsentsStatus.ACTIVE_UNCHANGEABLE,
                ],
                "https://eservice.netzooe.at/service/v1.0/consents?status=ACTIVE%252CACTIVE_UNCHANGEABLE",
            ),
            (
                ConsentsStatus.ACTIVE,
                "https://eservice.netzooe.at/service/v1.0/consents?status=ACTIVE",
            ),
        ],
    )
    async def test_consents(self, status: list[ConsentsStatus] | ConsentsStatus | None, url: str) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, payload=[])

            result: list[dict[str, Any]] = await client.consents(status)
            assert result == []

            await client.logout()

            consents_key = ("GET", URL(url))
            assert consents_key in mock_api.requests

            assert len(mock_api.requests) == LOGIN_AND_LOGOUT_API_CALLS + 1
            assert len(mock_api.requests[consents_key]) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("branch", "url"),
        [
            (
                None,
                "https://eservice.netzooe.at/service/v1.0/consumptions/profiles",
            ),
            (
                ConsumptionsProfilesBranch.ELECTRICITY,
                "https://eservice.netzooe.at/service/v1.0/consumptions/profiles?branch=STROM",
            ),
        ],
    )
    async def test_consumptions_profiles(
        self, branch: list[ConsumptionsProfilesBranch] | ConsumptionsProfilesBranch | None, url: str
    ) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, payload=[])

            result: list[dict[str, Any]] = await client.consumptions_profiles(branch)
            assert result == []

            await client.logout()

            consumptions_profiles_key = ("GET", URL(url))
            assert consumptions_profiles_key in mock_api.requests

            assert len(mock_api.requests) == LOGIN_AND_LOGOUT_API_CALLS + 1
            assert len(mock_api.requests[consumptions_profiles_key]) == 1

    @pytest.mark.asyncio
    async def test_contract_account(self) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/contract-accounts/123/345", status=200, payload={})

            result = await client.contract_accounts(business_partner_number="123", contract_account_number="345")
            assert result == {}

            await client.logout()

            contract_account_key = ("GET", URL("https://eservice.netzooe.at/service/v1.0/contract-accounts/123/345"))
            assert contract_account_key in mock_api.requests

            assert len(mock_api.requests) == LOGIN_AND_LOGOUT_API_CALLS + 1
            assert len(mock_api.requests[contract_account_key]) == 1

    @pytest.mark.asyncio
    async def test_consumptions_profile(self) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.post(
                "https://eservice.netzooe.at/service/v1.0/consumptions/profile/active", status=200, payload=[]
            )

            result: list[dict[str, Any]] = await client.consumptions_profile(
                pods=[
                    Pod(
                        contract_account_number="123",
                        energy_community_id="345",
                        profile_type="mocked-profile",
                        best_available_granularity="mocked-granularity",
                        meter_point_administration_number="AT123",
                        date_from="2026-01-01",
                        date_to="2026-01-30",
                    )
                ]
            )
            assert result == []

            await client.logout()

            consumptions_profile_key = (
                "POST",
                URL("https://eservice.netzooe.at/service/v1.0/consumptions/profile/active"),
            )
            assert consumptions_profile_key in mock_api.requests

            assert len(mock_api.requests) == LOGIN_AND_LOGOUT_API_CALLS + 1
            assert len(mock_api.requests[consumptions_profile_key]) == 1

            consumptions_profile_call = mock_api.requests[consumptions_profile_key][0]

            payload = consumptions_profile_call.kwargs["json"]

            assert payload["dimension"] == "ENERGY"

            pod: dict[str, Any] = payload["pods"][0]
            assert pod["contractAccountNumber"] == "123"
            assert pod["energyCommunityId"] == "345"
            assert pod["type"] == "mocked-profile"
            assert pod["bestAvailableGranularity"] == "mocked-granularity"
            assert pod["meterPointAdministrationNumber"] == "AT123"
            assert pod["timerange"]["from"] == "2026-01-01"
            assert pod["timerange"]["to"] == "2026-01-30"


class TestUnhappyPathNetzOOEeServiceAPI:

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("exception", "status", "message"),
        [
            (
                AuthenticationError,
                401,
                "401 Unauthorized: No permission -- see authorization schemes",
            ),
            (
                APIError,
                400,
                "400 Bad Request: Bad request syntax or unsupported method",
            ),
        ],
    )
    async def test_login_failed(self, exception: type[APIError], status: int, message: str) -> None:
        with aioresponses() as mock_api:
            mock_api.post(
                "https://eservice.netzooe.at/service/j_security_check",
                status=status,
            )
            session: ClientSession = ClientSession()

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username="test",
                password="test",  # noqa: S106
                session=session,
            )

            with pytest.raises(exception) as error:
                await client.login()

            assert str(error.value) == message
            assert client.xsrf_token == ""

            login_key = ("POST", URL("https://eservice.netzooe.at/service/j_security_check"))

            assert len(mock_api.requests) == 1
            assert login_key in mock_api.requests
            assert len(mock_api.requests[login_key]) == 1

            login_call = mock_api.requests[login_key][0]

            assert login_call.kwargs["json"] == {
                "j_username": "test",
                "j_password": "test",
            }

            assert login_call.kwargs["headers"] == {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
                "client-id": "netzonline",
                "Content-Type": "application/json",
            }

    @pytest.mark.asyncio
    async def test_session_failed(self) -> None:
        with aioresponses() as mock_api:
            mock_api.post(
                "https://eservice.netzooe.at/service/j_security_check",
                status=200,
            )

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/session",
                status=401,
            )

            session: ClientSession = ClientSession()

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username="test",
                password="test",  # noqa: S106
                session=session,
            )

            with pytest.raises(APIError) as error:
                await client.login()

            assert str(error.value) == "401 Unauthorized: No permission -- see authorization schemes"

            assert client.xsrf_token == ""

            login_key = ("POST", URL("https://eservice.netzooe.at/service/j_security_check"))
            session_key = ("GET", URL("https://eservice.netzooe.at/service/v1.0/session"))

            assert login_key in mock_api.requests
            assert session_key in mock_api.requests

            assert len(mock_api.requests) == 2  # noqa: PLR2004
            assert len(mock_api.requests[login_key]) == 1
            assert len(mock_api.requests[session_key]) == 1

    @pytest.mark.asyncio
    async def test_reconnect_failed(self) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=401, repeat=2, payload={})

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "401 Unauthorized: No permission -- see authorization schemes"

    @pytest.mark.asyncio
    async def test_client_error(self) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/dashboard",
                exception=ClientError("mocked error"),
            )

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "mocked error"

    @pytest.mark.asyncio
    async def test_internal_server_error(self) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/dashboard",
                status=500,
            )

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "500 Internal Server Error: Server got itself in trouble"
