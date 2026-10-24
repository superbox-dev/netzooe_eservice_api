# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0

"""Test data for `test_api.py`."""

from typing import Final

from netzooe_eservice_api.api import Pod
from netzooe_eservice_api.constants import Granularity
from netzooe_eservice_api.constants import ProfileType

MOCK_USERNAME: Final[str] = "test"
MOCK_CREDENTIAL: Final[str] = "test"
MOCK_XSRF: Final[str] = "mocked-token-value"
MOCK_NEW_XSRF: Final[str] = "mocked-new-token-value"
MOCK_OUTSIDE_XSRF: Final[str] = "mocked-outside-token-value"
MOCK_UNKNOWN_STATUS: Final[int] = 520

MOCK_LOGIN_URL: Final[str] = "https://eservice.netzooe.at/service/j_security_check"
MOCK_SESSION_URL: Final[str] = "https://eservice.netzooe.at/service/v1.0/session"
MOCK_LOGOUT_URL: Final[str] = "https://eservice.netzooe.at/service/logout"
MOCK_DASHBOARD_URL: Final[str] = "https://eservice.netzooe.at/service/v1.0/dashboard"
MOCK_PROFILE_URL: Final[str] = "https://eservice.netzooe.at/service/v1.0/consumptions/profile/active"
MOCK_API_URL: Final[str] = "https://eservice.netzooe.at/service/v1.0"

MOCK_POD: Final[Pod] = Pod(
    contract_account_number="123",
    profile_type=ProfileType.ACTIVE_CURRENT,
    best_available_granularity=Granularity.QUARTER_OF_AN_HOUR,
    meter_point_administration_number="AT123",
    date_from="2026-01-01",
    date_to="2026-01-30",
)
