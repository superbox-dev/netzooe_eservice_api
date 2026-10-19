---
sidebar_position: 5
---

# Usage

## Read data

```python
import asyncio
from typing import Any

from netzooe_eservice_api import NetzOOEeServiceAPI

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

## Session

All methods of `NetzOOEeServiceAPI` are asynchronous. The client logs in automatically on the first request and
logs in again once if the session has expired. The data methods return the raw JSON response of the portal.

A passed `aiohttp` `ClientSession` is never closed by the client. Without a passed session, the client creates its
own and closes it on `logout()` and if a login fails.

| Method     | Portal endpoint                                                    | Description                                                                                                                                                             |
|------------|--------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `login()`  | `POST /service/j_security_check`, then `GET /service/v1.0/session` | Logs in and gets a new XSRF token. Optional, the client logs in automatically.                                                                                          |
| `logout()` | `GET /service/logout`                                              | Logs out and resets the XSRF token. A running login is cancelled and raises an `APIError`. A session created by the client is closed, a passed session is never closed. |

## Endpoints

See the [API client](/api) for all parameters and return values.

| Method                                                               | Portal endpoint                                                                       | Returns                                                                             |
|----------------------------------------------------------------------|---------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| `dashboard()`                                                        | `GET /service/v1.0/dashboard`                                                         | Dashboard data, e.g. business partners and contract accounts                        |
| `dashboard_headers(branch=None, *, active_only=None)`                | `GET /service/v1.0/dashboard/headers`                                                 | Short overview of the contract accounts with their contracts and points of delivery |
| `contract_accounts(business_partner_number, contract_account_number)` | `GET /service/v1.0/contract-accounts/{businessPartnerNumber}/{contractAccountNumber}` | Data of a contract account                                                          |
| `consents(status=None)`                                              | `GET /service/v1.0/consents`                                                          | Data sharing consents                                                               |
| `consent_requests(status=None)`                                      | `GET /service/v1.0/consent-requests`                                                  | Data sharing consent requests, e.g. of energy communities                           |
| `consumptions_profiles(branch=None, *, active_only=None)`            | `GET /service/v1.0/consumptions/profiles`                                             | Consumption profiles of all points of delivery                                      |
| `consumptions_profile(pods, dimension=ConsumptionsDimension.ENERGY)` | `POST /service/v1.0/consumptions/profile/active`                                      | Measured values of one or more points of delivery in a time range                   |

### Parameters

| Parameter                                            | Type                                                                                  | Description                                                                                                                           |
|------------------------------------------------------|---------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `branch`                                             | A `ConsumptionsProfilesBranch` member, an iterable of members (e.g. a list) or `None` | Only returns entries of these branches (`ELECTRICITY`, `GAS`). `None`, an empty list or both branches return all.                     |
| `active_only`                                        | `bool` or `None`                                                                      | `True` only returns active contract accounts or points of delivery. `None` returns all.                                               |
| `status` of `consents()`                             | A `ConsentsStatus` member, an iterable of members (e.g. a list) or `None`             | `REQUESTED`, `QR_CODE_SENT`, `ACTIVE`, `ACTIVE_UNCHANGEABLE`, `TIMEOUT`, `REVOKED`, `CONCLUDED`. `None` or an empty list returns all. |
| `status` of `consent_requests()`                     | A `ConsentRequestsStatus` member, an iterable of members (e.g. a list) or `None`      | `INITIAL`, `SENT`, `CONFIRMED`, `REJECTED`, `TIMEOUT`. `None` or an empty list returns all.                                           |
| `business_partner_number`, `contract_account_number` | `str`                                                                                 | Numbers from `dashboard()`.                                                                                                           |
| `pods`                                               | `list[Pod]`                                                                           | Points of delivery and the time range to request, see [Consumption profile](#consumption-profile).                                    |
| `dimension`                                          | `ConsumptionsDimension`                                                               | `ENERGY` (default), `POWER` or `VOLUME`.                                                                                              |

All enums and their values are listed under [Constants](/constants).

## Consumption profile

`consumptions_profile()` takes a list of [`Pod`](/types#pod) dictionaries. The values for `profile_type` and
`best_available_granularity` can be taken from `consumptions_profiles()`.

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

## Errors

All errors are subclasses of `APIError`, see [Errors](/errors):

| Exception             | Raised when                                                                                                                                                                                                      |
|-----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `AuthenticationError` | The credentials were rejected (HTTP 401), also after a new login                                                                                                                                                 |
| `InvalidJsonError`    | The response is not valid JSON, e.g. the maintenance page ("Wartungsseite")                                                                                                                                      |
| `APIError`            | Any other HTTP or connection error, a `logout()` during the login, or a filter or `dimension` that is no member of its enum (e.g. a plain string). `status` holds the HTTP status, `detail` the original message |
