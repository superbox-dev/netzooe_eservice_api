# Netz OÖ eService API

A Python wrapper for the unofficial Netz Oberösterreich eService-Portal API.

![coverage-badge](https://raw.githubusercontent.com/superbox-dev/netzooe_eservice_api/main/coverage-badge.svg)
[![Version](https://img.shields.io/pypi/pyversions/netzooe-eservice-api.svg)][pypi-version]
[![CI](https://github.com/superbox-dev/netzooe_eservice_api/actions/workflows/ci.yml/badge.svg?branch=main)][workflow-ci]

[pypi-version]: https://pypi.python.org/pypi//netzooe-eservice-api
[workflow-ci]: https://github.com/superbox-dev/netzooe_eservice_api/actions/workflows/ci.yml

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

asyncio.run(main())
```

## Changelog

The changelog lives in the [CHANGELOG.md](https://github.com/superbox-dev/netzooe_eservice_api/blob/main/CHANGELOG.md) document.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Get Involved

The **Netz OÖ eService-Portal API** is an open-source project and contributions are welcome. You can:

* Report [issues](https://github.com/superbox-dev/netzooe_eservice_api/issues/new/choose) or request new features
* Improve documentation
* Contribute code
* Support the project by starring it on GitHub ⭐

I'm happy about your contributions to the project!
You can get started by reading the [CONTRIBUTING.md](https://github.com/superbox-dev/netzooe_eservice_api/blob/main/CONTRIBUTING.md).
