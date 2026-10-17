# AGENTS.md

Async Python client (`aiohttp`) for the unofficial Netz Oberösterreich eService portal API (`eservice.netzooe.at`).
Published on PyPI and used by the Home Assistant integration.

## Commands

- Use `uv`, always via `uv run`
- Setup: `./scripts/setup.sh`

```bash
uv run ruff format                   # format (lint.sh only checks)
./scripts/lint.sh                    # all linters and type checks
uv run pytest                        # tests + coverage
uv run pytest --snapshot-update      # regenerate snapshots, then review the diff
```

Before finishing a change, run all of them except the snapshot update.

## Rules

- **No breaking changes** to anything usable externally, i.e. everything without a `_` prefix:
  - classes, methods, signatures, return values
  - types, constants, enum members, exceptions
  - behaviour that worked before
- Allowed:
  - renames, if the old name stays as an alias (note it in the changelog)
  - new parameters, if they are optional and the default keeps the old behaviour
  - turning a crash (uncaught built-in or `aiohttp` exception) into one of the package's exceptions
  - changing `_`-prefixed internals
- New public names are exported in the package `__init__.py` (`__all__`)
- **Python 3.13 minimum**: no syntax or features of newer versions (e.g. PEP 649, 750, 758)
- Every `.py` file starts with:

  ```python
  # Copyright 2026 Michael Hacker
  # SPDX-License-Identifier: Apache-2.0
  ```

- NumPy-style docstrings everywhere, also in tests
- No lint or type suppressions (inline or in config). Fix the code instead
- Avoid `cast()`: narrow types with checks that also run at runtime (e.g. `isinstance`) or with generics
- No real credentials or customer data, use placeholders like `"test"`
- `git add` new files, CI only checks tracked files
- Never edit generated or CI-managed files (`version.py`, `coverage-badge.svg`)

## Architecture

- `api.py`: the client class and its request types
  - login: `POST /service/j_security_check`, then `GET /service/v1.0/session` sets the `XSRF-TOKEN` cookie,
    which is sent as `x-xsrf-token` header
  - one central request method logs in lazily, retries once after re-login on `401` and maps all errors to the
    package's exceptions
  - a passed `session` is never closed, an own session is closed on logout and on errors
  - helpers are `_`-prefixed methods of the class that uses them (`@staticmethod` if they need no `self`),
    not module-level functions
- `constants.py`: URLs, headers, enums (values are the exact strings the portal expects)
- `error.py`: exceptions
- Public methods:
  - `snake_case` parameters, mapped to the portal's `camelCase` inside the method
  - optional fields are only sent when set
  - enum parameters accept a member, a list of members or `None`
  - return the raw JSON
  - pass the expected JSON type (`dict` or `list`) to the request helpers, which check it

## Adding an endpoint

1. Add new enums or constants
2. Add the public method, built on the existing request helpers
3. Cover happy and unhappy paths (see [Tests](#tests))
4. Update the README usage example if relevant

## Tests

- **100% test coverage** (lines and branches) is enforced
- Mock HTTP with `aioresponses`, reuse the existing client factories and mock constants of the test module
- Assert the recorded requests with snapshots
- Test only through the public API:
  - never call, patch or inspect `_`-prefixed methods or attributes
  - drive the client through its public methods and mocked HTTP responses
  - assert return values, raised exceptions or the recorded requests

## Changelog and git

- `CHANGELOG.md`:
  - every user-visible change gets an entry under `## [Unreleased]`
  - Keep a Changelog format, past tense
  - identifiers in backticks
  - issues as `([Issue #25][issue-25])`, pull requests as `([PR #19][pr-19])`
  - issue and PR links are defined at the end of their release section, not at the bottom
  - releases are linked at the bottom:
    - `[Unreleased]` compares the latest release tag (no pre-release) with `HEAD`
    - each release compares its tag with the previous one
    - the first release links to its release tag
- Branches:
  - work on `develop`
  - `main` is the release branch
  - `v*` tags publish to PyPI
- Only commit or push when asked
