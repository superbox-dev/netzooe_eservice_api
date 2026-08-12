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
    """Consent status values."""

    ACTIVE = "ACTIVE"
    ACTIVE_UNCHANGEABLE = "ACTIVE_UNCHANGEABLE"
    REVOKED = "REVOKED"


class ConsumptionsProfilesBranch(Enum):
    """Consumption profile branch values."""

    ELECTRICITY = "STROM"


class SynthProfile(Enum):
    """Synthetic profile types."""

    HOUSEHOLD = "Haushalt"
    PHOTOVOLTAICS = "Photovoltaik"


class ConsumptionsDimension(Enum):
    """Consumption measurement dimensions."""

    ENERGY = "ENERGY"
    POWER = "POWER"
