# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0
"""Netz OÖ eService API client."""

from netzooe_eservice_api.api import NetzOOEeServiceAPI
from netzooe_eservice_api.api import Pod
from netzooe_eservice_api.constants import ConsentRequestsStatus
from netzooe_eservice_api.constants import ConsentsStatus
from netzooe_eservice_api.constants import ConsumptionsDimension
from netzooe_eservice_api.constants import ConsumptionsProfilesBranch
from netzooe_eservice_api.constants import Granularity
from netzooe_eservice_api.constants import ProfileType
from netzooe_eservice_api.constants import SynthProfile
from netzooe_eservice_api.error import APIError
from netzooe_eservice_api.error import AuthenticationError
from netzooe_eservice_api.error import InvalidJsonError
from netzooe_eservice_api.version import __version__

__all__ = [
    "APIError",
    "AuthenticationError",
    "ConsentRequestsStatus",
    "ConsentsStatus",
    "ConsumptionsDimension",
    "ConsumptionsProfilesBranch",
    "Granularity",
    "InvalidJsonError",
    "NetzOOEeServiceAPI",
    "Pod",
    "ProfileType",
    "SynthProfile",
    "__version__",
]
