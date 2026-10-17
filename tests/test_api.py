# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Netz OÖ eService API client."""

import asyncio
import gc
import warnings
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

import pytest
from aiohttp import ClientError
from aiohttp import ClientSession
from aioresponses import CallbackResult
from aioresponses import aioresponses
from aioresponses.core import RequestCall
from syrupy import SnapshotAssertion
from yarl import URL

from netzooe_eservice_api.api import NetzOOEeServiceAPI
from netzooe_eservice_api.api import Pod
from netzooe_eservice_api.constants import ConsentRequestsStatus
from netzooe_eservice_api.constants import ConsentsStatus
from netzooe_eservice_api.constants import ConsumptionsDimension
from netzooe_eservice_api.constants import ConsumptionsProfilesBranch
from netzooe_eservice_api.constants import Granularity
from netzooe_eservice_api.constants import ProfileType
from netzooe_eservice_api.error import APIError
from netzooe_eservice_api.error import AuthenticationError
from netzooe_eservice_api.error import InvalidJsonError

MOCK_USERNAME: str = "test"
MOCK_CREDENTIAL: str = "test"
MOCK_XSRF: str = "mocked-token-value"
MOCK_NEW_XSRF: str = "mocked-new-token-value"
MOCK_UNKNOWN_STATUS: int = 520


def recorded_calls(mock_api: aioresponses, url_part: str, /) -> list[RequestCall]:
    """Return the recorded calls of all requests whose URL contains `url_part`."""
    assert mock_api.requests is not None
    return [call for (_, url), calls in mock_api.requests.items() if url_part in str(url) for call in calls]


async def count_unclosed_sessions(scenario: Callable[[aioresponses], Awaitable[None]], /) -> int:
    """Run `scenario` with mocked HTTP and count the sessions that are garbage collected without being closed."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)

        with aioresponses() as mock_api:
            await scenario(mock_api)

        # The recorded calls of aioresponses keep the sessions alive.
        del mock_api
        gc.collect()

    return sum("Unclosed client session" in str(warning.message) for warning in caught)


async def create_client(mock_api: aioresponses, /, *, repeat: bool | int = False) -> NetzOOEeServiceAPI:
    """Create a client with mocked login, session and logout endpoints."""
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
        username=MOCK_USERNAME,
        password=MOCK_CREDENTIAL,
    )

    return client


async def create_logged_in_client(mock_api: aioresponses, /, *, repeat: bool | int = False) -> NetzOOEeServiceAPI:
    """Create a client with mocked endpoints and log in."""
    client: NetzOOEeServiceAPI = await create_client(mock_api, repeat=repeat)

    await client.login()
    return client


class TestHappyPathNetzOOEeServiceAPI:
    """Tests for successful API calls."""

    @pytest.mark.asyncio
    async def test_login(self, snapshot: SnapshotAssertion) -> None:
        """Test login and logout set and reset the XSRF token."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            assert client.xsrf_token == MOCK_XSRF
            await client.logout()
            assert client.xsrf_token == ""

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_reconnect(self, snapshot: SnapshotAssertion) -> None:
        """Test a request logs in again after a 401 response."""
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
        """Test getting the dashboard data."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            result = await client.dashboard()
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_dashboard_without_login(self, snapshot: SnapshotAssertion) -> None:
        """Test a request logs in automatically without a prior login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            result = await client.dashboard()
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("branch", "active_only", "url"),
        [
            (
                None,
                None,
                "https://eservice.netzooe.at/service/v1.0/dashboard/headers",
            ),
            (
                ConsumptionsProfilesBranch.ELECTRICITY,
                True,
                "https://eservice.netzooe.at/service/v1.0/dashboard/headers?branch=STROM&activeOnly=true",
            ),
            (
                [
                    ConsumptionsProfilesBranch.ELECTRICITY,
                    ConsumptionsProfilesBranch.GAS,
                ],
                False,
                "https://eservice.netzooe.at/service/v1.0/dashboard/headers?branch=STROM,GAS&activeOnly=false",
            ),
        ],
    )
    async def test_dashboard_headers(
        self,
        *,
        snapshot: SnapshotAssertion,
        branch: list[ConsumptionsProfilesBranch] | ConsumptionsProfilesBranch | None,
        active_only: bool | None,
        url: str,
    ) -> None:
        """Test getting the dashboard headers with different branch and active filters."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, payload=[])

            result: list[dict[str, Any]] = await client.dashboard_headers(branch, active_only=active_only)
            assert result == []
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
        self,
        snapshot: SnapshotAssertion,
        status: list[ConsentsStatus] | ConsentsStatus | None,
        url: str,
    ) -> None:
        """Test getting the consents with different status filters."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, payload=[])

            result: list[dict[str, Any]] = await client.consents(status)
            assert result == []
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "url"),
        [
            (
                None,
                "https://eservice.netzooe.at/service/v1.0/consent-requests",
            ),
            (
                ConsentRequestsStatus.CONFIRMED,
                "https://eservice.netzooe.at/service/v1.0/consent-requests?status=CONFIRMED",
            ),
            (
                [
                    ConsentRequestsStatus.INITIAL,
                    ConsentRequestsStatus.SENT,
                ],
                "https://eservice.netzooe.at/service/v1.0/consent-requests?status=INITIAL,SENT",
            ),
        ],
    )
    async def test_consent_requests(
        self,
        snapshot: SnapshotAssertion,
        status: list[ConsentRequestsStatus] | ConsentRequestsStatus | None,
        url: str,
    ) -> None:
        """Test getting the consent requests with different status filters."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, payload=[])

            result: list[dict[str, Any]] = await client.consent_requests(status)
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
        """Test getting the consumption profiles with different branch filters."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, payload=[])

            result: list[dict[str, Any]] = await client.consumptions_profiles(branch)
            assert result == []
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_consumptions_profiles_active_only(self, snapshot: SnapshotAssertion) -> None:
        """Test getting only the consumption profiles of active points of delivery."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/consumptions/profiles?branch=STROM&activeOnly=true",
                status=200,
                payload=[],
            )

            result: list[dict[str, Any]] = await client.consumptions_profiles(
                ConsumptionsProfilesBranch.ELECTRICITY,
                active_only=True,
            )
            assert result == []
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_contract_account(self, snapshot: SnapshotAssertion) -> None:
        """Test getting the contract account data."""
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
                    ),
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
                    ),
                ],
                ConsumptionsDimension.ENERGY,
            ),
            (
                [
                    Pod(
                        contract_account_number="123",
                        profile_type=ProfileType.ACTIVE_CURRENT,
                        best_available_granularity=Granularity.QUARTER_OF_AN_HOUR,
                        meter_point_administration_number="AT123",
                        date_from="2026-01-01",
                        date_to="2026-01-30",
                    ),
                ],
                ConsumptionsDimension.POWER,
            ),
        ],
    )
    async def test_consumptions_profile(
        self,
        snapshot: SnapshotAssertion,
        pods: list[Pod],
        dimension: ConsumptionsDimension,
    ) -> None:
        """Test getting the consumption profile for points of delivery."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.post(
                "https://eservice.netzooe.at/service/v1.0/consumptions/profile/active",
                status=200,
                payload=[],
            )

            result: list[dict[str, Any]] = await client.consumptions_profile(pods=pods, dimension=dimension)
            assert result == []
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_post_without_login(self) -> None:
        """Test a POST request as first call sends the XSRF token of the automatic login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            mock_api.post(
                "https://eservice.netzooe.at/service/v1.0/consumptions/profile/active",
                status=200,
                payload=[],
            )

            result: list[dict[str, Any]] = await client.consumptions_profile(pods=[])
            assert result == []

            calls: list[RequestCall] = recorded_calls(mock_api, "profile/active")
            assert calls[0].kwargs["headers"]["x-xsrf-token"] == MOCK_XSRF

            await client.logout()

    @pytest.mark.asyncio
    async def test_concurrent_requests_login_once(self) -> None:
        """Test concurrent requests without a prior login share one login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={}, repeat=2)

            results = await asyncio.gather(client.dashboard(), client.dashboard())
            assert results == [{}, {}]

            assert len(recorded_calls(mock_api, "j_security_check")) == 1

            await client.logout()

    @pytest.mark.asyncio
    async def test_concurrent_requests_relogin_once(self) -> None:
        """Test concurrent requests with an expired token share one re-login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.post("https://eservice.netzooe.at/service/j_security_check", status=200)
            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/session",
                headers={"Set-Cookie": f"XSRF-TOKEN={MOCK_NEW_XSRF}; Path=/; Secure"},
                status=200,
            )
            # Hold the first two responses back until both requests are in flight with the same expired token.
            barrier: asyncio.Barrier = asyncio.Barrier(2)
            calls: int = 0

            async def dashboard(_url: URL, **_kwargs: object) -> CallbackResult:
                nonlocal calls
                calls += 1

                if calls <= barrier.parties:
                    await barrier.wait()
                    return CallbackResult(status=401, payload={})

                return CallbackResult(status=200, payload={})

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", callback=dashboard, repeat=4)

            logins: int = len(recorded_calls(mock_api, "j_security_check"))

            results = await asyncio.gather(client.dashboard(), client.dashboard())
            assert results == [{}, {}]

            assert len(recorded_calls(mock_api, "j_security_check")) == logins + 1
            assert client.xsrf_token == MOCK_NEW_XSRF

            await client.logout()

    @pytest.mark.asyncio
    async def test_late_401_after_relogin(self) -> None:
        """Test a 401 response that arrives after another request already logged in again retries without a login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.post("https://eservice.netzooe.at/service/j_security_check", status=200)
            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/session",
                headers={"Set-Cookie": f"XSRF-TOKEN={MOCK_NEW_XSRF}; Path=/; Secure"},
                status=200,
            )
            # Set by the retry of the first request, i.e. after it logged in again.
            relogged_in: asyncio.Event = asyncio.Event()
            calls: int = 0
            late_call: int = 2

            async def dashboard(_url: URL, **_kwargs: object) -> CallbackResult:
                nonlocal calls
                calls += 1

                if calls == 1:
                    return CallbackResult(status=401, payload={})

                if calls == late_call:
                    # Answer the second request with the expired token only after the first one logged in again.
                    await relogged_in.wait()
                    return CallbackResult(status=401, payload={})

                relogged_in.set()
                return CallbackResult(status=200, payload={})

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", callback=dashboard, repeat=4)

            logins: int = len(recorded_calls(mock_api, "j_security_check"))

            results = await asyncio.gather(client.dashboard(), client.dashboard())
            assert results == [{}, {}]

            assert len(recorded_calls(mock_api, "j_security_check")) == logins + 1
            await client.logout()

    @pytest.mark.asyncio
    async def test_consumptions_profiles_without_branch(self) -> None:
        """Test getting the consumption profiles without passing a branch."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/consumptions/profiles", status=200, payload=[])

            result: list[dict[str, Any]] = await client.consumptions_profiles()
            assert result == []
            await client.logout()

    @pytest.mark.asyncio
    async def test_contract_account_quoted(self) -> None:
        """Test the path parameters of the contract account are URL encoded."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/contract-accounts/1%2F2/3%3F4",
                status=200,
                payload={},
            )

            result = await client.contract_accounts(business_partner_number="1/2", contract_account_number="3?4")
            assert result == {}
            await client.logout()

    @pytest.mark.asyncio
    async def test_contract_account_not_str(self) -> None:
        """Test the path parameters of the contract account still accept values that are not strings."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/contract-accounts/123/345", status=200, payload={})

            business_partner_number: Any = 123
            contract_account_number: Any = 345

            result = await client.contract_accounts(
                business_partner_number=business_partner_number,
                contract_account_number=contract_account_number,
            )
            assert result == {}
            await client.logout()

    @pytest.mark.asyncio
    async def test_login_still_logged_in(self, snapshot: SnapshotAssertion) -> None:
        """Test a login on a session that is still logged in logs out and logs in again."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.post("https://eservice.netzooe.at/service/j_security_check", status=404)
            mock_api.get("https://eservice.netzooe.at/service/logout", status=200)
            mock_api.post("https://eservice.netzooe.at/service/j_security_check", status=200)
            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/session",
                headers={"Set-Cookie": f"XSRF-TOKEN={MOCK_NEW_XSRF}; Path=/; Secure"},
                status=200,
            )
            mock_api.get("https://eservice.netzooe.at/service/logout", status=200)

            await client.login()
            assert client.xsrf_token == MOCK_NEW_XSRF
            await client.logout()

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_logout_without_session(self) -> None:
        """Test logout without a session sends no request and resets the XSRF token."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)
            client.xsrf_token = MOCK_XSRF

            await client.logout()

            assert client.xsrf_token == ""
            assert mock_api.requests == {}

    @pytest.mark.asyncio
    async def test_passed_session_is_not_closed(self) -> None:
        """Test a passed session is not closed on logout."""
        with aioresponses() as mock_api:
            create_client_mocks: NetzOOEeServiceAPI = await create_client(mock_api)
            del create_client_mocks

            async with ClientSession() as session:
                client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                    username=MOCK_USERNAME,
                    password=MOCK_CREDENTIAL,
                    session=session,
                )
                await client.login()
                await client.logout()

                assert not session.closed

    @pytest.mark.asyncio
    async def test_passed_closed_session(self) -> None:
        """Test a passed but closed session is replaced by an own session that is closed on logout."""

        async def scenario(mock_api: aioresponses) -> None:
            create_client_mocks: NetzOOEeServiceAPI = await create_client(mock_api)
            del create_client_mocks

            session: ClientSession = ClientSession()
            await session.close()

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username=MOCK_USERNAME,
                password=MOCK_CREDENTIAL,
                session=session,
            )
            await client.login()
            assert client.xsrf_token == MOCK_XSRF

            await client.logout()

        assert await count_unclosed_sessions(scenario) == 0


class TestUnhappyPathNetzOOEeServiceAPI:
    """Tests for failing API calls."""

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
        self,
        snapshot: SnapshotAssertion,
        exception: type[APIError],
        status: int,
        message: str,
    ) -> None:
        """Test a failed login raises the matching error."""
        with aioresponses() as mock_api:
            mock_api.post(
                "https://eservice.netzooe.at/service/j_security_check",
                status=status,
            )

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username=MOCK_USERNAME,
                password=MOCK_CREDENTIAL,
            )

            with pytest.raises(exception) as error:
                await client.login()

            assert str(error.value) == message
            assert client.xsrf_token == ""

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_session_failed(self, snapshot: SnapshotAssertion) -> None:
        """Test a failed session request raises an API error."""
        with aioresponses() as mock_api:
            mock_api.post(
                "https://eservice.netzooe.at/service/j_security_check",
                status=200,
            )

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/session",
                status=401,
                body="mocked body",
            )

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username=MOCK_USERNAME,
                password=MOCK_CREDENTIAL,
            )

            with pytest.raises(APIError) as error:
                await client.login()

            assert str(error.value) == "401 Unauthorized: No permission -- see authorization schemes"
            assert error.value.detail == "mocked body"
            assert client.xsrf_token == ""

            assert mock_api.requests == snapshot

    @pytest.mark.asyncio
    async def test_session_without_xsrf_cookie(self) -> None:
        """Test a session response without an XSRF cookie raises an API error and closes the own session."""

        async def scenario(mock_api: aioresponses) -> None:
            mock_api.post("https://eservice.netzooe.at/service/j_security_check", status=200)
            mock_api.get("https://eservice.netzooe.at/service/v1.0/session", status=200)

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username=MOCK_USERNAME,
                password=MOCK_CREDENTIAL,
            )

            with pytest.raises(APIError) as error:
                await client.login()

            assert str(error.value) == "The session response contains no XSRF token"
            assert client.xsrf_token == ""

        assert await count_unclosed_sessions(scenario) == 0

    @pytest.mark.asyncio
    async def test_reconnect_failed(self) -> None:
        """Test a second 401 response raises an authentication error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=401, repeat=2, payload={})

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "401 Unauthorized: No permission -- see authorization schemes"
            assert client.xsrf_token == ""

            await client.logout()

    @pytest.mark.asyncio
    async def test_client_error(self) -> None:
        """Test an aiohttp client error is raised as an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/dashboard",
                exception=ClientError("mocked error"),
            )

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "mocked error"

            await client.logout()

    @pytest.mark.asyncio
    async def test_client_error_keeps_login(self) -> None:
        """Test a client error keeps the session and its login, so the next request does not log in again."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/dashboard",
                exception=ClientError("mocked error"),
            )
            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            with pytest.raises(APIError):
                await client.dashboard()

            assert client.xsrf_token == MOCK_XSRF

            result = await client.dashboard()
            assert result == {}

            assert len(recorded_calls(mock_api, "j_security_check")) == 1
            await client.logout()

    @pytest.mark.asyncio
    async def test_concurrent_requests_failed_login_once(self) -> None:
        """Test concurrent requests with rejected credentials share one failed login instead of logging in each."""
        with aioresponses() as mock_api:
            mock_api.post("https://eservice.netzooe.at/service/j_security_check", status=401, repeat=True)

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            results = await asyncio.gather(
                client.dashboard(),
                client.consents(),
                client.consumptions_profiles(),
                return_exceptions=True,
            )

            assert [type(result) for result in results] == [AuthenticationError] * 3
            assert len(recorded_calls(mock_api, "j_security_check")) == 1

    @pytest.mark.asyncio
    async def test_passed_session_closed_after_login(self) -> None:
        """Test a request logs in again if the passed session was closed after the login."""

        async def scenario(mock_api: aioresponses) -> None:
            create_client_mocks: NetzOOEeServiceAPI = await create_client(mock_api, repeat=2)
            del create_client_mocks

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload={})

            session: ClientSession = ClientSession()
            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username=MOCK_USERNAME,
                password=MOCK_CREDENTIAL,
                session=session,
            )
            await client.login()
            await session.close()
            logins: int = len(recorded_calls(mock_api, "j_security_check"))

            result = await client.dashboard()
            assert result == {}

            assert len(recorded_calls(mock_api, "j_security_check")) == logins + 1
            await client.logout()

        assert await count_unclosed_sessions(scenario) == 0

    @pytest.mark.asyncio
    async def test_internal_server_error(self) -> None:
        """Test an internal server error is raised as an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/dashboard",
                status=500,
                body="mocked body",
            )

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "500 Internal Server Error: Server got itself in trouble"
            assert error.value.detail == "mocked body"

            await client.logout()

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
        """Test a maintenance page response raises an invalid JSON error."""
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
            assert error.value.detail == body

            await client.logout()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "exception"),
        [
            (200, InvalidJsonError),
            (500, APIError),
        ],
    )
    async def test_undecodable_body(self, status: int, exception: type[APIError]) -> None:
        """Test a body that is not valid in its charset is raised as an API error with the decodable part."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/dashboard",
                status=status,
                body="mocked body \xfc".encode("latin-1"),
                content_type="application/json",
            )

            with pytest.raises(exception) as error:
                await client.dashboard()

            assert type(error.value) is exception
            assert error.value.detail == "mocked body \ufffd"

            await client.logout()

    @pytest.mark.asyncio
    async def test_unexpected_json_shape(self) -> None:
        """Test a JSON array where an object is expected raises an invalid JSON error instead of returning it."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", status=200, payload=[])

            with pytest.raises(InvalidJsonError) as error:
                await client.dashboard()

            assert error.value.detail == "[]"

            await client.logout()

    @pytest.mark.asyncio
    async def test_empty_body(self) -> None:
        """Test a successful response with an empty body raises an invalid JSON error instead of returning None."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/dashboard",
                status=200,
                body="",
                content_type="application/json",
            )

            with pytest.raises(InvalidJsonError) as error:
                await client.dashboard()

            assert error.value.detail == ""

            await client.logout()

    @pytest.mark.asyncio
    async def test_unknown_status(self) -> None:
        """Test a status code that is not part of HTTPStatus is raised as an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/dashboard",
                status=MOCK_UNKNOWN_STATUS,
                body="mocked body",
            )

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "520 Unknown Status"
            assert error.value.status == MOCK_UNKNOWN_STATUS
            assert error.value.detail == "mocked body"

            await client.logout()

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        """Test a timeout is raised as an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/dashboard", exception=TimeoutError())

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "TimeoutError"

            await client.logout()

    @pytest.mark.asyncio
    async def test_login_client_error(self) -> None:
        """Test an aiohttp client error on login is raised as an API error."""
        with aioresponses() as mock_api:
            mock_api.post(
                "https://eservice.netzooe.at/service/j_security_check",
                exception=ClientError("mocked error"),
            )

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            with pytest.raises(APIError) as error:
                await client.login()

            assert str(error.value) == "mocked error"

    @pytest.mark.asyncio
    async def test_logout_failed(self) -> None:
        """Test a failed logout request raises an API error and still resets the client."""

        async def scenario(mock_api: aioresponses) -> None:
            mock_api.post("https://eservice.netzooe.at/service/j_security_check", status=200)
            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/session",
                headers={"Set-Cookie": "XSRF-TOKEN=mocked-token-value; Path=/; Secure"},
                status=200,
            )
            mock_api.get("https://eservice.netzooe.at/service/logout", status=500, body="mocked body")

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)
            await client.login()

            with pytest.raises(APIError) as error:
                await client.logout()

            assert str(error.value) == "500 Internal Server Error: Server got itself in trouble"
            assert error.value.detail == "mocked body"
            assert client.xsrf_token == ""

        assert await count_unclosed_sessions(scenario) == 0

    @pytest.mark.asyncio
    async def test_logout_client_error(self) -> None:
        """Test an aiohttp client error on logout is raised as an API error and still resets the client."""

        async def scenario(mock_api: aioresponses) -> None:
            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            mock_api.post("https://eservice.netzooe.at/service/j_security_check", status=200)
            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/session",
                headers={"Set-Cookie": "XSRF-TOKEN=mocked-token-value; Path=/; Secure"},
                status=200,
            )
            mock_api.get("https://eservice.netzooe.at/service/logout", exception=ClientError("mocked error"))

            await client.login()

            with pytest.raises(APIError) as error:
                await client.logout()

            assert str(error.value) == "mocked error"
            assert client.xsrf_token == ""

        assert await count_unclosed_sessions(scenario) == 0
