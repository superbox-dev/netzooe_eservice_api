# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0
"""Constants used by the Netz OÖ eService API."""

from enum import Enum
from typing import Final

ESERVICE_PORTAL: Final[str] = "https://eservice.netzooe.at"
ESERVICE_PORTAL_API: Final[str] = f"{ESERVICE_PORTAL}/service/v1.0"

COMMON_HEADERS: Final[dict[str, str]] = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "client-id": "netzonline",
}


class ConsentsStatus(Enum):
    """Status of a data sharing consent, used by `NetzOOEeServiceAPI.consents()`."""

    REQUESTED = "REQUESTED"
    QR_CODE_SENT = "QR_CODE_SENT"
    ACTIVE = "ACTIVE"
    ACTIVE_UNCHANGEABLE = "ACTIVE_UNCHANGEABLE"
    TIMEOUT = "TIMEOUT"
    REVOKED = "REVOKED"
    CONCLUDED = "CONCLUDED"


class ConsentRequestsStatus(Enum):
    """Status of a data sharing consent request, used by `NetzOOEeServiceAPI.consent_requests()`."""

    INITIAL = "INITIAL"
    SENT = "SENT"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"


class ConsumptionsProfilesBranch(Enum):
    """Branch, used by `NetzOOEeServiceAPI.consumptions_profiles()` and `NetzOOEeServiceAPI.dashboard_headers()`."""

    ELECTRICITY = "STROM"
    GAS = "GAS"


class SynthProfile(Enum):
    """Type of a synthetic load profile."""

    HOUSEHOLD = "Haushalt"
    PHOTOVOLTAICS = "Photovoltaik"


class ConsumptionsDimension(Enum):
    """Measurement dimension, used by `NetzOOEeServiceAPI.consumptions_profile()`."""

    ENERGY = "ENERGY"
    POWER = "POWER"
    VOLUME = "VOLUME"


class Granularity(Enum):
    """Granularity of the measured values, used by `Pod`."""

    QUARTER_OF_AN_HOUR = "QUARTER_OF_AN_HOUR"
    HOUR = "HOUR"
    DAY = "DAY"
    MONTH = "MONTH"
    YEAR = "YEAR"


class ProfileType(Enum):
    """Type of a consumption profile, used by `Pod`."""

    ACTIVE_CURRENT = "ACTIVE_CURRENT"
    REACTIVE_CURRENT = "REACTIVE_CURRENT"
    JOINT_GENERATING_PLANT_PRODUCTION = "JOINT_GENERATING_PLANT_PRODUCTION"
    JOINT_GENERATING_PLANT_CONSUMATION = "JOINT_GENERATING_PLANT_CONSUMATION"
    JOINT_GENERATING_PLANT_PARTICIPATION = "JOINT_GENERATING_PLANT_PARTICIPATION"
    JOINT_GENERATING_PLANT_GENERATION = "JOINT_GENERATING_PLANT_GENERATION"
    JOINT_GENERATING_PLANT_GENERATION_RENEWABLE = "JOINT_GENERATING_PLANT_GENERATION_RENEWABLE"
    COMPARISON = "COMPARISON"
    GAS_IN_KWH = "GAS_IN_KWH"
    GAS_IN_CUBIC_METERS = "GAS_IN_CUBIC_METERS"
    ENERGY_COMMUNITY_OWN_COVERAGE = "ENERGY_COMMUNITY_OWN_COVERAGE"
    ENERGY_COMMUNITY_OWN_COVERAGE_TOTAL = "ENERGY_COMMUNITY_OWN_COVERAGE_TOTAL"
    ENERGY_COMMUNITY_REMAINING_GRID_USAGE = "ENERGY_COMMUNITY_REMAINING_GRID_USAGE"
    ENERGY_COMMUNITY_CONSUMPTION_PER_CONTRIBUTION_FACTOR = "ENERGY_COMMUNITY_CONSUMPTION_PER_CONTRIBUTION_FACTOR"
    ENERGY_COMMUNITY_REMAINING_GRID_USAGE_PER_CONTRIBUTION_FACTOR = (
        "ENERGY_COMMUNITY_REMAINING_GRID_USAGE_PER_CONTRIBUTION_FACTOR"
    )
    ENERGY_COMMUNITY_OVER_COVERAGE = "ENERGY_COMMUNITY_OVER_COVERAGE"
    ENERGY_COMMUNITY_GENERATION_PER_CONTRIBUTION_FACTOR = "ENERGY_COMMUNITY_GENERATION_PER_CONTRIBUTION_FACTOR"
    ENERGY_COMMUNITY_OVER_COVERAGE_PER_CONTRIBUTION_FACTOR = "ENERGY_COMMUNITY_OVER_COVERAGE_PER_CONTRIBUTION_FACTOR"
    ENERGY_COMMUNITY_ALLOCATED_PLANT_PRODUCTION = "ENERGY_COMMUNITY_ALLOCATED_PLANT_PRODUCTION"
