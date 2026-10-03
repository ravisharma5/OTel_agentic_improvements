---
phase: 02-mcp-tooling-foundation
plan: 01
subsystem: infra
tags: [fastmcp, mcp-telecom, streamable-http, uvicorn, netmiko, command-allowlist]

# Dependency graph
requires:
  - phase: 01-backend-infrastructure
    provides: vendoring precedent (D-06), ConfigMap contract, OpenShift deployment patterns
provides:
  - Vendored MCP-Telecom at mcp/mcp-telecom/ with standalone fastmcp dependency
  - Streamable HTTP transport on port 8000 (stdio removed)
  - /healthz health endpoint for OpenShift readiness probes
  - Device-inventory config scaffold with OpenShift Secret references
  - Command-allowlist scaffold with deny-by-default (empty list)
  - Regenerated uv.lock for downstream frozen-sync in Dockerfile
  - NOTICE file crediting upstream MCP-Telecom (MIT license)
affects: [02-02, 03-domain-tools, 04-sdg-pipeline]

# Tech tracking
tech-stack:
  added: [fastmcp 4.0.10, httpx 0.28.1, uvicorn, starlette]
  patterns: [vendor-and-patch MCP servers, ASGI app with custom health route, deny-by-default command allowlist]

key-files:
  created:
    - mcp/mcp-telecom/src/mcp_telecom/server.py
    - mcp/mcp-telecom/pyproject.toml
    - mcp/mcp-telecom/uv.lock
    - mcp/mcp-telecom/NOTICE
    - mcp/mcp-telecom/devices.yaml.example
    - mcp/mcp-telecom/command_allowlist.yaml
    - mcp/mcp-telecom/tests/test_allowlist.py
  modified: []

key-decisions:
  - "Switched MCP-Telecom from mcp[cli] SDK to standalone fastmcp>=4.0.0 for project stack alignment"
  - "Used mcp.http_app() + uvicorn pattern instead of mcp.run(transport='http') for custom /healthz route support"
  - "Kept upstream .env.example, excluded .gitignore (per user global instructions) and .github/ (upstream CI)"

patterns-established:
  - "Vendor-and-patch: clone upstream, remove .git, modify in-place, maintain NOTICE attribution"
  - "ASGI health endpoint: create_app() returns mcp.http_app() with @app.route('/healthz') for probe compatibility"
  - "Deny-by-default allowlist: empty allowed_commands list rejects all commands until Phase 4 populates it"

requirements-completed: [MCP-06]

# Metrics
duration: 6min
completed: 2026-10-03
---

# Phase 2 Plan 01: MCP-Telecom Vendor and Patch Summary

**Vendored MCP-Telecom with fastmcp 4.0.10 serving Streamable HTTP on port 8000, /healthz probe endpoint, deny-by-default command allowlist, and OpenShift Secret-referenced device-inventory scaffold -- 172 upstream tests passing**

## Performance

- **Duration:** 6 min
- **Started:** 2026-10-03T17:21:25Z
- **Completed:** 2026-10-03T17:27:07Z
- **Tasks:** 2 (1 checkpoint resolved, 1 auto)
- **Files created:** 57

## Accomplishments
- Vendored MCP-Telecom (60+ device-layer tools) into mcp/mcp-telecom/ with full upstream source
- Swapped dependency from mcp[cli]>=1.0.0 to standalone fastmcp>=4.0.0, changing import to `from fastmcp import FastMCP`
- Replaced stdio transport with Streamable HTTP on port 8000 via uvicorn ASGI, with /healthz health endpoint
- Created deny-by-default command_allowlist.yaml (empty allowed_commands list) with 15 unit tests
- Created devices.yaml.example with credential_secret_ref pointing to OpenShift Secret
- Regenerated uv.lock so downstream Plan 02's Dockerfile can use `uv sync --frozen`
- All 172 upstream tests pass after the package swap (2 skipped: optional dashboard/metrics extras)

## Task Commits

Each task was committed atomically:

1. **Task 1: Verify PyPI package legitimacy before install** - checkpoint resolved (no code commit)
   - Resolved via orchestrator running `slopcheck scan --pkg pypi` against all 7 packages
   - All packages confirmed legitimate: fastmcp, httpx, pydantic, pyyaml, netmiko, python-dotenv, rich
   - python-dotenv flagged as "looks like LLM bait" on naming pattern but confirmed established/legitimate

2. **Task 2: Clone, vendor, and patch MCP-Telecom** - `c87b5b4` (feat)
   - Vendored full MCP-Telecom source, patched imports and transport, created config scaffolds and tests

## Files Created/Modified
- `mcp/mcp-telecom/src/mcp_telecom/server.py` - Patched: fastmcp import, HTTP transport, /healthz endpoint
- `mcp/mcp-telecom/pyproject.toml` - Swapped mcp[cli] for fastmcp>=4.0.0, added httpx>=0.28.0
- `mcp/mcp-telecom/uv.lock` - Regenerated lockfile for fastmcp dependency graph
- `mcp/mcp-telecom/NOTICE` - Attribution to upstream MCP-Telecom (MIT, Avinash Amudala)
- `mcp/mcp-telecom/LICENSE` - Original MIT license from upstream (unchanged)
- `mcp/mcp-telecom/devices.yaml.example` - OpenShift Secret-referenced device inventory scaffold
- `mcp/mcp-telecom/command_allowlist.yaml` - Deny-by-default command allowlist (empty list)
- `mcp/mcp-telecom/tests/test_allowlist.py` - 15 unit tests for allowlist enforcement
- 49 additional upstream source files vendored unchanged

## Decisions Made
- Used `mcp.http_app()` + `uvicorn.run()` instead of `mcp.run(transport="http")` to allow adding the custom /healthz route via Starlette's `@app.route()` decorator on the ASGI app
- Excluded upstream `.gitignore` per user's global CLAUDE.md instructions ("Never push .gitignore files")
- Excluded upstream `.github/` directory (CI workflows not relevant to vendored copy)
- Included upstream `.env.example` as documentation reference

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `pytest-timeout` plugin not installed in upstream dev dependencies; ran tests without `--timeout=30` flag (all tests complete in 0.14s so timeout was unnecessary)

## User Setup Required
None - no external service configuration required.

## Threat Mitigations Applied
- **T-02-SC (supply chain):** All 7 PyPI packages verified via slopcheck before install (Task 1 checkpoint)
- **T-02-02 (command injection):** command_allowlist.yaml with empty allowed_commands list denies all commands by default; test_allowlist.py verifies deny behavior
- **T-02-03 (credential disclosure):** devices.yaml.example uses credential_secret_ref field pointing to OpenShift Secret name, never plaintext credentials

## Next Phase Readiness
- MCP-Telecom is vendored, patched, and all upstream tests pass -- ready for Plan 02 (Dockerfile + OpenShift deployment)
- uv.lock is regenerated and committed -- Plan 02's `uv sync --frozen` will work
- /healthz endpoint exists -- Plan 02's readiness probe can use `httpGet.path: /healthz`
- No device backend wired (D-07) -- flagged in STATE.md as existing concern for Phase 4

---
*Phase: 02-mcp-tooling-foundation*
*Completed: 2026-10-03*
