---
phase: 03-mcp-domain-servers-and-gateway
plan: 03
subsystem: mcp-domain-servers
tags: [nwdaf, camara, mcp-tools, explicit-tools, fastmcp]
dependency_graph:
  requires: [03-01]
  provides: [mcp-nwdaf-server, mcp-camara-server]
  affects: [03-05, 03-06]
tech_stack:
  added: []
  patterns: [explicit-mcp-tool-decorators, dual-configmap-watcher, dual-httpx2-client]
key_files:
  created:
    - mcp/nwdaf/server.py
    - mcp/nwdaf/pyproject.toml
    - mcp/nwdaf/Dockerfile
    - mcp/nwdaf/allowlist_analytics.yaml
    - mcp/nwdaf/allowlist_events.yaml
    - mcp/nwdaf/specs/nwdaf_analyticsinfo_bundled.yaml
    - mcp/nwdaf/specs/nwdaf_eventssubscription_rel16.yaml
    - mcp/nwdaf/uv.lock
    - mcp/camara/server.py
    - mcp/camara/pyproject.toml
    - mcp/camara/Dockerfile
    - mcp/camara/allowlist_verify.yaml
    - mcp/camara/allowlist_retrieve.yaml
    - mcp/camara/specs/camara_location_verification.yaml
    - mcp/camara/specs/camara_location_retrieval.yaml
    - mcp/camara/uv.lock
  modified: []
decisions:
  - "D-10a applied: hand-written @mcp.tool() decorators for multi-spec domains instead of from_openapi() composition"
  - "NWDAF uses single httpx2 client (both specs share NWDAF_BASE_URL); CAMARA uses dual clients (separate verify/retrieve backends)"
  - "NextGCore EventsSubscription path divergence documented as Phase 4 forward concern, not addressed now"
metrics:
  duration: "4m 42s"
  completed: "2026-10-05T13:08:01Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 16
  files_modified: 0
---

# Phase 03 Plan 03: NWDAF & CAMARA Multi-Spec Domain Servers Summary

Explicit @mcp.tool() servers for NWDAF (3 tools from 2 TS 29.520 specs) and CAMARA (2 tools from 2 location specs) with ConfigMap file-watchers and OpenShift-ready Dockerfiles.

## What Was Built

### NWDAF MCP Server (mcp/nwdaf/)
- **server.py**: 3 explicit @mcp.tool() functions covering 2 OpenAPI specs:
  - `get_nwdaf_analytics(event_id)` -- GET /analytics (AnalyticsInfo spec)
  - `subscribe_nwdaf_events(event_id, notification_uri)` -- POST /subscriptions (EventsSubscription spec)
  - `unsubscribe_nwdaf_events(subscription_id)` -- DELETE /subscriptions/{id} (EventsSubscription spec)
- Single httpx2.AsyncClient with ConfigMap file-watcher reading NWDAF_BASE_URL
- Tool functions append API-relative paths in code (ConfigMap provides host:port only)
- /healthz liveness probe, create_app() factory, uvicorn runner
- NextGCore EventsSubscription path divergence documented as Phase 4 forward concern

### CAMARA MCP Server (mcp/camara/)
- **server.py**: 2 explicit @mcp.tool() functions covering 2 OpenAPI specs:
  - `verify_location(device_phone_number, latitude, longitude, accuracy)` -- POST /verify (Location Verification spec)
  - `retrieve_location(device_phone_number)` -- POST /retrieve (Location Retrieval spec)
- Dual httpx2.AsyncClient instances: verify_client (CAMARA_BASE_URL) and retrieve_client (CAMARA_RETRIEVAL_BASE_URL)
- Dual ConfigMap file-watchers (one per backend URL)
- /healthz liveness probe, create_app() factory, uvicorn runner

### Supporting Files (both servers)
- pyproject.toml with fastmcp>=4.0.11, httpx2>=2.13.1, pyyaml>=6.0.3, uvicorn>=0.30.0
- Dockerfile using python:3.12-slim with OpenShift arbitrary-UID support (GID 0, USER 1001)
- uv.lock generated for reproducible builds
- Allowlist YAML configs (documentation only -- not consumed by CLI for explicit-tool servers)
- Spec files copied from backends/specs/ for reference

## Task Details

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | NWDAF analytics server (3 tools from 2 specs) | 973c5d7 | mcp/nwdaf/server.py, mcp/nwdaf/Dockerfile, mcp/nwdaf/pyproject.toml |
| 2 | CAMARA device location server (2 tools from 2 specs) | b78db5c | mcp/camara/server.py, mcp/camara/Dockerfile, mcp/camara/pyproject.toml |
| - | uv.lock files for both servers | 7b90763 | mcp/nwdaf/uv.lock, mcp/camara/uv.lock |

## Deviations from Plan

None -- plan executed exactly as written.

## Decisions Made

1. **D-10a hand-written tools**: Both servers use explicit @mcp.tool() decorators rather than from_openapi() composition. This gives full control over tool names, descriptions, and parameter schemas for the small tool counts (3 and 2). Avoids MCPServerRegistration double-prefixing that mount() composition would introduce.

2. **Single vs dual client**: NWDAF uses a single httpx2.AsyncClient because both specs (AnalyticsInfo, EventsSubscription) share the same NWDAF_BASE_URL backend. CAMARA uses two separate clients because verify and retrieve hit different Prism instances (CAMARA_BASE_URL vs CAMARA_RETRIEVAL_BASE_URL).

3. **NextGCore path divergence**: Documented as a forward concern for Phase 4. The EventsSubscription spec uses server base path /nnwdaf-eventssubscription/v1 vs AnalyticsInfo's /nnwdaf-analyticsinfo/v1. For Prism (D-11 target), both serve at root so single base URL works. For NextGCore, Phase 4 would need a second ConfigMap key or per-tool path logic.

## Verification Results

- NWDAF: 6/6 automated checks passed (3 tool functions, /healthz, NWDAF_BASE_URL, @mcp.tool)
- CAMARA: 6/6 automated checks passed (2 tool functions, /healthz, both base URLs, @mcp.tool)
- Additional acceptance criteria verified: no from_openapi() in executable code, correct API paths appended in tool functions, dual clients for CAMARA, spec/allowlist files present, Dockerfiles have python:3.12-slim

## Self-Check: PASSED

- All 16 created files verified present on disk
- All 3 commits verified in git log (973c5d7, b78db5c, 7b90763)
