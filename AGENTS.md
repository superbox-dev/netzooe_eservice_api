# AGENTS.md

Async Python client (`aiohttp`) for the unofficial Netz Oberösterreich eService portal API (`eservice.netzooe.at`).
Published on PyPI and used by the Home Assistant integration.

## Commands

- Use `uv`, always via `uv run`
- Setup: `./scripts/setup.sh`

```bash
uv run ruff format                   # format (lint.sh only checks)
./scripts/lint.sh                    # ruff, ty, yamllint, rumdl
uv run pytest                        # tests + coverage
uv run pytest --snapshot-update      # regenerate syrupy snapshots, then review the diff
```

Before finishing a change, run:

- `uv run ruff format`
- `./scripts/lint.sh`
- `uv run pytest`

## Rules

- **No breaking changes** to anything usable externally:
  - public methods of `NetzOOEeServiceAPI`, signatures, return values
  - `Pod`, constants, exceptions
  - enum members
  - behaviour that worked before
- Allowed:
  - renames, if the old name stays as an alias (note it in the changelog)
  - new parameters, if they are optional and the default keeps the old behaviour
  - turning a crash (`KeyError`, uncaught `aiohttp` exception, ...) into an `APIError`
  - changing `_`-prefixed internals
- New public classes and enums are exported in `netzooe_eservice_api/__init__.py` (`__all__`)
- **Python 3.13 minimum**, so no:
  - `except A, B` without parentheses (PEP 758)
  - template strings `t"..."` (PEP 750)
  - `annotationlib` or relying on deferred annotations (PEP 649)
- Every `.py` file starts with:

  ```python
  # Copyright 2026 Michael Hacker
  # SPDX-License-Identifier: Apache-2.0
  ```

- NumPy-style docstrings (also in tests)
- No `# noqa`, no `# type: ignore`, no new `ruff.toml` ignores. Fix the code instead
- No real credentials or customer data, use placeholders like `"test"`
- `git add` new files, CI only checks tracked files
- Never edit:
  - `netzooe_eservice_api/version.py` (generated)
  - `coverage-badge.svg` (updated by CI)

## Architecture

- `api.py`: `NetzOOEeServiceAPI` and the `Pod` `TypedDict`
  - `login()`: `POST /service/j_security_check`, then `GET /service/v1.0/session` sets the `XSRF-TOKEN` cookie
  - the token is sent as `x-xsrf-token` header
  - `_request()` logs in lazily, retries once after re-login on `401`, maps errors to `error.py`
  - a passed `session` is never closed, an own session is closed on `logout()` and on errors
- `constants.py`: URLs, headers, enums (values are the exact strings the portal expects)
- `error.py`: exceptions
- Public methods:
  - `snake_case` parameters, mapped to the portal's `camelCase` inside the method
  - optional fields are only sent when set
  - enum parameters accept a member, a list of members or `None`
  - return the raw JSON

## Adding an endpoint

1. `constants.py`: add new enums or constants
2. `api.py`: add the public method, use `_get` / `_post`
3. `tests/test_api.py`: cover happy and unhappy paths (see [Tests](#tests))
4. `README.md`: update the usage example if relevant

## Tests

- **100% test coverage** (lines and branches) is enforced
- Mock HTTP with `aioresponses` (`create_client` / `create_logged_in_client`)
- Assert the recorded requests with the `snapshot` fixture
- Use constants like `MOCK_CREDENTIAL`, no real credentials or customer data
- Never test or patch internal methods or attributes (e.g. `api._request()`, `api._session`):
  - drive the client only through its public methods and the mocked HTTP responses
  - assert return values, raised exceptions or the recorded requests

## Changelog and git

- `CHANGELOG.md`:
  - every user-visible change gets an entry under `## [Unreleased]`
  - Keep a Changelog format, past tense
  - identifiers in backticks
  - issues as `([Issue #67][issue-67])`
  - releases are linked at the bottom:
    - `[Unreleased]` compares the latest tag with `HEAD`
    - each release compares its tag with the previous one
    - the first release links to its release tag
- Branches:
  - work on `develop`
  - `main` is the release branch
  - `v*` tags publish to PyPI
- Only commit or push when asked
