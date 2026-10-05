---
phase: 03-mcp-domain-servers-and-gateway
plan: 02
subsystem: mcp-domain-servers
tags: [mcp, tmf642, tmf628, tmf621, openapi, fastmcp, domain-tools]
dependency_graph:
  requires: [03-01]
  provides: [tmf642-server, tmf628-server, tmf621-server, 15-domain-tools]
  affects: [mcp/tmf642/, mcp/tmf628/, mcp/tmf621/, mcp/tooling/openapi_to_mcp.py]
tech_stack:
  added: []
  patterns: [swagger2-to-oas3-conversion, anchored-routemap-patterns]
key_files:
  created:
    - mcp/tmf642/server.py
    - mcp/tmf642/allowlist.yaml
    - mcp/tmf642/Dockerfile
    - mcp/tmf642/pyproject.toml
    - mcp/tmf642/specs/tmf642_alarm_v5.0.1.oas.yaml
    - mcp/tmf628/server.py
    - mcp/tmf628/allowlist.yaml
    - mcp/tmf628/Dockerfile
    - mcp/tmf628/pyproject.toml
    - mcp/tmf628/specs/tmf628_performance_v4.0.0.swagger.json
    - mcp/tmf621/server.py
    - mcp/tmf621/allowlist.yaml
    - mcp/tmf621/Dockerfile
    - mcp/tmf621/pyproject.toml
    - mcp/tmf621/specs/tmf621_troubleticket_v5.0.1.oas.yaml
  modified:
    - mcp/tooling/openapi_to_mcp.py
decisions:
  - Anchored RouteMap regex patterns with ^ and $ to prevent false positives from substring matching on listener/event paths
  - Added runtime Swagger 2.0 to OAS 3.0 conversion for TMF628 since FastMCP requires OAS 3.0
  - TMF642 PATCH /alarm/{id} split into 3 semantic tools (acknowledge, clear, comment) using @mcp.tool() decorators
metrics:
  duration: 7m 23s
  completed: "2026-10-05T13:10:50Z"
---

# Phase 3 Plan 02: TMF Domain MCP Servers Summary

Three single-spec TMF domain MCP servers (TMF642, TMF628, TMF621) totaling 15 tools, generated via Phase 2's conversion CLI and hand-curated for production with /healthz, uvicorn runner, and ConfigMap watcher.

## What Was Done

### Task 1: TMF642 Alarm Management Server (6 tools)

| Step | Description | Result |
|------|-------------|--------|
| Pre-step | Removed resolved TODO from CLI scaffold template | 4-line comment block about FastMCP base_url propagation removed from openapi_to_mcp.py |
| 1 | Created mcp/tmf642/specs/ and copied TMF642 OAS 3.0 spec | Done |
| 2 | Created allowlist.yaml with 3 operations (GET /alarm, GET /alarm/{id}, POST /hub) | Done |
| 3 | Ran CLI to generate scaffold | Generated server.py with 3 from_openapi tools |
| 4 | Hand-curated server.py | Fixed SPEC_PATH to relative, added /healthz, added runner, added 3 explicit PATCH tools |
| 5 | Created pyproject.toml | fastmcp>=4.0.11, httpx2>=2.13.1, pyyaml>=6.0.3, uvicorn>=0.34.3 |
| 6 | Created Dockerfile | python:3.12-slim, OpenShift arbitrary-UID support |
| 7 | Smoke test | 6 tools confirmed: acknowledge_alarm, clear_alarm, add_comment, listAlarm, retrieveAlarm, createHub |

**Commit:** `8f93139`

### Task 2: TMF628 and TMF621 Servers (5+4 tools)

**TMF628 Performance Management (5 tools):**
| Step | Result |
|------|--------|
| Copy spec | tmf628_performance_v4.0.0.swagger.json copied |
| Allowlist | 5 operations: GET /measurementCollectionJob, GET /measurementCollectionJob/{id}, POST /onDemandCollection, GET /trackingRecord, GET /trackingRecord/{id} |
| Generate + curate | Added Swagger 2.0 -> OAS 3.0 converter, fixed SPEC_PATH, added /healthz and runner |
| Verify | 5 tools: listMeasurementCollectionJob, retrieveMeasurementCollectionJob, createOnDemandCollection, listTrackingRecord, retrieveTrackingRecord |

**TMF621 Trouble Ticket (4 tools):**
| Step | Result |
|------|--------|
| Copy spec | tmf621_troubleticket_v5.0.1.oas.yaml copied |
| Allowlist | 4 operations: POST /troubleTicket, PATCH /troubleTicket/{id}, GET /troubleTicket/{id}, GET /troubleTicket |
| Generate + curate | Fixed SPEC_PATH, anchored patterns, added /healthz and runner |
| Verify | 4 tools: listTroubleTicket, createTroubleTicket, retrieveTroubleTicket, patchTroubleTicket |

**Commit:** `0c2e699`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] FastMCP rejects Swagger 2.0 specs (TMF628)**
- **Found during:** Task 2
- **Issue:** Research claim A2 stated FastMCP from_openapi() handles Swagger 2.0. In practice, FastMCP's OpenAPI parser uses strict OAS 3.0 Pydantic models that reject Swagger 2.0's `in: body` parameter type (42 validation errors).
- **Fix:** Added `_convert_swagger2_to_oas3()` function in TMF628's server.py that converts Swagger 2.0 format to OAS 3.0 at load time, handling: version field, host/basePath to servers, definitions to components/schemas, in:body params to requestBody, and $ref path fixups.
- **Files modified:** mcp/tmf628/server.py
- **Commit:** 0c2e699

**2. [Rule 1 - Bug] RouteMap patterns match too broadly**
- **Found during:** Task 2 (TMF628 returned 11 tools instead of 5)
- **Issue:** Unanchored RouteMap regex patterns like `/onDemandCollection` matched listener event paths like `/listener/onDemandCollectionCreateEvent` as substrings.
- **Fix:** Anchored all RouteMap patterns with `^` and `$` across all three servers (TMF642, TMF628, TMF621) to ensure exact path matching.
- **Files modified:** mcp/tmf642/server.py, mcp/tmf628/server.py, mcp/tmf621/server.py
- **Commit:** 0c2e699 (TMF628/621), 0c2e699 includes TMF642 fix

## Verification Results

| Server | Expected Tools | Actual Tools | Status |
|--------|---------------|--------------|--------|
| TMF642 | 6 | 6 | PASS |
| TMF628 | 5 | 5 | PASS |
| TMF621 | 4 | 4 | PASS |

All servers verified with:
- `from_openapi()` call present
- `/healthz` endpoint present
- ConfigMap watcher reading correct `*_BASE_URL` key
- `create_app()` + `main()` uvicorn runner present
- SPEC_PATH uses relative path
- Dockerfile with python:3.12-slim and OpenShift arbitrary-UID support

## Known Stubs

None -- all servers are fully wired to their respective backend URLs via ConfigMap watcher.

## Threat Flags

None -- all files match the plan's threat model. The Swagger 2.0 conversion function does not introduce new trust boundaries (conversion happens at server startup from a local spec file).

## Self-Check: PASSED

- All 16 files exist on disk
- Commit 8f93139 exists in history
- Commit 0c2e699 exists in history
- No unexpected file deletions
