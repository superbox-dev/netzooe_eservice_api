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
uv run pytest -n0 --snapshot-update  # regenerate snapshots (without xdist), then review the diff
./scripts/docs.sh                    # docs (Docusaurus, needs Node.js)
./scripts/docs.sh start              # docs with live reload
```

Before finishing a change, run:

- `uv run ruff format`
- `./scripts/lint.sh`
- `uv run pytest`
- `./scripts/docs.sh`

## Rules

- **No breaking changes** to anything usable externally, i.e. everything without a `_` prefix:
  - classes, methods, signatures, return values
  - types, constants, exceptions
  - enum members
  - behaviour that worked before
- Allowed:
  - renames, if the old name stays as an alias (note it in the changelog)
  - new parameters, if they are optional and the default keeps the old behaviour
  - turning a crash (uncaught built-in or `aiohttp` exception) into an `APIError` (or a subclass)
  - changing `_`-prefixed internals
- **Python 3.13 minimum**, so no syntax or features of newer versions
- Every `.py` file starts with (after the shebang of an executable script):

  ```python
  # Copyright 2026 Michael Hacker
  # SPDX-License-Identifier: Apache-2.0
  ```

- NumPy-style docstrings everywhere, also in tests
- No lint or type suppressions (inline or in config), except the existing ignores in `ruff.toml`. Fix the code instead
- New public names are exported in the package `__init__.py` (`__all__`)
- Avoid `cast()`: narrow types with checks that also run at runtime (e.g. `isinstance`) or with generics
- No real credentials or customer data, use placeholders like `"test"`
- `git add` new files, CI only checks tracked files
- Never edit generated or CI-managed files (`version.py`, `coverage-badge.svg`)

## Architecture

- `constants.py`:
  - URLs, headers and enums
  - enum values are the exact strings the portal expects
- `api.py`: `NetzOOEeServiceAPI` and its request types (`TypedDict`s)
  - login: `POST /service/j_security_check`, then `GET /service/v1.0/session` sets the `XSRF-TOKEN` cookie
  - the `XSRF-TOKEN` cookie is sent as `x-xsrf-token` header
  - one central request method logs in lazily, retries once after re-login on `401` and maps all errors to
    the package's exceptions
  - a passed `session` is never closed, an own session is closed on logout and on errors
- `error.py`: exceptions
- Helpers are `_`-prefixed methods of the class that uses them (`@staticmethod` if they need no `self`),
  not module-level functions
- Public methods:
  - `snake_case` parameters, mapped to the portal's `camelCase` inside the method
  - optional fields are only sent when set
  - enum parameters accept a member, a list of members or `None`
  - return the raw JSON
  - pass the expected JSON type (`dict` or `list`) to the request helpers, which check it

## Adding an endpoint

1. `constants.py`: add new enums or constants
2. `api.py`: add the public method, built on the existing request helpers
3. `tests/test_api.py`: add tests for happy and unhappy paths (see [Tests](#tests))
4. `website/content/usage.md`: update it if relevant, the API reference is generated from the docstrings

## Documentation

- Docusaurus website in `website/`, deployed to GitHub Pages from `main` (`.github/workflows/page.yml`)
- `scripts/generate-docs.py` writes all pages into `website/docs/` (not tracked, run by `scripts/docs.sh`):
  - API reference from the docstrings (griffe): client, types (`TypedDict`s in `api.py`), constants and enums,
    errors
  - home, donation, contributing and changelog from the `<!--start-…-->` / `<!--end-…-->` markers
    in `README.md`, `CONTRIBUTING.md` and `CHANGELOG.md`, so keep the markers
  - hand-written pages from `website/content/` (e.g. `usage.md`, with `sidebar_position` but no `title`
    in the front matter, the title comes from the `#` heading)
- Keep `README.md` short (install, a minimal example), details go to `website/content/`
- Design after home-assistant.io: `website/src/css/custom.css`, the project card in
  `website/src/components/ProjectInfo/` and the wrapped `website/src/theme/TOC/`

## Tests

- **100% test coverage** (lines and branches) is enforced
- Tests live in `tests/test_api.py`:
  - mock HTTP with `aioresponses`
  - reuse the client factories (`create_client`, `create_logged_in_client`) and the mock constants
  - cover error responses and invalid input
- The recorded requests are [syrupy](https://github.com/syrupy-project/syrupy) snapshots:
  - `assert mock_api.requests == snapshot`
  - create or update them with `uv run pytest -n0 --snapshot-update`
  - review the `__snapshots__/*.ambr` diff and `git add` them
- Never call, patch or inspect `_`-prefixed methods or attributes:
  - call the public API (`NetzOOEeServiceAPI` methods)
  - drive the client through mocked HTTP responses
  - assert return values, raised exceptions or the recorded requests

## Changelog and git

- `CHANGELOG.md`:
  - every user-visible change gets an entry under `## [Unreleased]`
  - Keep a Changelog format, past tense
  - identifiers in backticks
  - issues as `([Issue #25][issue-25])`, pull requests as `([PR #19][pr-19])`
  - issue and PR links are defined at the end of their release section, not at the bottom
  - releases are linked at the bottom, before `<!--end-->`:
    - `[Unreleased]` compares the latest release tag (no pre-release) with `HEAD`
    - each release compares its tag with the previous one
    - the first release links to its release tag
- Branches:
  - work on `develop`
  - `main` is the release branch
  - `v*` tags publish to PyPI
- Only commit or push when asked
