# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- An empty list as `branch` or `status` filter is no filter like `None`, `dashboard_headers([])` and
  `consumptions_profiles([])` no longer raise an `APIError` with HTTP 404
- A filter or `dimension` that is no enum member, e.g. a plain string like `"STROM"`, raises an `APIError` before
  any request instead of an `AttributeError`
- A `logout()` while a login is still running raises an `APIError` instead of a `RuntimeError` of aiohttp

<!--start-->

## [1.2.0] - 2026-10-18

### Added

- Added the `detail` attribute to `APIError` with the original message, e.g. the response body or the content of the
  maintenance page
- Exported `NetzOOEeServiceAPI`, `Pod`, the enums and the exceptions from the `netzooe_eservice_api` package
- Added `dashboard_headers()` to get a short overview of the contract accounts with their contracts and points of
  delivery, optionally filtered by `branch` and `active_only`
- Added `consent_requests()` and the `ConsentRequestsStatus` enum to get the data sharing consent requests
- Added the optional `active_only` argument to `consumptions_profiles()`
- Added the `REQUESTED`, `QR_CODE_SENT`, `TIMEOUT` and `CONCLUDED` members to `ConsentsStatus`
- Added the `GAS` member to `ConsumptionsProfilesBranch`
- Added the `VOLUME` member to `ConsumptionsDimension`
- Added the `Granularity` and `ProfileType` enums, `Pod` accepts them for `best_available_granularity` and
  `profile_type` in addition to strings
- Added the `Apache-2.0` license expression and the `Typing :: Typed` / `Framework :: AsyncIO` classifiers
  to the package metadata

### Changed

- Made the `branch` argument of `consumptions_profiles()` optional with a default of `None`
- Changed concurrent requests without a valid session and concurrent `login()` calls to share a single login and
  its result, so rejected credentials are sent only once instead of once per request
- Stopped closing the own session on connection errors and timeouts, so concurrent requests are no longer aborted and
  the next request reuses the login. The own session is closed on `logout()` and if a login fails
- Stopped `logout()` from sending a request if the client has no open session
- Changed `login()` to raise `APIError` if the session response contains no `XSRF-TOKEN` cookie, instead of
  succeeding with an empty XSRF token
- Changed `logout()` to raise `APIError` if the logout request fails with an HTTP error, the XSRF token is still
  reset and the own session is still closed
- Added the documentation with Docusaurus on GitHub Pages (<https://superbox-dev.github.io/netzooe_eservice_api/>),
  the API reference is generated from the docstrings
- Shortened the `README.md` to a quick start and moved the endpoints, consumption profile and errors to the
  [Usage](https://superbox-dev.github.io/netzooe_eservice_api/usage) page

### Fixed

- Fixed the first `POST` request after the automatic login (e.g. `consumptions_profile()` without a prior `login()`)
  being sent without the XSRF token and failing with `400 Bad Request`
- Caught timeouts and unknown HTTP status codes (e.g. `520`) and raised them as `APIError`
- Caught `aiohttp` exceptions in `login()` and `logout()` when they are called directly and raised them as `APIError`
- Fixed `logout()` not releasing the response of the logout request
- Fixed a session leak when a closed `session` was passed to `NetzOOEeServiceAPI()`
- URL encoded the path parameters of `contract_accounts()`
- Fixed `args` and `repr()` of `APIError` not containing the message
- Fixed `login()` failing with `404 Not Found` if the session is still logged in, it now logs out and logs in again
- Fixed requests being sent with the XSRF token of a passed `session` that was closed after the login, instead of
  logging in again on the new session
- Caught response bodies that are not valid in their charset (`UnicodeDecodeError`) and raised them as
  `InvalidJsonError` or `APIError`
- Raised `InvalidJsonError` for a successful response with an empty body or JSON of an unexpected type (e.g. an array
  instead of an object), instead of returning `None` or the unexpected value
- Kept the response body of a failed session request in `APIError.detail`
- Fixed the re-login after a `401` response holding a connection of the session until the retry finished

## [1.1.1] - 2026-08-12

### Added

- Added the `ConsumptionsDimension` enum with the members `ENERGY` and `POWER`
- Added the optional `dimension` argument to `consumptions_profile()`, the default `ConsumptionsDimension.ENERGY`
  keeps the previously hard-coded value

### Changed

- Made `energy_community_id` in `Pod` optional (`NotRequired[str | None]`), `consumptions_profile()` only sends
  `energyCommunityId` if it is set instead of raising a `KeyError` if it is missing
- Added docstrings to the package, the modules, `Pod`, the enums and `APIError`
- Raised the build requirements to `setuptools>=84.0.0` and `setuptools-scm>=10.2.1`
- Replaced `black` and `mypy` with `ruff format` and `ty`, `pre-commit` with `prek` and `pip-audit` with
  `uv audit` in the development tooling
- Moved the `ruff`, `rumdl`, `pytest` and `coverage` configuration from `pyproject.toml` into own files
- Switched the tests from `aioresponses` to `aioresponses-ng` and added `syrupy` snapshots of the recorded requests

### Security

- Updated `idna` to `3.15` in `uv.lock`

## [1.1.0] - 2026-06-09

### Added

- Made the `session` argument of `NetzOOEeServiceAPI()` optional, without a `session` the client creates its own
  `aiohttp.ClientSession` on the first request and creates a new one if it was closed

### Changed

- Stopped closing a passed `session` on errors and on `logout()`, only the own session of the client is closed
- Changed `logout()` to reset the XSRF token, so the next request logs in again

### Fixed

- Caught JSON decode errors when the API returns a maintenance page ("Wartungsseite") with status `200` and raised
  them as `InvalidJsonError` instead of `aiohttp.ContentTypeError` / `json.JSONDecodeError`

### Security

- Updated `urllib3` to `2.7.0` and `pip` to `26.1` in `uv.lock`

## [1.0.2] - 2026-04-05

### Added

- Added a usage example to `README.md`

### Fixed

- Caught `aiohttp` exceptions during the automatic login of a request and raised them as `APIError`

## [1.0.1] - 2026-04-03

### Security

- Updated `aiohttp` to `3.13.5`, `requests` to `2.33.1` and `pygments` to `2.20.0` in `uv.lock`, the package
  requirement `aiohttp==3.*` is unchanged

## [1.0.0] - 2026-02-21

### Added

- Added the asynchronous client `NetzOOEeServiceAPI` for the eService portal, based on `aiohttp`
- Added `login()` and `logout()`, the XSRF token is read from the `XSRF-TOKEN` cookie of the session and sent as
  `x-xsrf-token` header
- Added the automatic login on the first request and one re-login and retry after a `401` response
- Added the endpoints `dashboard()`, `consents()`, `consumptions_profiles()`, `contract_accounts()` and
  `consumptions_profile()`
- Added the `Pod` `TypedDict`, `consumptions_profile()` accepts multiple pods in one request
- Added the enums `ConsentsStatus`, `ConsumptionsProfilesBranch` and `SynthProfile`, `consents()` and
  `consumptions_profiles()` accept a member or a list of members
- Added the constants `ESERVICE_PORTAL`, `ESERVICE_PORTAL_API` and `COMMON_HEADERS`
- Added the exceptions `APIError` (with the HTTP `status`), `AuthenticationError` and `InvalidJsonError`
- Supported Python 3.13 and 3.14

[Unreleased]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/superbox-dev/netzooe_eservice_api/releases/tag/v1.0.0

<!--end-->
