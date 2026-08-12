from typing import Any

import pytest
from aiohttp import ClientError
from aioresponses import aioresponses
from syrupy import SnapshotAssertion

from netzooe_eservice_api.api import NetzOOEeServiceAPI
from netzooe_eservice_api.api import Pod
from netzooe_eservice_api.constants import ConsentsStatus
from netzooe_eservice_api.constants import ConsumptionsDimension
from netzooe_eservice_api.constants import ConsumptionsProfilesBranch
from netzooe_eservice_api.error import APIError
from netzooe_eservice_api.error import AuthenticationError
from netzooe_eservice_api.error import InvalidJsonError


async def create_client(mock_api: aioresponses, /, *, repeat: bool | int = False) -> NetzOOEeServiceAPI:
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
    )

    return client


async def create_logged_in_client(mock_api: aioresponses, /, *, repeat: bool | int = False) -> NetzOOEeServiceAPI:
    client: NetzOOEeServiceAPI = await create_client(mock_api, repeat=repeat)

    await client.login()
    return client


class TestHappyPathNetzOOEeServiceAPI:
    @pytest.mark.asyncio
    async def test_login(self, snapshot: SnapshotAssertion) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            assert client.xsrf_token == "mocked-token-value"  # noqa: S105
            await client.logout()
            assert client.xsrf_token == ""

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_reconnect(self, snapshot: SnapshotAssertion) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=401, payload={})
            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            result = await client.dashboard()
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_dashboard(self, snapshot: SnapshotAssertion) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            result = await client.dashboard()
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_dashboard_without_login(self, snapshot: SnapshotAssertion) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            result = await client.dashboard()
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "url"),
        [
            (
                [
                    ConsentsStatus.ACTIVE,
                    ConsentsStatus.ACTIVE_UNCHANGEABLE,
                ],
                "https://eservice.netzooe.at/service/v1.0/consents?status=ACTIVE,ACTIVE_UNCHANGEABLE",
            ),
            (
                ConsentsStatus.ACTIVE,
                "https://eservice.netzooe.at/service/v1.0/consents?status=ACTIVE",
            ),
        ],
    )
    async def test_consents(
        self, snapshot: SnapshotAssertion, status: list[ConsentsStatus] | ConsentsStatus | None, url: str
    ) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, payload=[])

            result: list[dict[str, Any]] = await client.consents(status)
            assert result == []
            await client.logout()

            assert mock_api.requests == snapshot

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
        self,
        snapshot: SnapshotAssertion,
        branch: list[ConsumptionsProfilesBranch] | ConsumptionsProfilesBranch | None,
        url: str,
    ) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, payload=[])

            result: list[dict[str, Any]] = await client.consumptions_profiles(branch)
            assert result == []
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_contract_account(self, snapshot: SnapshotAssertion) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/contract-accounts/123/345", status=200, payload={})

            result = await client.contract_accounts(business_partner_number="123", contract_account_number="345")
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("pods", "dimension"),
        [
            (
                [
                    Pod(
                        contract_account_number="123",
                        energy_community_id="345",
                        profile_type="mocked-profile",
                        best_available_granularity="mocked-granularity",
                        meter_point_administration_number="AT123",
                        date_from="2026-01-01",
                        date_to="2026-01-30",
                    )
                ],
                ConsumptionsDimension.ENERGY,
            ),
            (
                [
                    Pod(
                        contract_account_number="123",
                        profile_type="mocked-profile",
                        best_available_granularity="mocked-granularity",
                        meter_point_administration_number="AT123",
                        date_from="2026-01-01",
                        date_to="2026-01-30",
                    )
                ],
                ConsumptionsDimension.ENERGY,
            ),
        ],
    )
    async def test_consumptions_profile(
        self, snapshot: SnapshotAssertion, pods: list[Pod], dimension: ConsumptionsDimension
    ) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.post(
                "https://eservice.netzooe.at/service/v1.0/consumptions/profile/active", status=200, payload=[]
            )

            result: list[dict[str, Any]] = await client.consumptions_profile(pods=pods, dimension=dimension)
            assert result == []
            await client.logout()

            assert mock_api.requests == snapshot


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
    async def test_login_failed(
        self, snapshot: SnapshotAssertion, exception: type[APIError], status: int, message: str
    ) -> None:
        with aioresponses() as mock_api:
            mock_api.post(
                "https://eservice.netzooe.at/service/j_security_check",
                status=status,
            )

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username="test",
                password="test",  # noqa: S106
            )

            with pytest.raises(exception) as error:
                await client.login()

            assert str(error.value) == message
            assert client.xsrf_token == ""

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_session_failed(self, snapshot: SnapshotAssertion) -> None:
        with aioresponses() as mock_api:
            mock_api.post(
                "https://eservice.netzooe.at/service/j_security_check",
                status=200,
            )

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/session",
                status=401,
            )

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username="test",
                password="test",  # noqa: S106
            )

            with pytest.raises(APIError) as error:
                await client.login()

            assert str(error.value) == "401 Unauthorized: No permission -- see authorization schemes"
            assert client.xsrf_token == ""

            assert mock_api.requests == snapshot

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

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("body", "content_type"),
        [
            (
                "<html></html>",
                "text/html",
            ),
            (
                "<html></html>",
                "application/json",
            ),
        ],
    )
    async def test_maintenance_page(self, body: str, content_type: str) -> None:
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/dashboard",
                status=200,
                body=body,
                content_type=content_type,
            )

            with pytest.raises(InvalidJsonError) as error:
                await client.dashboard()

            assert str(error.value) == "200 OK: Request fulfilled, document follows"

            await client.logout()
