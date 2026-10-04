---
phase: 02-mcp-tooling-foundation
plan: 02
subsystem: infra
tags: [docker, openshift, mcp, streamable-http, python, fastmcp, deployment]

requires:
  - phase: 02-01
    provides: Vendored MCP-Telecom with HTTP transport and config scaffolds

provides:
  - Dockerfile for MCP-Telecom with OpenShift arbitrary-UID support
  - OpenShift manifests (namespace, deployment, service, secret) for otel25-mcp
  - MCP protocol verification script with session management and smart tool selection
  - Live MCP-Telecom deployment on OpenShift verified via Streamable HTTP round-trip

affects: [02-03, 03-gateway, 04-sdg-pipeline]

tech-stack:
  added: [uv-in-docker, python-3.12-slim]
  patterns: [openshift-arbitrary-uid, tcpSocket-liveness, healthz-readiness, mcp-session-management, cross-arch-build]

key-files:
  created:
    - mcp/mcp-telecom/Dockerfile
    - mcp/openshift/namespace.yaml
    - mcp/openshift/mcp-telecom-deployment.yaml
    - mcp/openshift/mcp-telecom-secret.yaml
    - scripts/verify-mcp-telecom.sh
  modified:
    - mcp/mcp-telecom/src/mcp_telecom/server.py

key-decisions:
  - "Used uv (not pip) in Dockerfile for reproducible frozen lockfile installs"
  - "liveness tcpSocket + readiness httpGet /healthz probe combination per D-20"
  - "Smart schema-preference heuristic for tool selection in verification script"
  - "Cross-architecture build (--platform=linux/amd64) required for ARM macOS to x86 OpenShift"
  - "MCP Streamable HTTP requires session management (initialize + Mcp-Session-Id header)"
  - "StarletteWithLifespan uses router.routes.append(Route) not @app.route decorator"

patterns-established:
  - "OpenShift arbitrary-UID: chgrp -R 0 /app && chmod -R g=u /app, writable cache dirs, USER 1001"
  - "MCP verification: session-based protocol (initialize handshake), SSE response parsing, error-type discrimination"
  - "Python Dockerfile layer caching: copy pyproject.toml+uv.lock+README.md first, then src/"
  - "Cross-arch container builds: --platform=linux/amd64 when building on ARM for x86 clusters"

requirements-completed: [MCP-06]

duration: 12min
completed: 2026-10-04
---

# Phase 2 Plan 02: MCP-Telecom Containerization and OpenShift Deployment Summary

**MCP-Telecom containerized and deployed to OpenShift otel25-mcp namespace with 58 tools verified via Streamable HTTP session-based protocol round-trip**

## Performance

- **Duration:** 12 min (Task 2 continuation; Task 1 completed in prior session at 4 min)
- **Started:** 2026-10-04T17:53:05Z
- **Completed:** 2026-10-04T18:05:05Z
- **Tasks:** 2 of 3 completed (Task 3 is human-verify checkpoint)
- **Files modified:** 6

## Accomplishments
- Created production Dockerfile for MCP-Telecom with OpenShift arbitrary-UID support (chgrp/chmod g=u, writable cache dirs, PYTHONDONTWRITEBYTECODE, USER 1001)
- Created otel25-mcp namespace, Deployment+ClusterIP Service, and placeholder Secret manifests following Phase 1 established patterns
- Built comprehensive MCP protocol verification script with session management, SSE-aware parsing, smart schema-preference tool selection heuristic, and three-tier error discrimination
- Built linux/amd64 container image, pushed to OpenShift internal registry, deployed to otel25-mcp namespace
- Pod running 1/1 Ready with zero restarts, no probe failures
- Verification script confirms 58 tools via tools/list and successful list_devices invocation via tools/call
- STATE.md D-09 no-device-backend entry confirmed present (idempotent -- already added during discuss-phase)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Dockerfile, OpenShift manifests, and verification script** - `3659dc4` (feat) -- completed in prior session
2. **Task 2: Build image, deploy to OpenShift, verify MCP protocol, update STATE.md** - `ab3450b` (feat)
3. **Task 3: Human verification of OpenShift deployment** - checkpoint:human-verify (awaiting user)

## Files Created/Modified
- `mcp/mcp-telecom/Dockerfile` - Production container image with uv, OpenShift arbitrary-UID support, layer-cached dependency install, README.md fix for hatchling
- `mcp/mcp-telecom/src/mcp_telecom/server.py` - Fixed /healthz route registration (router.routes.append instead of @app.route decorator)
- `mcp/openshift/namespace.yaml` - otel25-mcp namespace with layer: mcp label (D-17)
- `mcp/openshift/mcp-telecom-deployment.yaml` - Deployment (readiness /healthz, liveness tcpSocket, 256Mi/512Mi resources) + ClusterIP Service (D-18, D-20, T-02-01)
- `mcp/openshift/mcp-telecom-secret.yaml` - Placeholder device credentials Secret (D-10, T-02-03)
- `scripts/verify-mcp-telecom.sh` - MCP protocol round-trip verification with session management: initialize handshake, tools/list (58 tools), smart tool invocation with error discrimination (D-08)

## Decisions Made
- Used uv (not pip) in Dockerfile for frozen lockfile reproducibility, matching the vendored mcp-telecom's existing uv.lock
- Combined tcpSocket liveness (process-up) with httpGet /healthz readiness (MCP endpoint responds) per D-20 and prism-camara.yaml pattern
- Verification script handles MCP Streamable HTTP session management: sends initialize request, captures Mcp-Session-Id header, uses it for all subsequent requests
- Smart schema-preference heuristic: prefers tools with no required fields (found list_devices) or only string-typed required fields, avoiding nested objects/enums
- Cross-architecture build required: macOS ARM host building for OpenShift x86_64 cluster, used podman build --platform=linux/amd64
- StarletteWithLifespan (from FastMCP 4.x http_app()) does not support @app.route decorator; used app.router.routes.append(Route) pattern instead

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Dockerfile missing README.md for hatchling build backend**
- **Found during:** Task 2 (pre-existing from prior agent's discovery)
- **Issue:** hatchling's build backend requires README.md (referenced in pyproject.toml), but Dockerfile COPY only copied pyproject.toml and uv.lock
- **Fix:** Added README.md to the COPY layer: `COPY pyproject.toml uv.lock README.md ./`
- **Files modified:** mcp/mcp-telecom/Dockerfile
- **Commit:** ab3450b

**2. [Rule 1 - Bug] Fixed architecture mismatch (arm64 image on x86_64 cluster)**
- **Found during:** Task 2 (pod CrashLoopBackOff with "Exec format error")
- **Issue:** Default podman build on macOS ARM produces arm64 images; OpenShift cluster runs x86_64
- **Fix:** Rebuilt with `podman build --platform=linux/amd64`
- **Files modified:** None (runtime build flag change)
- **Commit:** ab3450b

**3. [Rule 1 - Bug] Fixed /healthz route registration on StarletteWithLifespan**
- **Found during:** Task 2 (pod crash: AttributeError: 'StarletteWithLifespan' object has no attribute 'route')
- **Issue:** FastMCP 4.x's http_app() returns StarletteWithLifespan which does not have a .route() decorator method
- **Fix:** Changed from `@app.route("/healthz")` to `app.router.routes.append(Route("/healthz", healthz))`
- **Files modified:** mcp/mcp-telecom/src/mcp_telecom/server.py
- **Commit:** ab3450b

**4. [Rule 1 - Bug] Fixed verification script missing MCP session management**
- **Found during:** Task 2 (HTTP 400 "Missing session ID" when sending tools/list without initialize)
- **Issue:** MCP Streamable HTTP protocol requires session initialization before any method calls
- **Fix:** Added initialize handshake (captures Mcp-Session-Id header) and notifications/initialized to verification script; all subsequent requests include session ID header
- **Files modified:** scripts/verify-mcp-telecom.sh
- **Commit:** ab3450b

## Verification Results

```
=== MCP-Telecom Protocol Verification ===
Target: http://localhost:8000

--- Session Setup: MCP initialize handshake ---
  PASS: obtained session ID
  PASS: sent notifications/initialized

--- Test 1: tools/list via Streamable HTTP ---
  PASS: HTTP 200
  PASS: valid JSON-RPC response
  PASS: tools/list returned 58 tools (>= 50)

--- Test 2: tool invocation via Streamable HTTP ---
  Selected tool: list_devices
  Arguments: {}
  PASS: HTTP 200
  PASS: valid JSON-RPC response
  PASS: tool invocation returned a result

=== Results ===
Tests: 2
Passed: 2
Failed: 0
Warnings: 0

OVERALL: PASS
```

## Known Stubs

None -- all functionality is wired and operational. The placeholder Secret (mcp-telecom-device-creds) has intentionally empty values per D-10/T-02-03, to be populated in-cluster during Phase 4.

## User Setup Required

None -- deployment is live on OpenShift. Human verification (Task 3) asks user to independently confirm pod status and run the verification script.

## Next Phase Readiness
- MCP-Telecom is deployed and reachable at mcp-telecom.otel25-mcp.svc.cluster.local:8000 within the cluster
- 58 device-layer tools available via Streamable HTTP for Phase 3 gateway composition
- STATE.md has D-09 no-device-backend entry for Phase 4's SDG planner
- ClusterIP-only service (no external Route) per T-02-01; Phase 3 adds Kuadrant gateway with auth

---
*Phase: 02-mcp-tooling-foundation*
*Completed: 2026-10-04 (Tasks 1-2 of 3; Task 3 is human-verify checkpoint)*
