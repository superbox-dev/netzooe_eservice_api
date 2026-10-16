# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Added the `Apache-2.0` license expression and the `Typing :: Typed` / `Framework :: AsyncIO` classifiers
  to the package metadata

## [1.1.1] - 2026-08-12

### Added

- Added the optional `dimension` argument to `consumptions_profile()`

### Changed

- `consumptions_profile()` now supports an optional `energy_community_id` in `Pod`

## [1.1.0] - 2026-06-09

### Changed

- `NetzOOEeServiceAPI()` now creates a default session if no `session` is passed

### Fixed

- Caught JSON decode errors when the API returns a maintenance page ("Wartungsseite")

## [1.0.2] - 2026-04-05

### Fixed

- Caught `aiohttp` exceptions on login

## [1.0.1] - 2026-04-03

### Security

- Updated `aiohttp` and `requests`

## [1.0.0] - 2026-02-14

Initial release

[Unreleased]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/superbox-dev/netzooe_eservice_api/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/superbox-dev/netzooe_eservice_api/releases/tag/v1.0.0
