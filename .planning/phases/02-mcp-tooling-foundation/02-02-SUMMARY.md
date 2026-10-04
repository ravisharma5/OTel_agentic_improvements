---
phase: 02-mcp-tooling-foundation
plan: 02
subsystem: infra
tags: [docker, openshift, mcp, streamable-http, python, fastmcp]

requires:
  - phase: 02-01
    provides: Vendored MCP-Telecom with HTTP transport and config scaffolds

provides:
  - Dockerfile for MCP-Telecom with OpenShift arbitrary-UID support
  - OpenShift manifests (namespace, deployment, service, secret) for otel25-mcp
  - MCP protocol verification script with smart tool selection heuristic
  - (BLOCKED) Live OpenShift deployment and MCP protocol round-trip verification

affects: [02-03, 03-gateway, 04-sdg-pipeline]

tech-stack:
  added: [uv-in-docker, python-3.12-slim]
  patterns: [openshift-arbitrary-uid, tcpSocket-liveness, healthz-readiness, sse-aware-verification]

key-files:
  created:
    - mcp/mcp-telecom/Dockerfile
    - mcp/openshift/namespace.yaml
    - mcp/openshift/mcp-telecom-deployment.yaml
    - mcp/openshift/mcp-telecom-secret.yaml
    - scripts/verify-mcp-telecom.sh
  modified: []

key-decisions:
  - "Used uv (not pip) in Dockerfile for reproducible frozen lockfile installs"
  - "liveness tcpSocket + readiness httpGet /healthz probe combination per D-20"
  - "Smart schema-preference heuristic for tool selection in verification script"

patterns-established:
  - "OpenShift arbitrary-UID: chgrp -R 0 /app && chmod -R g=u /app, writable cache dirs, USER 1001"
  - "MCP verification: SSE-aware response parsing, error-type discrimination (not-found vs connection vs schema)"
  - "Python Dockerfile layer caching: copy pyproject.toml+uv.lock first, then src/"

requirements-completed: []

duration: 4min
completed: 2026-10-03
---

# Phase 2 Plan 02: MCP-Telecom Containerization and OpenShift Deployment Summary

**Dockerfile with OpenShift arbitrary-UID support and full deployment manifests created; OpenShift deployment blocked by cluster connectivity timeout**

## Performance

- **Duration:** 4 min (Task 1 only; Task 2 blocked)
- **Started:** 2026-10-03T17:32:30Z
- **Completed:** 2026-10-03T17:36:16Z (partial -- Task 2 blocked)
- **Tasks:** 1 of 3 completed (Task 2 blocked by OpenShift connectivity, Task 3 depends on Task 2)
- **Files modified:** 5

## Accomplishments
- Created production Dockerfile for MCP-Telecom with OpenShift arbitrary-UID support (chgrp/chmod g=u, writable cache dirs, PYTHONDONTWRITEBYTECODE, USER 1001)
- Created otel25-mcp namespace, Deployment+ClusterIP Service, and placeholder Secret manifests following Phase 1 established patterns
- Built comprehensive MCP protocol verification script with SSE-aware parsing, smart schema-preference tool selection heuristic, and three-tier error discrimination

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Dockerfile, OpenShift manifests, and verification script** - `3659dc4` (feat)
2. **Task 2: Build image, deploy to OpenShift, verify MCP protocol, update STATE.md** - BLOCKED (OpenShift cluster unreachable: `dial tcp 3.143.198.38:6443: i/o timeout`)
3. **Task 3: Human verification of OpenShift deployment** - BLOCKED (depends on Task 2)

## Files Created/Modified
- `mcp/mcp-telecom/Dockerfile` - Production container image with uv, OpenShift arbitrary-UID support, layer-cached dependency install
- `mcp/openshift/namespace.yaml` - otel25-mcp namespace with layer: mcp label (D-17)
- `mcp/openshift/mcp-telecom-deployment.yaml` - Deployment (readiness /healthz, liveness tcpSocket, 256Mi/512Mi resources) + ClusterIP Service (D-18, D-20, T-02-01)
- `mcp/openshift/mcp-telecom-secret.yaml` - Placeholder device credentials Secret (D-10, T-02-03)
- `scripts/verify-mcp-telecom.sh` - MCP protocol round-trip verification: tools/list + smart tool invocation with error discrimination (D-08)

## Decisions Made
- Used uv (not pip) in Dockerfile for frozen lockfile reproducibility, matching the vendored mcp-telecom's existing uv.lock
- Combined tcpSocket liveness (process-up) with httpGet /healthz readiness (MCP endpoint responds) per D-20 and prism-camara.yaml pattern
- Verification script handles FastMCP's SSE (text/event-stream) responses by extracting JSON from `data:` lines
- Smart schema-preference heuristic: prefers tools with no required fields or only string-typed required fields, avoiding nested objects/enums

## Deviations from Plan

None - Task 1 executed exactly as written. Tasks 2-3 not attempted due to cluster connectivity blocker.

## Issues Encountered
- **OpenShift cluster unreachable:** `oc whoami` returned `dial tcp 3.143.198.38:6443: i/o timeout`. The oc CLI is installed but the cluster API server is not reachable from this environment. This blocks Tasks 2 and 3 (build, push, deploy, verify).
- **STATE.md no-device-backend entry already present:** The idempotent check in Task 2's plan confirms the D-09 blocker entry was already added during the discuss-phase flow (line 78 of STATE.md). No append needed.

## User Setup Required

None - no external service configuration required for the artifacts created in Task 1. OpenShift deployment (Task 2) requires cluster connectivity.

## Next Phase Readiness
- All deployment artifacts are ready for `oc apply` once OpenShift cluster is reachable
- Verification script is ready to run via port-forward once pod is deployed
- STATE.md already has the D-09 no-device-backend entry (no action needed)
- **Blocker:** OpenShift cluster must be reachable to complete Tasks 2 and 3

---
*Phase: 02-mcp-tooling-foundation*
*Partial completion: 2026-10-03 (Task 1 of 3)*
