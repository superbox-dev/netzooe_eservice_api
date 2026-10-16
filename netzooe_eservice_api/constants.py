# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0
"""Constants used by the Netz OÖ eService API."""

from enum import Enum

ESERVICE_PORTAL: str = "https://eservice.netzooe.at"
ESERVICE_PORTAL_API: str = f"{ESERVICE_PORTAL}/service/v1.0"

COMMON_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "client-id": "netzonline",
}


class ConsentsStatus(Enum):
    """Status of a data sharing consent, used by `NetzOOEeServiceAPI.consents()`."""

    ACTIVE = "ACTIVE"
    ACTIVE_UNCHANGEABLE = "ACTIVE_UNCHANGEABLE"
    REVOKED = "REVOKED"


class ConsumptionsProfilesBranch(Enum):
    """Branch of a consumption profile, used by `NetzOOEeServiceAPI.consumptions_profiles()`."""

    ELECTRICITY = "STROM"


class SynthProfile(Enum):
    """Type of a synthetic load profile."""

    HOUSEHOLD = "Haushalt"
    PHOTOVOLTAICS = "Photovoltaik"


class ConsumptionsDimension(Enum):
    """Measurement dimension, used by `NetzOOEeServiceAPI.consumptions_profile()`."""

    ENERGY = "ENERGY"
    POWER = "POWER"
