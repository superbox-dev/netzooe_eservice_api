# Netz OÖ eService API

A Python wrapper for the unofficial Netz Oberösterreich eService portal API.

## Getting started

```bash
pip install netzooe_eservice_api
```

## Usage

```python
import asyncio
from typing import Any

from netzooe_eservice_api.api import NetzOOEeServiceAPI

from aiohttp import ClientSession


async def main():
    async with ClientSession() as session:
        client: NetzOOEeServiceAPI = NetzOOEeServiceAPI(
            username="test",
            password="test",
            session=session,
        )

        # Get dashboard data
        dashboard: dict[str, Any] = await client.dashboard()

        for dashboard_contract_accounts in dashboard["contractAccounts"]:
            # Get contract accounts data
            contract_accounts: dict[str, Any] = await client.contract_accounts(
                business_partner_number=dashboard_contract_accounts["businessPartnerNumber"],
                contract_account_number=dashboard_contract_accounts["contractAccountNumber"],
            )

        # Get a short overview of the active contract accounts, e.g. the meter point administration numbers
        dashboard_headers: list[dict[str, Any]] = await client.dashboard_headers(active_only=True)

        for dashboard_header in dashboard_headers:
            for contract in dashboard_header["contracts"]:
                print(contract["meterPointAdministrationNumber"])


asyncio.run(main())
```

## Endpoints

All methods of `NetzOOEeServiceAPI` are asynchronous. The client logs in automatically on the first request and
logs in again once if the session has expired. The data methods return the raw JSON response of the portal.

### Session

| Method     | Portal endpoint                                                      | Description                                                                                                                        |
|------------|----------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| `login()`  | `POST /service/j_security_check`, then `GET /service/v1.0/session`  | Logs in and gets a new XSRF token. Optional, the client logs in automatically.                                                     |
| `logout()` | `GET /service/logout`                                                | Logs out and resets the XSRF token. A session created by the client is closed, a passed session is never closed.                   |

### Data

| Method                                                                 | Portal endpoint                                                                     | Returns                                                                                           |
|------------------------------------------------------------------------|-------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| `dashboard()`                                                          | `GET /service/v1.0/dashboard`                                                       | Dashboard data, e.g. business partners and contract accounts                                      |
| `dashboard_headers(branch=None, *, active_only=None)`                  | `GET /service/v1.0/dashboard/headers`                                               | Short overview of the contract accounts with their contracts and points of delivery               |
| `contract_accounts(business_partner_number, contract_account_number)`  | `GET /service/v1.0/contract-accounts/{businessPartnerNumber}/{contractAccountNumber}` | Data of a contract account                                                                        |
| `consents(status=None)`                                                | `GET /service/v1.0/consents`                                                        | Data sharing consents                                                                             |
| `consent_requests(status=None)`                                        | `GET /service/v1.0/consent-requests`                                                | Data sharing consent requests, e.g. of energy communities                                         |
| `consumptions_profiles(branch=None, *, active_only=None)`              | `GET /service/v1.0/consumptions/profiles`                                           | Consumption profiles of all points of delivery                                                    |
| `consumptions_profile(pods, dimension=ConsumptionsDimension.ENERGY)`   | `POST /service/v1.0/consumptions/profile/active`                                    | Measured values of one or more points of delivery in a time range                                 |

#### Parameters

| Parameter                                             | Type                                                                                                   | Description                                                                                                                            |
|-------------------------------------------------------|--------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| `branch`                                              | `ConsumptionsProfilesBranch`, a list of members or `None`                                              | Only returns entries of these branches (`ELECTRICITY`, `GAS`). `None` returns all.                                                     |
| `active_only`                                         | `bool` or `None`                                                                                       | `True` only returns active contract accounts or points of delivery. `None` returns all.                                                |
| `status` of `consents()`                              | `ConsentsStatus`, a list of members or `None`                                                          | `REQUESTED`, `QR_CODE_SENT`, `ACTIVE`, `ACTIVE_UNCHANGEABLE`, `TIMEOUT`, `REVOKED`, `CONCLUDED`. `None` returns all.                  |
| `status` of `consent_requests()`                      | `ConsentRequestsStatus`, a list of members or `None`                                                   | `INITIAL`, `SENT`, `CONFIRMED`, `REJECTED`, `TIMEOUT`. `None` returns all.                                                             |
| `business_partner_number`, `contract_account_number`  | `str`                                                                                                  | Numbers from `dashboard()`.                                                                                                            |
| `pods`                                                | `list[Pod]`                                                                                            | Points of delivery and the time range to request, see [Consumption profile](#consumption-profile).                                     |
| `dimension`                                           | `ConsumptionsDimension`                                                                                | `ENERGY` (default), `POWER` or `VOLUME`.                                                                                               |

### Consumption profile

`consumptions_profile()` takes a list of `Pod` dictionaries. The values for `profile_type` and
`best_available_granularity` can be taken from `consumptions_profiles()`.

| Key                                  | Type                    | Description                                                     |
|--------------------------------------|-------------------------|-----------------------------------------------------------------|
| `contract_account_number`            | `str`                   | Contract account number of the point of delivery                |
| `energy_community_id`                | `str` (optional)        | ID of the energy community, only sent if it is set              |
| `profile_type`                       | `ProfileType` or `str`  | Profile type, e.g. `ProfileType.ACTIVE_CURRENT`                 |
| `best_available_granularity`         | `Granularity` or `str`  | Granularity, e.g. `Granularity.QUARTER_OF_AN_HOUR`              |
| `meter_point_administration_number`  | `str`                   | Meter point administration number (Zählpunktnummer)             |
| `date_from`                          | `str`                   | Start of the time range                                         |
| `date_to`                            | `str`                   | End of the time range                                           |

```python
from netzooe_eservice_api import ConsumptionsDimension
from netzooe_eservice_api import Granularity
from netzooe_eservice_api import Pod
from netzooe_eservice_api import ProfileType

profile: list[dict[str, Any]] = await client.consumptions_profile(
    pods=[
        Pod(
            contract_account_number="123456789012",
            profile_type=ProfileType.ACTIVE_CURRENT,
            best_available_granularity=Granularity.QUARTER_OF_AN_HOUR,
            meter_point_administration_number="AT0031000000000000000000000000000",
            date_from="2026-01-01",
            date_to="2026-01-31",
        ),
    ],
    dimension=ConsumptionsDimension.ENERGY,
)
```

### Errors

All errors are subclasses of `APIError`:

| Exception             | Raised when                                                                                         |
|-----------------------|-----------------------------------------------------------------------------------------------------|
| `AuthenticationError` | The credentials were rejected (HTTP 401), also after a new login                                    |
| `InvalidJsonError`    | The response is not valid JSON, e.g. the maintenance page ("Wartungsseite")                         |
| `APIError`            | Any other HTTP or connection error. `status` holds the HTTP status, `detail` the original message   |

## Changelog

The changelog lives in the [CHANGELOG.md](https://github.com/superbox-dev/netzooe_eservice_api/blob/main/CHANGELOG.md) document.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Get Involved

The **Netz OÖ eService portal API** is an open-source project and contributions are welcome. You can:

* Report [issues](https://github.com/superbox-dev/netzooe_eservice_api/issues/new/choose) or request new features
* Improve documentation
* Contribute code
* Support the project by starring it on GitHub ⭐

I'm happy about your contributions to the project!
You can get started by reading the [CONTRIBUTING.md](https://github.com/superbox-dev/netzooe_eservice_api/blob/main/CONTRIBUTING.md).

![coverage-badge](https://raw.githubusercontent.com/superbox-dev/netzooe_eservice_api/main/coverage-badge.svg)

[![CI](https://github.com/superbox-dev/netzooe_eservice_api/actions/workflows/ci.yml/badge.svg?branch=main)][workflow-ci]
![Typing: strict][typing-strict]
![Code style: Ruff][code-ruff]

[workflow-ci]: https://github.com/superbox-dev/netzooe_eservice_api/actions/workflows/ci.yml
[typing-strict]: https://img.shields.io/badge/typing-strict-green.svg
[code-ruff]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v1.json
