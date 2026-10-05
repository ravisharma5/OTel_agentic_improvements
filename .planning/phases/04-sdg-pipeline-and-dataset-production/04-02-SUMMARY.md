---
phase: 04-sdg-pipeline-and-dataset-production
plan: 02
subsystem: nwdaf-transport-configmap
tags: [h2c, configmap, nwdaf, transport, d-15, d-17]
dependency_graph:
  requires: []
  provides: [nwdaf-h2c-transport, configmap-sync, events-url-routing]
  affects: [mcp-nwdaf, backend-routing]
tech_stack:
  added: [httpcore2]
  patterns: [content-hash-configmap-watcher, conditional-transport, events-url-split]
key_files:
  created:
    - scripts/sync-backend-routing.sh
  modified:
    - mcp/nwdaf/server.py
    - backends/openshift/configmap-backend-routing.yaml
decisions:
  - "SHA-256 content hashing for ConfigMap change detection instead of st_mtime (reliable under K8s symlink rotation)"
  - "Separate events_client for EventsSubscription path divergence rather than URL rewriting per request"
  - "Protocol selection via ConfigMap key (NWDAF_PROTOCOL) rather than port-based inference"
metrics:
  duration: "4m 14s"
  completed: "2026-10-05T22:10:54Z"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 04 Plan 02: NWDAF h2c Transport Fix and ConfigMap Consolidation Summary

Conditional h2c/http1.1 transport for NWDAF MCP server using httpcore2 prior-knowledge mode, with content-hash-based ConfigMap watcher and cross-namespace sync script for single-source-of-truth ConfigMap management.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | NWDAF h2c conditional transport fix with reliable ConfigMap change detection | ef69479 | mcp/nwdaf/server.py |
| 2 | ConfigMap consolidation and sync script | 26bbf05 | backends/openshift/configmap-backend-routing.yaml, scripts/sync-backend-routing.sh |

## What Was Built

### Task 1: NWDAF h2c Conditional Transport

- Added `_create_client(base_url, protocol)` function that selects transport based on protocol parameter: "h2c" creates `httpcore2.AsyncConnectionPool(http1=False, http2=True)` for HTTP/2 cleartext prior-knowledge mode; "http1.1" (or anything else) uses default httpx2 transport
- Added `NWDAF_PROTOCOL` ConfigMap key support (`NWDAF_PROTOCOL_PATH` env-overridable path)
- Added `NWDAF_EVENTS_BASE_URL` support with separate `events_client` for EventsSubscription path divergence
- Added `get_events_backend_url()` function for events URL access under lock
- Updated `subscribe_nwdaf_events` and `unsubscribe_nwdaf_events` to use `events_client`
- Replaced st_mtime-based ConfigMap polling with SHA-256 content hashing (`_compute_file_hash()`)
- Added `os.path.realpath()` as secondary change-detection signal (catches symlink rotation even if hash computation fails)
- Watches three ConfigMap files: URL, protocol, and events URL
- Client properly closed and recreated when protocol or URL changes (old client `aclose()` scheduled)

### Task 2: ConfigMap Consolidation and Sync Script

- Added `NWDAF_EVENTS_BASE_URL` and `NWDAF_PROTOCOL` keys to configmap-backend-routing.yaml
- Updated phase label from "1" to "4"
- Documented single-source-of-truth status (D-17) in file header
- Created `scripts/sync-backend-routing.sh` following drift-check.sh pattern:
  - Reads canonical ConfigMap from otel25-backends via `oc get`
  - Extracts `.data` section with jq
  - Patches otel25-mcp ConfigMap via `oc patch --type merge`
  - Verifies patch by comparing key counts
  - Reports PASS/FAIL summary with exit codes

## Decisions Made

1. **Content hashing over st_mtime**: SHA-256 content hashing is always reliable for detecting ConfigMap changes, regardless of CRI runtime or storage driver behavior during K8s symlink rotation. The st_mtime approach had known reliability issues documented in the Gemini review.

2. **Separate events_client**: Rather than computing events URLs per-request by rewriting the base URL, a separate `events_client` is maintained with its own lifecycle. This keeps the request path simple and allows independent URL/protocol changes for analytics vs. events backends.

3. **Protocol via ConfigMap key**: Transport selection uses an explicit `NWDAF_PROTOCOL` ConfigMap key rather than inferring from port number or hostname. This is more maintainable and allows the operator to control transport independently of the URL.

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

- Syntax check: `bash -n scripts/sync-backend-routing.sh` -- PASS
- Key check: `grep NWDAF_PROTOCOL` and `grep NWDAF_EVENTS_BASE_URL` in ConfigMap -- PASS
- Import check: AST parse of server.py confirms httpcore2, hashlib imports -- PASS
- All 10 acceptance criteria for Task 1 verified programmatically -- PASS
- All 8 acceptance criteria for Task 2 verified programmatically -- PASS
- Manual verification pending: curl --http2-prior-knowledge from NWDAF pod to NextGCore (per VALIDATION.md)

## Self-Check: PASSED

- All 4 files verified present on disk
- Commit ef69479 verified in git log
- Commit 26bbf05 verified in git log
- No unexpected file deletions in either commit
