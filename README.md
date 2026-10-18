# Netz OÖ eService API

<!--start-home-->
A Python wrapper for the unofficial Netz Oberösterreich eService portal API.

> **Note:** This is an unofficial community project. It is not affiliated with, endorsed by or supported by
> Netz Oberösterreich GmbH. For support, open an [issue](https://github.com/superbox-dev/netzooe_eservice_api/issues),
> do not contact Netz Oberösterreich.

![coverage-badge](https://raw.githubusercontent.com/superbox-dev/netzooe_eservice_api/main/coverage-badge.svg)

[![CI](https://github.com/superbox-dev/netzooe_eservice_api/actions/workflows/ci.yml/badge.svg?branch=main)][workflow-ci]
![Typing: strict][typing-strict]
![Code style: Ruff][code-ruff]

[workflow-ci]: https://github.com/superbox-dev/netzooe_eservice_api/actions/workflows/ci.yml
[typing-strict]: https://img.shields.io/badge/typing-strict-green.svg
[code-ruff]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v1.json

<!--end-home-->

## Donation

<!--start-donation-->

I put a lot of time into this project. If you like it, you can support me with a donation.

[![KoFi](https://raw.githubusercontent.com/superbox-dev/.github/refs/heads/main/profile/superbox-kofi.jpg)][kofi]

[kofi]: https://ko-fi.com/F2F0KXO6D

or [donate with PayPal](https://www.paypal.com/donate?hosted_button_id=34ZFWTH4TNLXS)

<!--end-donation-->

<!--start-home-->

## Getting started

```bash
pip install netzooe_eservice_api
```

```python
import asyncio

from netzooe_eservice_api import NetzOOEeServiceAPI

from aiohttp import ClientSession


async def main():
    async with ClientSession() as session:
        client = NetzOOEeServiceAPI(username="test", password="test", session=session)
        print(await client.dashboard())


asyncio.run(main())
```

See [Usage](https://superbox-dev.github.io/netzooe_eservice_api/usage) for all endpoints, consumption profiles and
errors.

<!--end-home-->

## Documentation

Read the full API documentation on
[superbox-dev.github.io/netzooe_eservice_api](https://superbox-dev.github.io/netzooe_eservice_api/).

## Changelog

The changelog lives in the [CHANGELOG.md](CHANGELOG.md) document.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

<!--start-contributing-->

## Get Involved

The **Netz OÖ eService API** is an open-source project and contributions are welcome. You can:

- Report [issues](https://github.com/superbox-dev/netzooe_eservice_api/issues/new/choose) or request new features
- Improve documentation
- Contribute code
- Support the project by starring it on GitHub ⭐

<!--end-contributing-->

I'm happy about your contributions to the project!
You can get started by reading the [CONTRIBUTING.md](CONTRIBUTING.md).
