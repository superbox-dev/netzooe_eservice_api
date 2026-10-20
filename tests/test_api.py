# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Netz OÖ eService API client."""

import asyncio
import gc
import warnings
from collections.abc import Awaitable
from collections.abc import Callable
from http import HTTPStatus
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
from netzooe_eservice_api.constants import COMMON_HEADERS
from netzooe_eservice_api.constants import ConsentRequestsStatus
from netzooe_eservice_api.constants import ConsentsStatus
from netzooe_eservice_api.constants import ConsumptionsDimension
from netzooe_eservice_api.constants import ConsumptionsProfilesBranch
from netzooe_eservice_api.constants import Granularity
from netzooe_eservice_api.constants import ProfileType
from netzooe_eservice_api.error import APIError
from netzooe_eservice_api.error import AuthenticationError
from netzooe_eservice_api.error import InvalidJsonError
from tests.test_api_data import MOCK_API_URL
from tests.test_api_data import MOCK_CREDENTIAL
from tests.test_api_data import MOCK_DASHBOARD_URL
from tests.test_api_data import MOCK_LOGIN_URL
from tests.test_api_data import MOCK_LOGOUT_URL
from tests.test_api_data import MOCK_NEW_XSRF
from tests.test_api_data import MOCK_OUTSIDE_XSRF
from tests.test_api_data import MOCK_POD
from tests.test_api_data import MOCK_PROFILE_URL
from tests.test_api_data import MOCK_SESSION_URL
from tests.test_api_data import MOCK_UNKNOWN_STATUS
from tests.test_api_data import MOCK_USERNAME
from tests.test_api_data import MOCK_XSRF


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


def mock_login(mock_api: aioresponses, /, *, xsrf: str = MOCK_XSRF, repeat: bool | int = False) -> None:
    """Mock a successful login whose session response sets the XSRF token `xsrf`."""
    mock_api.post(
        MOCK_LOGIN_URL,
        status=200,
        repeat=repeat,
    )

    mock_api.get(
        MOCK_SESSION_URL,
        headers={
            "Set-Cookie": f"XSRF-TOKEN={xsrf}; Path=/; Secure",
        },
        status=200,
        repeat=repeat,
    )


async def create_client(
    mock_api: aioresponses,
    /,
    *,
    repeat: bool | int = False,
    mocks: bool = True,
    session: ClientSession | None = None,
) -> NetzOOEeServiceAPI:
    """Create a client with mocked login, session and logout endpoints, or without any mocks if `mocks` is false."""
    if mocks:
        mock_login(mock_api, repeat=repeat)

        mock_api.get(
            MOCK_LOGOUT_URL,
            status=200,
            repeat=False,
        )

    client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
        username=MOCK_USERNAME,
        password=MOCK_CREDENTIAL,
        session=session,
    )

    return client


async def create_logged_in_client(mock_api: aioresponses, /, *, repeat: bool | int = False) -> NetzOOEeServiceAPI:
    """Create a client with mocked endpoints and log in."""
    client: NetzOOEeServiceAPI = await create_client(mock_api, repeat=repeat)

    await client.login()
    return client


class TestHappyPathNetzOOEeServiceAPI:
    """Tests for successful API calls."""

    async def test_login(self, snapshot: SnapshotAssertion) -> None:
        """Test login and logout set and reset the XSRF token."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            assert client.xsrf_token == MOCK_XSRF
            await client.logout()
            assert client.xsrf_token == ""

            assert mock_api.requests == snapshot

    async def test_reconnect(self, snapshot: SnapshotAssertion) -> None:
        """Test a request logs in again after a 401 response."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)

            mock_api.get(MOCK_DASHBOARD_URL, status=401, payload={})
            mock_api.get(MOCK_DASHBOARD_URL, status=200, payload={})

            result: dict[str, Any] = await client.dashboard()
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

    async def test_dashboard(self, snapshot: SnapshotAssertion) -> None:
        """Test getting the dashboard data."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(MOCK_DASHBOARD_URL, status=200, payload={})

            result: dict[str, Any] = await client.dashboard()
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

    async def test_dashboard_without_login(self, snapshot: SnapshotAssertion) -> None:
        """Test a request logs in automatically without a prior login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            mock_api.get(MOCK_DASHBOARD_URL, status=200, payload={})

            result: dict[str, Any] = await client.dashboard()
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

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
                "https://eservice.netzooe.at/service/v1.0/dashboard/headers?activeOnly=false",
            ),
        ],
        ids=["no_filter", "single_branch_active_only", "multiple_branches_not_active_only"],
    )
    async def test_dashboard_headers(
        self,
        *,
        snapshot: SnapshotAssertion,
        branch: ConsumptionsProfilesBranch | list[ConsumptionsProfilesBranch] | None,
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
            (
                None,
                "https://eservice.netzooe.at/service/v1.0/consents",
            ),
        ],
        ids=["multiple_statuses", "single_status", "no_status"],
    )
    async def test_consents(
        self,
        snapshot: SnapshotAssertion,
        status: ConsentsStatus | list[ConsentsStatus] | None,
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
        ids=["no_status", "single_status", "multiple_statuses"],
    )
    async def test_consent_requests(
        self,
        snapshot: SnapshotAssertion,
        status: ConsentRequestsStatus | list[ConsentRequestsStatus] | None,
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
        ids=["no_branch", "single_branch"],
    )
    async def test_consumptions_profiles(
        self,
        snapshot: SnapshotAssertion,
        branch: ConsumptionsProfilesBranch | list[ConsumptionsProfilesBranch] | None,
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

    async def test_contract_account(self, snapshot: SnapshotAssertion) -> None:
        """Test getting the contract account data."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/contract-accounts/123/345", status=200, payload={})

            result: dict[str, Any] = await client.contract_accounts(
                business_partner_number="123", contract_account_number="345"
            )
            assert result == {}
            await client.logout()

            assert mock_api.requests == snapshot

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
            (
                [
                    Pod(
                        contract_account_number="123",
                        energy_community_id=None,
                        profile_type=ProfileType.ACTIVE_CURRENT,
                        best_available_granularity=Granularity.QUARTER_OF_AN_HOUR,
                        meter_point_administration_number="AT123",
                        date_from="2026-01-01",
                        date_to="2026-01-30",
                    ),
                    Pod(
                        contract_account_number="456",
                        energy_community_id="789",
                        profile_type=ProfileType.ACTIVE_CURRENT,
                        best_available_granularity=Granularity.QUARTER_OF_AN_HOUR,
                        meter_point_administration_number="AT456",
                        date_from="2026-01-01",
                        date_to="2026-01-30",
                    ),
                ],
                ConsumptionsDimension.ENERGY,
            ),
        ],
        ids=["energy_community_energy", "no_energy_community_energy", "enums_power", "multiple_pods_energy"],
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
                MOCK_PROFILE_URL,
                status=200,
                payload=[],
            )

            result: list[dict[str, Any]] = await client.consumptions_profile(pods=pods, dimension=dimension)
            assert result == []
            await client.logout()

            assert mock_api.requests == snapshot

    async def test_post_without_login(self) -> None:
        """Test a POST request as first call sends the XSRF token of the automatic login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            mock_api.post(
                MOCK_PROFILE_URL,
                status=200,
                payload=[],
            )

            result: list[dict[str, Any]] = await client.consumptions_profile(pods=[])
            assert result == []

            calls: list[RequestCall] = recorded_calls(mock_api, "profile/active")
            assert calls[0].kwargs["headers"]["x-xsrf-token"] == MOCK_XSRF

            await client.logout()

    async def test_concurrent_requests_login_once(self) -> None:
        """Test concurrent requests without a prior login share one login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            mock_api.get(MOCK_DASHBOARD_URL, status=200, payload={}, repeat=2)

            results: tuple[dict[str, Any], dict[str, Any]] = await asyncio.gather(
                client.dashboard(), client.dashboard()
            )
            assert results == [{}, {}]

            assert len(recorded_calls(mock_api, "j_security_check")) == 1

            await client.logout()

    async def test_concurrent_requests_relogin_once(self) -> None:
        """Test concurrent requests with an expired token share one re-login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_login(mock_api, xsrf=MOCK_NEW_XSRF)
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

            mock_api.get(MOCK_DASHBOARD_URL, callback=dashboard, repeat=4)

            logins: int = len(recorded_calls(mock_api, "j_security_check"))

            results: tuple[dict[str, Any], dict[str, Any]] = await asyncio.gather(
                client.dashboard(), client.dashboard()
            )
            assert results == [{}, {}]

            assert len(recorded_calls(mock_api, "j_security_check")) == logins + 1
            assert client.xsrf_token == MOCK_NEW_XSRF

            await client.logout()

    async def test_late_401_after_relogin(self) -> None:
        """Test a 401 response that arrives after another request already logged in again retries without a login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_login(mock_api, xsrf=MOCK_NEW_XSRF)
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

            mock_api.get(MOCK_DASHBOARD_URL, callback=dashboard, repeat=4)

            logins: int = len(recorded_calls(mock_api, "j_security_check"))

            results: tuple[dict[str, Any], dict[str, Any]] = await asyncio.gather(
                client.dashboard(), client.dashboard()
            )
            assert results == [{}, {}]

            assert len(recorded_calls(mock_api, "j_security_check")) == logins + 1
            await client.logout()

    async def test_contract_account_quoted(self) -> None:
        """Test the path parameters of the contract account are URL encoded."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                "https://eservice.netzooe.at/service/v1.0/contract-accounts/1%2F2/3%3F4",
                status=200,
                payload={},
            )

            result: dict[str, Any] = await client.contract_accounts(
                business_partner_number="1/2", contract_account_number="3?4"
            )
            assert result == {}
            await client.logout()

    async def test_contract_account_not_str(self) -> None:
        """Test the path parameters of the contract account still accept values that are not strings."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get("https://eservice.netzooe.at/service/v1.0/contract-accounts/123/345", status=200, payload={})

            business_partner_number: Any = 123
            contract_account_number: Any = 345

            result: dict[str, Any] = await client.contract_accounts(
                business_partner_number=business_partner_number,
                contract_account_number=contract_account_number,
            )
            assert result == {}
            await client.logout()

    async def test_login_still_logged_in(self, snapshot: SnapshotAssertion) -> None:
        """Test a login on a session that is still logged in logs out and logs in again."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.post(MOCK_LOGIN_URL, status=404)
            mock_api.get(MOCK_LOGOUT_URL, status=200)
            mock_login(mock_api, xsrf=MOCK_NEW_XSRF)
            mock_api.get(MOCK_LOGOUT_URL, status=200)

            await client.login()
            assert client.xsrf_token == MOCK_NEW_XSRF
            await client.logout()

            assert mock_api.requests == snapshot

    async def test_logout_without_session(self) -> None:
        """Test logout without a session sends no request and resets the XSRF token."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)
            client.xsrf_token = MOCK_XSRF

            await client.logout()

            assert client.xsrf_token == ""
            assert mock_api.requests == {}

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

    async def test_post_reconnect_sends_new_token(self) -> None:
        """Test the retry of a POST request after a 401 response sends the XSRF token of the new login."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_login(mock_api, xsrf=MOCK_NEW_XSRF)
            mock_api.post(MOCK_PROFILE_URL, status=401, payload={})
            mock_api.post(MOCK_PROFILE_URL, status=200, payload=[])

            result: list[dict[str, Any]] = await client.consumptions_profile(pods=[])
            assert result == []

            calls: list[RequestCall] = recorded_calls(mock_api, "profile/active")
            assert [call.kwargs["headers"]["x-xsrf-token"] for call in calls] == [MOCK_XSRF, MOCK_NEW_XSRF]
            assert calls[0].kwargs["json"] == calls[1].kwargs["json"]

            await client.logout()

    async def test_request_after_logout(self) -> None:
        """Test a request after a logout logs in again on a new own session that is closed on the next logout."""

        async def scenario(mock_api: aioresponses) -> None:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)
            logins: int = len(recorded_calls(mock_api, "j_security_check"))

            mock_api.get(MOCK_DASHBOARD_URL, status=200, payload={})
            mock_api.get(MOCK_LOGOUT_URL, status=200)

            await client.logout()

            result: dict[str, Any] = await client.dashboard()
            assert result == {}
            assert client.xsrf_token == MOCK_XSRF
            assert len(recorded_calls(mock_api, "j_security_check")) == logins + 1

            await client.logout()

        assert await count_unclosed_sessions(scenario) == 0

    async def test_logout_twice(self) -> None:
        """Test a second logout after the own session is closed sends no request."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            await client.logout()
            await client.logout()

            assert len(recorded_calls(mock_api, "logout")) == 1
            assert client.xsrf_token == ""

    async def test_login_after_failed_login(self) -> None:
        """Test a login after a failed login is not answered with the result of the failed one."""
        with aioresponses() as mock_api:
            mock_api.post(MOCK_LOGIN_URL, status=401)
            mock_login(mock_api)

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            with pytest.raises(AuthenticationError):
                await client.login()

            await client.login()
            assert client.xsrf_token == MOCK_XSRF

            mock_api.get(MOCK_LOGOUT_URL, status=200)
            await client.logout()

    async def test_cancelled_login_caller(self) -> None:
        """Test cancelling one caller of a shared login does not cancel the login of the other callers."""
        with aioresponses() as mock_api:
            started: asyncio.Event = asyncio.Event()
            release: asyncio.Event = asyncio.Event()

            async def security_check(_url: URL, **_kwargs: object) -> CallbackResult:
                started.set()
                await release.wait()
                return CallbackResult(status=200)

            mock_api.post(MOCK_LOGIN_URL, callback=security_check)
            mock_api.get(
                MOCK_SESSION_URL,
                headers={"Set-Cookie": f"XSRF-TOKEN={MOCK_XSRF}; Path=/; Secure"},
                status=200,
            )
            mock_api.get(MOCK_LOGOUT_URL, status=200)

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            cancelled: asyncio.Task[None] = asyncio.create_task(client.login())
            waiting: asyncio.Task[None] = asyncio.create_task(client.login())
            await started.wait()

            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled

            release.set()
            await waiting

            assert client.xsrf_token == MOCK_XSRF
            assert len(recorded_calls(mock_api, "j_security_check")) == 1

            await client.logout()

    @pytest.mark.parametrize(
        ("request_method", "url"),
        [
            (
                lambda client: client.dashboard_headers([]),
                f"{MOCK_API_URL}/dashboard/headers",
            ),
            (
                lambda client: client.consents([]),
                f"{MOCK_API_URL}/consents",
            ),
            (
                lambda client: client.consent_requests([]),
                f"{MOCK_API_URL}/consent-requests",
            ),
            (
                lambda client: client.consumptions_profiles([], active_only=True),
                f"{MOCK_API_URL}/consumptions/profiles?activeOnly=true",
            ),
            (
                lambda client: client.consumptions_profiles((ConsumptionsProfilesBranch.GAS,)),
                f"{MOCK_API_URL}/consumptions/profiles?branch=GAS",
            ),
            (
                lambda client: client.dashboard_headers({ConsumptionsProfilesBranch.ELECTRICITY}),
                f"{MOCK_API_URL}/dashboard/headers?branch=STROM",
            ),
            (
                lambda client: client.consumptions_profiles(
                    [ConsumptionsProfilesBranch.GAS, ConsumptionsProfilesBranch.GAS],
                ),
                f"{MOCK_API_URL}/consumptions/profiles?branch=GAS",
            ),
            (
                lambda client: client.consumptions_profiles(
                    [ConsumptionsProfilesBranch.GAS, ConsumptionsProfilesBranch.ELECTRICITY],
                    active_only=True,
                ),
                f"{MOCK_API_URL}/consumptions/profiles?activeOnly=true",
            ),
            (
                lambda client: client.consents(status for status in [ConsentsStatus.ACTIVE]),
                f"{MOCK_API_URL}/consents?status=ACTIVE",
            ),
            (
                lambda client: client.consent_requests(set()),
                f"{MOCK_API_URL}/consent-requests",
            ),
        ],
        ids=[
            "dashboard_headers_empty_list",
            "consents_empty_list",
            "consent_requests_empty_list",
            "consumptions_profiles_empty_list_active_only",
            "consumptions_profiles_tuple",
            "dashboard_headers_set",
            "consumptions_profiles_duplicate_branch",
            "consumptions_profiles_multiple_branches_active_only",
            "consents_generator",
            "consent_requests_empty_set",
        ],
    )
    async def test_empty_filter(
        self,
        request_method: Callable[[NetzOOEeServiceAPI], Awaitable[list[dict[str, Any]]]],
        url: str,
    ) -> None:
        """Test an empty filter or both branches are no filter, duplicates are removed and any iterable works."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, payload=[])

            result: list[dict[str, Any]] = await request_method(client)
            assert result == []
            assert len(recorded_calls(mock_api, url.removeprefix(MOCK_API_URL))) == 1

            await client.logout()

    async def test_headers(self) -> None:
        """Test the headers contain the common headers, the content type and the current XSRF token."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            assert client.headers == {**COMMON_HEADERS, "Content-Type": "application/json", "x-xsrf-token": ""}

            await client.login()
            assert client.headers["x-xsrf-token"] == MOCK_XSRF

            await client.logout()
            assert client.headers["x-xsrf-token"] == ""

    async def test_xsrf_token_set_from_outside(self) -> None:
        """Test an XSRF token set from outside is discarded on a new own session, which has none of its cookies."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)
            client.xsrf_token = MOCK_OUTSIDE_XSRF

            mock_api.get(MOCK_DASHBOARD_URL, status=200, payload={})

            result: dict[str, Any] = await client.dashboard()
            assert result == {}

            calls: list[RequestCall] = recorded_calls(mock_api, "dashboard")
            assert calls[0].kwargs["headers"]["x-xsrf-token"] == MOCK_XSRF
            assert len(recorded_calls(mock_api, "j_security_check")) == 1

            await client.logout()

    @pytest.mark.parametrize(
        ("statuses", "tokens"),
        [
            ([200], [MOCK_OUTSIDE_XSRF]),
            ([401, 200], [MOCK_OUTSIDE_XSRF, MOCK_XSRF]),
        ],
        ids=["token_accepted", "token_replaced_after_401"],
    )
    async def test_xsrf_token_set_from_outside_passed_session(self, statuses: list[int], tokens: list[str]) -> None:
        """Test an XSRF token set from outside on a passed session is sent, and replaced by a login after a 401."""
        with aioresponses() as mock_api:
            create_client_mocks: NetzOOEeServiceAPI = await create_client(mock_api)
            del create_client_mocks

            for status in statuses:
                mock_api.get(MOCK_DASHBOARD_URL, status=status, payload={})

            async with ClientSession() as session:
                client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                    username=MOCK_USERNAME,
                    password=MOCK_CREDENTIAL,
                    session=session,
                )
                client.xsrf_token = MOCK_OUTSIDE_XSRF

                result: dict[str, Any] = await client.dashboard()
                assert result == {}

                calls: list[RequestCall] = recorded_calls(mock_api, "dashboard")
                assert [call.kwargs["headers"]["x-xsrf-token"] for call in calls] == tokens
                assert len(recorded_calls(mock_api, "j_security_check")) == len(statuses) - 1

                await client.logout()

    async def test_login_still_logged_in_logout_failed(self) -> None:
        """Test a failed logout of a still logged in session is ignored, the second login decides."""
        with aioresponses() as mock_api:
            mock_api.post(MOCK_LOGIN_URL, status=404)
            mock_api.get(MOCK_LOGOUT_URL, status=500, body="mocked body")
            mock_login(mock_api)
            mock_api.get(MOCK_LOGOUT_URL, status=200)

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            await client.login()
            assert client.xsrf_token == MOCK_XSRF

            await client.logout()

    async def test_logout_during_request(self) -> None:
        """Test a logout while a request is in flight resets the token, so the next request logs in again."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)
            logins: int = len(recorded_calls(mock_api, "j_security_check"))

            started: asyncio.Event = asyncio.Event()
            release: asyncio.Event = asyncio.Event()

            async def dashboard(_url: URL, **_kwargs: object) -> CallbackResult:
                started.set()
                await release.wait()
                return CallbackResult(status=200, payload={})

            mock_api.get(MOCK_DASHBOARD_URL, callback=dashboard, repeat=2)
            mock_api.get(MOCK_LOGOUT_URL, status=200)

            request: asyncio.Task[dict[str, Any]] = asyncio.create_task(client.dashboard())
            await started.wait()
            await client.logout()
            release.set()

            assert await request == {}
            assert client.xsrf_token == ""

            result: dict[str, Any] = await client.dashboard()
            assert result == {}
            assert len(recorded_calls(mock_api, "j_security_check")) == logins + 1

            await client.logout()

    async def test_cancelled_request(self) -> None:
        """Test a cancelled request is not raised as an API error and keeps the session and its login."""

        async def scenario(mock_api: aioresponses) -> None:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            started: asyncio.Event = asyncio.Event()

            async def dashboard(_url: URL, **_kwargs: object) -> CallbackResult:
                # The cancelled call keeps the mock registered, only the first call never answers.
                if not started.is_set():
                    started.set()
                    await asyncio.Event().wait()

                return CallbackResult(status=200, payload={})

            mock_api.get(MOCK_DASHBOARD_URL, callback=dashboard, repeat=True)

            request: asyncio.Task[dict[str, Any]] = asyncio.create_task(client.dashboard())
            await started.wait()
            request.cancel()

            with pytest.raises(asyncio.CancelledError):
                await request

            assert client.xsrf_token == MOCK_XSRF

            result: dict[str, Any] = await client.dashboard()
            assert result == {}
            assert len(recorded_calls(mock_api, "j_security_check")) == 1

            await client.logout()

        assert await count_unclosed_sessions(scenario) == 0


class TestUnhappyPathNetzOOEeServiceAPI:
    """Tests for failing API calls."""

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
        ids=["unauthorized", "bad_request"],
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
                MOCK_LOGIN_URL,
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

    async def test_session_failed(self, snapshot: SnapshotAssertion) -> None:
        """Test a failed session request raises an API error."""
        with aioresponses() as mock_api:
            mock_api.post(
                MOCK_LOGIN_URL,
                status=200,
            )

            mock_api.get(
                MOCK_SESSION_URL,
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

    @pytest.mark.parametrize(
        "headers",
        [
            {},
            {"Set-Cookie": "XSRF-TOKEN=; Path=/; Secure"},
            {"Set-Cookie": "OTHER=mocked-value; Path=/; Secure"},
        ],
        ids=["no_cookie", "empty_xsrf_cookie", "other_cookie"],
    )
    async def test_session_without_xsrf_cookie(self, headers: dict[str, str]) -> None:
        """Test a session response without a non-empty XSRF cookie raises an API error and closes the own session."""

        async def scenario(mock_api: aioresponses) -> None:
            mock_api.post(MOCK_LOGIN_URL, status=200)
            mock_api.get(MOCK_SESSION_URL, status=200, headers=headers)

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username=MOCK_USERNAME,
                password=MOCK_CREDENTIAL,
            )

            with pytest.raises(APIError) as error:
                await client.login()

            assert str(error.value) == "The session response contains no XSRF token"
            assert client.xsrf_token == ""

        assert await count_unclosed_sessions(scenario) == 0

    async def test_reconnect_failed(self) -> None:
        """Test a second 401 response raises an authentication error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)
            logins: int = len(recorded_calls(mock_api, "j_security_check"))

            mock_api.get(MOCK_DASHBOARD_URL, status=401, repeat=2, payload={})

            with pytest.raises(AuthenticationError) as error:
                await client.dashboard()

            assert str(error.value) == "401 Unauthorized: No permission -- see authorization schemes"
            assert client.xsrf_token == ""
            assert len(recorded_calls(mock_api, "j_security_check")) == logins + 1

            await client.logout()

    async def test_client_error(self) -> None:
        """Test an aiohttp client error is raised as an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                MOCK_DASHBOARD_URL,
                exception=ClientError("mocked error"),
            )

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "mocked error"

            await client.logout()

    async def test_client_error_keeps_login(self) -> None:
        """Test a client error keeps the session and its login, so the next request does not log in again."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)

            mock_api.get(
                MOCK_DASHBOARD_URL,
                exception=ClientError("mocked error"),
            )
            mock_api.get(MOCK_DASHBOARD_URL, status=200, payload={})

            with pytest.raises(APIError):
                await client.dashboard()

            assert client.xsrf_token == MOCK_XSRF

            result: dict[str, Any] = await client.dashboard()
            assert result == {}

            assert len(recorded_calls(mock_api, "j_security_check")) == 1
            await client.logout()

    async def test_concurrent_requests_failed_login_once(self) -> None:
        """Test concurrent requests with rejected credentials share one failed login instead of logging in each."""
        with aioresponses() as mock_api:
            mock_api.post(MOCK_LOGIN_URL, status=401, repeat=True)

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            results: tuple[
                dict[str, Any] | BaseException,
                list[dict[str, Any]] | BaseException,
                list[dict[str, Any]] | BaseException,
            ] = await asyncio.gather(
                client.dashboard(),
                client.consents(),
                client.consumptions_profiles(),
                return_exceptions=True,
            )

            assert [type(result) for result in results] == [AuthenticationError] * 3
            assert len(recorded_calls(mock_api, "j_security_check")) == 1

    async def test_passed_session_closed_after_login(self) -> None:
        """Test a request logs in again if the passed session was closed after the login."""

        async def scenario(mock_api: aioresponses) -> None:
            create_client_mocks: NetzOOEeServiceAPI = await create_client(mock_api, repeat=2)
            del create_client_mocks

            mock_api.get(MOCK_DASHBOARD_URL, status=200, payload={})

            session: ClientSession = ClientSession()
            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                username=MOCK_USERNAME,
                password=MOCK_CREDENTIAL,
                session=session,
            )
            await client.login()
            await session.close()
            logins: int = len(recorded_calls(mock_api, "j_security_check"))

            result: dict[str, Any] = await client.dashboard()
            assert result == {}

            assert len(recorded_calls(mock_api, "j_security_check")) == logins + 1
            await client.logout()

        assert await count_unclosed_sessions(scenario) == 0

    async def test_internal_server_error(self) -> None:
        """Test an internal server error is raised as an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                MOCK_DASHBOARD_URL,
                status=500,
                body="mocked body",
            )

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "500 Internal Server Error: Server got itself in trouble"
            assert error.value.detail == "mocked body"

            await client.logout()

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
        ids=["html_content_type", "json_content_type"],
    )
    async def test_maintenance_page(self, body: str, content_type: str) -> None:
        """Test a maintenance page response raises an invalid JSON error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                MOCK_DASHBOARD_URL,
                status=200,
                body=body,
                content_type=content_type,
            )

            with pytest.raises(InvalidJsonError) as error:
                await client.dashboard()

            assert str(error.value) == "200 OK: Request fulfilled, document follows"
            assert error.value.detail == body

            await client.logout()

    @pytest.mark.parametrize(
        ("status", "exception"),
        [
            (200, InvalidJsonError),
            (500, APIError),
        ],
        ids=["ok", "server_error"],
    )
    async def test_undecodable_body(self, status: int, exception: type[APIError]) -> None:
        """Test a body that is not valid in its charset is raised as an API error with the decodable part."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                MOCK_DASHBOARD_URL,
                status=status,
                body="mocked body \xfc".encode("latin-1"),
                content_type="application/json",
            )

            with pytest.raises(exception) as error:
                await client.dashboard()

            assert type(error.value) is exception
            assert error.value.detail == "mocked body \ufffd"

            await client.logout()

    @pytest.mark.parametrize(
        ("request_method", "url", "body"),
        [
            (NetzOOEeServiceAPI.dashboard, MOCK_DASHBOARD_URL, "[]"),
            (NetzOOEeServiceAPI.dashboard, MOCK_DASHBOARD_URL, "null"),
            (NetzOOEeServiceAPI.dashboard, MOCK_DASHBOARD_URL, "1"),
            (NetzOOEeServiceAPI.dashboard, MOCK_DASHBOARD_URL, '"mocked"'),
            (NetzOOEeServiceAPI.consents, "https://eservice.netzooe.at/service/v1.0/consents", "{}"),
            (NetzOOEeServiceAPI.consents, "https://eservice.netzooe.at/service/v1.0/consents", "true"),
        ],
        ids=[
            "dashboard_list",
            "dashboard_null",
            "dashboard_number",
            "dashboard_string",
            "consents_dict",
            "consents_bool",
        ],
    )
    async def test_unexpected_json_shape(
        self,
        request_method: Callable[[NetzOOEeServiceAPI], Awaitable[Any]],
        url: str,
        body: str,
    ) -> None:
        """Test valid JSON of another shape than expected raises an invalid JSON error instead of returning it."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(url, status=200, body=body, content_type="application/json")

            with pytest.raises(InvalidJsonError) as error:
                await request_method(client)

            assert error.value.detail == body

            await client.logout()

    async def test_empty_body(self) -> None:
        """Test a successful response with an empty body raises an invalid JSON error instead of returning None."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                MOCK_DASHBOARD_URL,
                status=200,
                body="",
                content_type="application/json",
            )

            with pytest.raises(InvalidJsonError) as error:
                await client.dashboard()

            assert error.value.detail == ""

            await client.logout()

    async def test_unknown_status(self) -> None:
        """Test a status code that is not part of HTTPStatus is raised as an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(
                MOCK_DASHBOARD_URL,
                status=MOCK_UNKNOWN_STATUS,
                body="mocked body",
            )

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "520 Unknown Status"
            assert error.value.status == MOCK_UNKNOWN_STATUS
            assert error.value.detail == "mocked body"

            await client.logout()

    async def test_timeout(self) -> None:
        """Test a timeout is raised as an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(MOCK_DASHBOARD_URL, exception=TimeoutError())

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert str(error.value) == "TimeoutError"

            await client.logout()

    @pytest.mark.parametrize(
        ("url", "exception", "message"),
        [
            (MOCK_LOGIN_URL, ClientError("mocked error"), "mocked error"),
            (MOCK_LOGIN_URL, TimeoutError(), "TimeoutError"),
            (MOCK_SESSION_URL, ClientError("mocked error"), "mocked error"),
        ],
        ids=["login_client_error", "login_timeout", "session_client_error"],
    )
    async def test_login_client_error(self, url: str, exception: Exception, message: str) -> None:
        """Test an aiohttp client error or a timeout on login is raised as an API error and closes the own session."""

        async def scenario(mock_api: aioresponses) -> None:
            if url == MOCK_SESSION_URL:
                mock_api.post(MOCK_LOGIN_URL, status=200)

            mock_api.add(url, "POST" if url == MOCK_LOGIN_URL else "GET", exception=exception)

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            with pytest.raises(APIError) as error:
                await client.login()

            assert type(error.value) is APIError
            assert str(error.value) == message
            assert client.xsrf_token == ""

        assert await count_unclosed_sessions(scenario) == 0

    async def test_logout_failed(self) -> None:
        """Test a failed logout request raises an API error and still resets the client."""

        async def scenario(mock_api: aioresponses) -> None:
            mock_login(mock_api)
            mock_api.get(MOCK_LOGOUT_URL, status=500, body="mocked body")

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)
            await client.login()

            with pytest.raises(APIError) as error:
                await client.logout()

            assert str(error.value) == "500 Internal Server Error: Server got itself in trouble"
            assert error.value.detail == "mocked body"
            assert client.xsrf_token == ""

        assert await count_unclosed_sessions(scenario) == 0

    async def test_logout_client_error(self) -> None:
        """Test an aiohttp client error on logout is raised as an API error and still resets the client."""

        async def scenario(mock_api: aioresponses) -> None:
            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            mock_login(mock_api)
            mock_api.get(MOCK_LOGOUT_URL, exception=ClientError("mocked error"))

            await client.login()

            with pytest.raises(APIError) as error:
                await client.logout()

            assert str(error.value) == "mocked error"
            assert client.xsrf_token == ""

        assert await count_unclosed_sessions(scenario) == 0

    async def test_relogin_rejected(self) -> None:
        """Test rejected credentials on the login after a 401 response raise an authentication error."""

        async def scenario(mock_api: aioresponses) -> None:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(MOCK_DASHBOARD_URL, status=401, payload={})
            mock_api.post(MOCK_LOGIN_URL, status=401)

            with pytest.raises(AuthenticationError):
                await client.dashboard()

            assert client.xsrf_token == ""
            assert len(recorded_calls(mock_api, "dashboard")) == 1

        assert await count_unclosed_sessions(scenario) == 0

    async def test_retry_other_error(self) -> None:
        """Test an error other than 401 on the retry after a new login is raised as that error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api, repeat=2)

            mock_api.get(MOCK_DASHBOARD_URL, status=401, payload={})
            mock_api.get(MOCK_DASHBOARD_URL, status=500, body="mocked body")

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert type(error.value) is APIError
            assert error.value.status == HTTPStatus.INTERNAL_SERVER_ERROR
            assert error.value.detail == "mocked body"

            await client.logout()

    @pytest.mark.parametrize(
        "status", [400, 403, 404, 503], ids=["bad_request", "forbidden", "not_found", "service_unavailable"]
    )
    async def test_error_status_not_retried(self, status: int) -> None:
        """Test an error status other than 401 is raised without a new login or a retry."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(MOCK_DASHBOARD_URL, status=status, body="mocked body")

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert type(error.value) is APIError
            assert error.value.status == status
            assert client.xsrf_token == MOCK_XSRF
            assert len(recorded_calls(mock_api, "dashboard")) == 1
            assert len(recorded_calls(mock_api, "j_security_check")) == 1

            await client.logout()

    async def test_post_error(self) -> None:
        """Test an error response of a POST request is raised as an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.post(MOCK_PROFILE_URL, status=500, body="mocked body")

            with pytest.raises(APIError) as error:
                await client.consumptions_profile(pods=[])

            assert error.value.status == HTTPStatus.INTERNAL_SERVER_ERROR
            assert error.value.detail == "mocked body"

            await client.logout()

    @pytest.mark.parametrize(
        ("status", "exception"),
        [
            (401, AuthenticationError),
            (500, APIError),
        ],
        ids=["unauthorized", "server_error"],
    )
    async def test_login_still_logged_in_failed(self, status: int, exception: type[APIError]) -> None:
        """Test a failed second login after the logout of a still logged in session raises the matching error."""

        async def scenario(mock_api: aioresponses) -> None:
            mock_api.post(MOCK_LOGIN_URL, status=404)
            mock_api.get(MOCK_LOGOUT_URL, status=200)
            mock_api.post(MOCK_LOGIN_URL, status=status)

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            with pytest.raises(exception) as error:
                await client.login()

            assert type(error.value) is exception
            assert error.value.status == status
            assert client.xsrf_token == ""

        assert await count_unclosed_sessions(scenario) == 0

    async def test_login_still_logged_in_logout_error(self) -> None:
        """Test a client error on the logout of a still logged in session is raised as an API error."""

        async def scenario(mock_api: aioresponses) -> None:
            mock_api.post(MOCK_LOGIN_URL, status=404)
            mock_api.get(MOCK_LOGOUT_URL, exception=ClientError("mocked error"))

            client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(username=MOCK_USERNAME, password=MOCK_CREDENTIAL)

            with pytest.raises(APIError) as error:
                await client.login()

            assert str(error.value) == "mocked error"
            assert len(recorded_calls(mock_api, "j_security_check")) == 1

        assert await count_unclosed_sessions(scenario) == 0

    async def test_passed_session_not_closed_on_login_error(self) -> None:
        """Test a failed login does not close a passed session."""
        with aioresponses() as mock_api:
            mock_api.post(MOCK_LOGIN_URL, status=401)

            async with ClientSession() as session:
                client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
                    username=MOCK_USERNAME,
                    password=MOCK_CREDENTIAL,
                    session=session,
                )

                with pytest.raises(AuthenticationError):
                    await client.login()

                assert not session.closed

    @pytest.mark.parametrize(
        ("request_method", "message"),
        [
            (
                lambda client: client.consents("ACTIVE"),
                "Invalid value for status: 'ACTIVE'",
            ),
            (
                lambda client: client.consent_requests(["CONFIRMED"]),
                "Invalid value for status: 'CONFIRMED'",
            ),
            (
                lambda client: client.dashboard_headers("STROM"),
                "Invalid value for branch: 'STROM'",
            ),
            (
                lambda client: client.consumptions_profiles([ConsumptionsProfilesBranch.GAS, None]),
                "Invalid value for branch: None",
            ),
            (
                lambda client: client.dashboard_headers(active_only="true"),
                "Invalid value for activeOnly: 'true'",
            ),
            (
                lambda client: client.consumptions_profiles(active_only=1),
                "Invalid value for activeOnly: 1",
            ),
            (
                lambda client: client.consumptions_profile([], dimension="ENERGY"),
                "Invalid value for dimension: 'ENERGY'",
            ),
            (
                lambda client: client.consents(ConsentRequestsStatus.CONFIRMED),
                "Invalid value for status: <ConsentRequestsStatus.CONFIRMED: 'CONFIRMED'>",
            ),
            (
                lambda client: client.dashboard_headers(5),
                "Invalid value for branch: 5",
            ),
            (
                lambda client: client.consumptions_profile([], dimension=Granularity.QUARTER_OF_AN_HOUR),
                "Invalid value for dimension: <Granularity.QUARTER_OF_AN_HOUR: 'QUARTER_OF_AN_HOUR'>",
            ),
            (
                lambda client: client.consumptions_profile([{**MOCK_POD, "profile_type": None}]),
                "Invalid value for profile_type: None",
            ),
            (
                lambda client: client.consumptions_profile(
                    [{**MOCK_POD, "best_available_granularity": ProfileType.ACTIVE_CURRENT}],
                ),
                "Invalid value for best_available_granularity: <ProfileType.ACTIVE_CURRENT: 'ACTIVE_CURRENT'>",
            ),
        ],
        ids=[
            "consents_string_status",
            "consent_requests_string_status",
            "dashboard_headers_string_branch",
            "consumptions_profiles_none_branch",
            "dashboard_headers_string_active_only",
            "consumptions_profiles_int_active_only",
            "consumptions_profile_string_dimension",
            "consents_other_enum_status",
            "dashboard_headers_int_branch",
            "consumptions_profile_other_enum_dimension",
            "consumptions_profile_none_profile_type",
            "consumptions_profile_other_enum_granularity",
        ],
    )
    async def test_invalid_enum_value(
        self,
        request_method: Callable[[NetzOOEeServiceAPI], Awaitable[Any]],
        message: str,
    ) -> None:
        """Test a filter, dimension or `Pod` value that is no member of its enum raises an API error."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_client(mock_api)

            with pytest.raises(APIError) as error:
                await request_method(client)

            assert type(error.value) is APIError
            assert str(error.value) == message
            assert error.value.status is None
            assert mock_api.requests == {}

    async def test_contract_account_empty(self) -> None:
        """Test empty path parameters of the contract account are sent and the 404 of the portal is raised."""
        with aioresponses() as mock_api:
            client: NetzOOEeServiceAPI = await create_logged_in_client(mock_api)

            mock_api.get(f"{MOCK_API_URL}/contract-accounts//", status=404, body="")

            with pytest.raises(APIError) as error:
                await client.contract_accounts(business_partner_number="", contract_account_number="")

            assert error.value.status == HTTPStatus.NOT_FOUND

            await client.logout()

    @pytest.mark.parametrize("auto_login", [False, True], ids=["manual_login", "auto_login"])
    @pytest.mark.parametrize("passed_session", [False, True], ids=["own_session", "passed_session"])
    async def test_logout_during_login(self, *, auto_login: bool, passed_session: bool) -> None:
        """Test a logout during the login cancels it, so it raises an API error and sets no token afterwards."""

        async def scenario(mock_api: aioresponses) -> None:
            started: asyncio.Event = asyncio.Event()
            release: asyncio.Event = asyncio.Event()

            async def security_check(_url: URL, **_kwargs: object) -> CallbackResult:
                started.set()
                await release.wait()
                return CallbackResult(status=200)

            mock_api.post(MOCK_LOGIN_URL, callback=security_check)
            mock_api.get(MOCK_SESSION_URL, headers={"Set-Cookie": f"XSRF-TOKEN={MOCK_XSRF}; Path=/; Secure"})
            mock_api.get(MOCK_LOGOUT_URL, status=200)

            async with ClientSession() as session:
                client: NetzOOEeServiceAPI = await create_client(
                    mock_api,
                    mocks=False,
                    session=session if passed_session else None,
                )

                login: asyncio.Task[Any] = asyncio.create_task(client.dashboard() if auto_login else client.login())
                await started.wait()
                await client.logout()
                release.set()

                with pytest.raises(APIError) as error:
                    await login

                assert type(error.value) is APIError
                assert str(error.value) == "Logged out during the login"
                assert client.xsrf_token == ""
                assert recorded_calls(mock_api, "/session") == []
                assert not session.closed

                # The next request logs in again.
                mock_login(mock_api)
                mock_api.get(MOCK_DASHBOARD_URL, status=200, payload={})
                mock_api.get(MOCK_LOGOUT_URL, status=200)

                result: dict[str, Any] = await client.dashboard()
                assert result == {}

                await client.logout()

        assert await count_unclosed_sessions(scenario) == 0

    @pytest.mark.parametrize("url", [MOCK_LOGIN_URL, MOCK_SESSION_URL], ids=["login", "session"])
    async def test_passed_session_closed_during_login(self, url: str) -> None:
        """Test a passed session that is closed during the login raises an API error instead of a RuntimeError."""
        with aioresponses() as mock_api:
            session: ClientSession = ClientSession()

            async def close_session(_url: URL, **_kwargs: object) -> CallbackResult:
                await session.close()
                return CallbackResult(status=200, headers={"Set-Cookie": f"XSRF-TOKEN={MOCK_XSRF}; Path=/; Secure"})

            mock_api.post(MOCK_LOGIN_URL, callback=close_session if url == MOCK_LOGIN_URL else None, status=200)
            mock_api.get(MOCK_SESSION_URL, callback=close_session if url == MOCK_SESSION_URL else None, status=200)

            client: NetzOOEeServiceAPI = await create_client(mock_api, mocks=False, session=session)

            with pytest.raises(APIError) as error:
                await client.dashboard()

            assert type(error.value) is APIError
            assert str(error.value) == "Session is closed"
            assert recorded_calls(mock_api, "dashboard") == []

    @pytest.mark.parametrize("url", [MOCK_LOGIN_URL, MOCK_DASHBOARD_URL], ids=["login", "dashboard"])
    async def test_other_runtime_error(self, url: str) -> None:
        """Test a RuntimeError that is not caused by a closed session is not hidden as an API error."""

        async def scenario(mock_api: aioresponses) -> None:
            client: NetzOOEeServiceAPI = await create_client(mock_api, mocks=url != MOCK_LOGIN_URL)

            mock_api.add(url, "POST" if url == MOCK_LOGIN_URL else "GET", exception=RuntimeError("mocked error"))

            with pytest.raises(RuntimeError, match="mocked error"):
                await client.dashboard()

            await client.logout()

        assert await count_unclosed_sessions(scenario) == 0
