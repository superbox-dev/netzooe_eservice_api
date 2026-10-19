# Tests

- Reuse the client factories (`create_client`, `create_logged_in_client`) and the mock constants
- Cover error responses and invalid input
- Recorded requests as syrupy snapshots (`assert mock_api.requests == snapshot`)
  - always review the `__snapshots__/*.ambr` diff
- Never call, patch or inspect `_`-prefixed methods or attributes, assert return values, exceptions or the recorded
  requests
