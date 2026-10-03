---
phase: 02-mcp-tooling-foundation
plan: 03
subsystem: tooling
tags: [fastmcp, openapi, codegen, configmap, httpx2, pydantic, yaml, routemap]

# Dependency graph
requires:
  - phase: 01-backend-infrastructure
    provides: "ConfigMap backend-routing contract (BACK-03), CAMARA spec at backends/specs/"
  - phase: 02-01
    provides: "Package legitimacy verification for fastmcp, httpx, pyyaml, pydantic"
provides:
  - "OpenAPI-to-MCP conversion CLI (mcp/tooling/openapi_to_mcp.py)"
  - "Allowlist schema with Pydantic validation (mcp/tooling/allowlist_schema.py)"
  - "ConfigMap mtime-polling watcher pattern with httpx client base_url mutation"
  - "CAMARA smoke test and synthetic 2-operation filtering proof"
affects: [03-domain-mcp-servers, 04-sdg-pipeline]

# Tech tracking
tech-stack:
  added: [fastmcp 4.0.10, httpx2 2.13.1, pydantic 2.13.5, pyyaml 6.0.3]
  patterns: [string.Template codegen, RouteMap pattern filtering with catch-all EXCLUDE, mtime-polling ConfigMap watcher, stateless Streamable HTTP]

key-files:
  created:
    - mcp/tooling/pyproject.toml
    - mcp/tooling/openapi_to_mcp.py
    - mcp/tooling/allowlist_schema.py
    - mcp/tooling/tests/__init__.py
    - mcp/tooling/tests/test_configmap_watcher.py
    - mcp/tooling/tests/test_allowlist_filtering.py
    - mcp/tooling/tests/camara_allowlist.yaml
    - mcp/tooling/tests/synthetic_two_op_spec.yaml
    - mcp/tooling/tests/synthetic_allowlist.yaml
    - mcp/tooling/uv.lock
  modified: []

key-decisions:
  - "Used string.Template ($var) instead of str.format or Jinja2 -- zero conflict with Python braces in generated code"
  - "Used RouteMap pattern= (regex) instead of path= -- matches actual FastMCP 4.0.10 API"
  - "Used httpx2.AsyncClient instead of httpx.AsyncClient -- FastMCP 4.0.10 expects httpx2"
  - "Used yaml.safe_load to parse spec into dict -- from_openapi() expects dict, not string"
  - "Added stateless_http=True for generated scaffolds -- simplifies testing and removes session management requirement"

patterns-established:
  - "Pattern: Generated scaffolds use stateless Streamable HTTP (stateless_http=True) at POST /mcp"
  - "Pattern: RouteMap uses pattern= (regex) for path matching, not a path= keyword"
  - "Pattern: from_openapi() expects dict (yaml.safe_load), not raw text string"
  - "Pattern: from_openapi() expects httpx2.AsyncClient, not httpx.AsyncClient (FastMCP 4.0.10)"
  - "Pattern: ConfigMap watcher uses mtime polling (not inotify) for K8s symlink swap compatibility"

requirements-completed: [MCP-07]

# Metrics
duration: 9min
completed: 2026-10-03
---

# Phase 2 Plan 3: OpenAPI-to-MCP Conversion CLI Summary

**Reusable codegen CLI generating FastMCP scaffolds from OpenAPI specs with RouteMap filtering, ConfigMap watcher, and httpx2 client base_url mutation -- proven via synthetic 2-operation fixture and CAMARA smoke test**

## Performance

- **Duration:** 9 min
- **Started:** 2026-10-03T17:32:25Z
- **Completed:** 2026-10-03T17:41:32Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Built reusable OpenAPI-to-MCP conversion CLI at mcp/tooling/openapi_to_mcp.py using string.Template codegen
- Generated scaffolds include ConfigMap mtime-polling watcher that mutates httpx2 client base_url on valid URL changes
- Proved allowlist filtering works end-to-end: synthetic 2-operation spec (POST /alpha, GET /beta) with 1-operation allowlist produces exactly 1 tool -- verified both via static source-text assertions AND dynamic runtime tools/list against the running generated server
- CAMARA smoke test passes: generated scaffold starts locally, tools/list returns verifyLocation tool with full schema

## Task Commits

Each task was committed atomically:

1. **Task 1: Create conversion CLI project, allowlist schema, and ConfigMap watcher test** - `43ae05f` (feat)
2. **Task 2: Build conversion CLI, smoke-test against CAMARA spec, and prove filtering with synthetic fixture** - `dc4b475` (feat)

## Files Created/Modified
- `mcp/tooling/pyproject.toml` - Project config with fastmcp, httpx, pyyaml, pydantic dependencies
- `mcp/tooling/allowlist_schema.py` - Pydantic AllowlistConfig and OperationFilter models with load_allowlist()
- `mcp/tooling/openapi_to_mcp.py` - Conversion CLI using string.Template codegen with ConfigMap watcher baked in
- `mcp/tooling/tests/__init__.py` - Test package marker
- `mcp/tooling/tests/test_configmap_watcher.py` - 4 tests: file change detection, missing file, invalid URL rejection, httpx client base_url mutation
- `mcp/tooling/tests/test_allowlist_filtering.py` - Static + dynamic runtime proof of allowlist exclusion
- `mcp/tooling/tests/camara_allowlist.yaml` - CAMARA smoke test allowlist (server_name: camara-location, /verify POST)
- `mcp/tooling/tests/synthetic_two_op_spec.yaml` - Minimal 2-operation OpenAPI spec for filtering proof
- `mcp/tooling/tests/synthetic_allowlist.yaml` - Allowlist selecting only POST /alpha
- `mcp/tooling/uv.lock` - Dependency lockfile for reproducibility

## Decisions Made
- **string.Template over str.format/Jinja2:** The generated Python code contains dict literals, f-strings, and set syntax that would require doubling every literal `{` and `}` with str.format. string.Template uses `$var` syntax which has zero conflict with Python braces. Avoids Jinja2 dependency for a single template.
- **RouteMap pattern= (regex) instead of path=:** FastMCP 4.0.10's RouteMap uses `pattern` (a regex string) for path matching, not a `path` keyword. The plan's RESEARCH.md Example 1 showed `path=` which was incorrect for the actual API.
- **httpx2.AsyncClient instead of httpx.AsyncClient:** FastMCP 4.0.10 has deprecated httpx in favor of httpx2. The generated scaffolds use httpx2 directly.
- **yaml.safe_load for spec parsing:** FastMCP's from_openapi() expects `dict[str, Any]`, not a raw string. Specs must be parsed via yaml.safe_load before passing.
- **stateless_http=True:** Generated scaffolds run in stateless Streamable HTTP mode, removing session management complexity and enabling simpler testing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed RouteMap API: pattern= instead of path=**
- **Found during:** Task 2 (conversion CLI implementation)
- **Issue:** RESEARCH.md Example 1 showed `RouteMap(path="/verify", ...)` but FastMCP 4.0.10's actual API uses `RouteMap(pattern=r"/verify", ...)` with regex matching
- **Fix:** Changed _build_route_maps_code() to generate `pattern=` with re.escape() for safe regex, updated test assertions
- **Files modified:** mcp/tooling/openapi_to_mcp.py, mcp/tooling/tests/test_allowlist_filtering.py
- **Verification:** Generated scaffold starts and tools/list returns correct filtered tools
- **Committed in:** dc4b475 (Task 2 commit)

**2. [Rule 1 - Bug] Fixed from_openapi() spec format: dict instead of string**
- **Found during:** Task 2 (CAMARA smoke test)
- **Issue:** Template passed `spec_text = SPEC_PATH.read_text()` (string) to from_openapi(), but the API expects `dict[str, Any]`
- **Fix:** Changed to `spec_dict = yaml.safe_load(SPEC_PATH.read_text())` and imported yaml in generated scaffold
- **Files modified:** mcp/tooling/openapi_to_mcp.py
- **Verification:** CAMARA scaffold starts successfully with parsed dict spec
- **Committed in:** dc4b475 (Task 2 commit)

**3. [Rule 1 - Bug] Fixed httpx -> httpx2 client for FastMCP 4.0.10 compatibility**
- **Found during:** Task 2 (CAMARA smoke test)
- **Issue:** FastMCP 4.0.10 expects httpx2.AsyncClient, not httpx.AsyncClient (deprecation warning)
- **Fix:** Changed generated scaffold to import and use httpx2 instead of httpx
- **Files modified:** mcp/tooling/openapi_to_mcp.py
- **Verification:** No deprecation warnings, scaffold starts cleanly
- **Committed in:** dc4b475 (Task 2 commit)

**4. [Rule 1 - Bug] Fixed session requirement: stateless HTTP mode**
- **Found during:** Task 2 (CAMARA smoke test)
- **Issue:** Server returned "Missing session ID" error on tools/list -- stateful Streamable HTTP requires initialize first with session tracking
- **Fix:** Added stateless_http=True to mcp.run() in generated scaffolds
- **Files modified:** mcp/tooling/openapi_to_mcp.py
- **Verification:** tools/list works directly without prior initialize
- **Committed in:** dc4b475 (Task 2 commit)

**5. [Rule 1 - Bug] Fixed SSE response parsing in dynamic test**
- **Found during:** Task 2 (filtering test implementation)
- **Issue:** FastMCP returns SSE-formatted responses (`event: message\ndata: {...}`) not plain JSON. Test's `resp.json()` would fail.
- **Fix:** Added _parse_sse_json() helper to extract JSON from SSE data lines
- **Files modified:** mcp/tooling/tests/test_allowlist_filtering.py
- **Verification:** test_allowlist_excludes_non_allowlisted_operation passes with SSE parsing
- **Committed in:** dc4b475 (Task 2 commit)

---

**Total deviations:** 5 auto-fixed (5 Rule 1 bugs -- API mismatches between RESEARCH.md examples and actual FastMCP 4.0.10 behavior)
**Impact on plan:** All auto-fixes necessary for correctness. The RESEARCH.md patterns were correct in concept but used outdated/incorrect API details. No scope creep.

## Issues Encountered
- httpx.AsyncClient base_url trailing-slash behavior differs between constructor and property setter -- fixed test assertion to use normalized string comparison

## Known Stubs
- `customize_components()` in generated scaffolds has a `pass` body -- intentional; Phase 3 curation hook for improving tool descriptions. Documented in generated scaffold's curation guide.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Conversion CLI ready for Phase 3 to generate 5 domain MCP servers (TMF642, TMF628, TMF621, NWDAF, CAMARA)
- Phase 3 must validate that FastMCP from_openapi() re-reads httpx2 client.base_url per-request (TODO comment baked into generated scaffolds, STATE.md flag-forward exists)
- Generated scaffolds use stateless Streamable HTTP -- Phase 3 may switch to stateful if session management is needed

---
*Phase: 02-mcp-tooling-foundation*
*Completed: 2026-10-03*
