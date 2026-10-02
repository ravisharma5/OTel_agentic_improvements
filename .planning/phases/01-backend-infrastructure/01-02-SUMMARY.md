---
phase: 01-backend-infrastructure
plan: 02
subsystem: nwdaf-validation
tags: [nextgcore, nwdaf, podman, validation, 5g-core]
dependency_graph:
  requires: []
  provides: [nwdaf-go-decision, nextgcore-port-findings]
  affects: [01-04-PLAN]
tech_stack:
  added: [nextgcore, nextgsim, podman-compose-workflow]
  patterns: [build-from-source, h2c-sbi, docker-shim-for-podman]
key_files:
  created:
    - .planning/phases/01-backend-infrastructure/01-02-nwdaf-validation-findings.md
  modified: []
decisions:
  - "GO: Deploy real NextGCore NWDAF on OpenShift (not Prism fallback)"
  - "NWDAF SBI port is 7777, not 8080 (RESEARCH.md Assumption A4 invalidated)"
  - "All SBI endpoints use HTTP/2 h2c (not HTTP/1.1)"
  - "NF_LOAD is the only event type returning real analytics data"
  - "UPF requires privileged + NET_ADMIN + SYS_ADMIN + /dev/net/tun (exceeds original NET_ADMIN-only SCC design)"
metrics:
  duration: 46 minutes
  completed: "2026-10-02T15:20:05Z"
---

# Phase 1 Plan 02: NextGCore NWDAF Local Validation Summary

GO decision on NWDAF: NWDAF returns real NF_LOAD analytics (HTTP 200 with per-NF load metrics) via Podman-validated E2E stack; deploy NextGCore on OpenShift in Plan 04, not Prism fallback.

## What Was Done

### Task 1: Clone, Build, Start, and Test NextGCore Stack

1. **Podman machine started** on macOS ARM64 (libkrun VM, Podman 5.6.1).
2. **Cloned** `github.com/NextgCoreLab/nextgcore` and `github.com/NextgCoreLab/nextgsim`.
3. **Built all 22 NF images from source** (~20 min Rust compilation via `rust:1.95.0-bookworm` builder, then individual `debian:bookworm-slim` runtime images per NF). No pre-built images exist on any public registry.
4. **Started the full 5G SA stack** using `docker-compose v5.0.2` against the Podman socket (not `podman-compose`, per RESEARCH.md Pitfall 3). All 22 containers started successfully.
5. **Verified UE registration and PDU session** (D-13): UE registered (`RM-REGISTERED, CM-CONNECTED`), PDU session 1 active (IPv4 10.45.0.2). Both markers found on first check.
6. **Tested NWDAF analytics endpoint**: NF_LOAD returned HTTP 200 with real analytics JSON; LOAD_LEVEL_INFORMATION, ABNORMAL_BEHAVIOUR, UE_MOBILITY returned 204 (no data). Event subscription and ML model provision endpoints exist (405 on GET = accept POST).
7. **Inspected k8s/ directory**: Contains real Kind manifests for core NFs but NO NWDAF manifest.
8. **Cleaned up**: `docker-compose down -v`.

### Task 2: GO/NO-GO Decision

**Decision: GO (go-nextgcore)**

Deploy real NextGCore NWDAF on OpenShift in Plan 04. The NWDAF returns real NF_LOAD analytics data with per-NF metrics (nfType, nfInstanceId, nfStatus, nfCpuUsage, nfLoadLevelAverage, nfLoadLevelpeak, confidence), which provides meaningfully better training data for the SDG pipeline than schema-generated Prism mock responses.

**Rationale:** The empirical test showed NWDAF is functional for its primary use case (NF load analytics). While most event types return 204, the NF_LOAD data alone provides real operational metrics that Prism cannot replicate. The OpenShift porting effort is justified by the data quality improvement for downstream fault prediction training.

**BACK-02 status:** GO means Plan 04 will deploy NextGCore on OpenShift as BACK-02 originally specified. No fallback deviation needed.

## Critical Findings for Plan 04

Plan 04's executor MUST read these findings before writing OpenShift manifests. Several RESEARCH.md assumptions were invalidated by empirical testing.

### 1. SBI Port is 7777, NOT 8080 (Assumption A4 invalidated)

All NextGCore NFs, including NWDAF, listen on SBI port **7777**. The NWDAF config confirms:
```yaml
nwdaf:
  sbi:
    server:
      - address: 0.0.0.0
        advertise: 172.23.0.30
        port: 7777
```

**Impact on Plan 04:** All Service definitions, health check probes, ConfigMap URLs (`NWDAF_BASE_URL`), and `check-nwdaf.sh` must target port **7777**, not 8080. The ConfigMap entry should be:
```yaml
NWDAF_BASE_URL: "http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:7777"
```

### 2. SBI Protocol is HTTP/2 h2c, NOT HTTP/1.1

All NextGCore SBI endpoints use HTTP/2 cleartext (h2c). Standard HTTP/1.1 `curl` returns "Received HTTP/0.9 when not allowed."

**Impact on Plan 04:**
- Health check probes: Kubernetes `httpGet` probes use HTTP/1.1 by default. Plan 04 must use `exec` probes with `curl --http2-prior-knowledge` instead, or use a TCP/command-based check.
- `check-nwdaf.sh`: Must use `curl --http2-prior-knowledge` for all NWDAF requests.
- ConfigMap routing verification script: NWDAF endpoint requires HTTP/2 unlike the Prism mocks.

### 3. UPF Requires More Than NET_ADMIN (SCC Revision Needed)

The docker-compose.yml shows UPF requires:
```yaml
privileged: true
user: root
cap_add:
  - NET_ADMIN
  - SYS_ADMIN
devices:
  - /dev/net/tun:/dev/net/tun
sysctls:
  - net.ipv4.ip_forward=1
```

**Impact on Plan 04:** The custom SCC in RESEARCH.md Pattern 3 only accounts for `NET_ADMIN` and `NET_RAW`. The actual requirement is `privileged: true` + `NET_ADMIN` + `SYS_ADMIN` + device access. Plan 04's SCC manifest AND threat model need revision:
- The SCC must either grant `privileged` or grant the specific combination of `NET_ADMIN` + `SYS_ADMIN` + `allowHostDirVolumePlugin` (for `/dev/net/tun`)
- Threat register entry T-02-02 needs updating to reflect the actual privilege level

### 4. No NWDAF Kubernetes Manifest Exists (Open Question Resolved)

The `k8s/` directory contains Kind manifests for: NRF, AUSF, UDM, UDR, PCF, NSSF, BSF, AMF, SMF, UPF. **NWDAF has no manifest.** The kustomization.yaml does not include it.

**Impact on Plan 04:** The NWDAF Deployment + Service manifest must be authored from scratch. Use the docker-compose.yml NWDAF service definition as the source of truth:
```yaml
# From docker-compose.yml:
nwdaf:
  image: nextgcore-rust/nwdaf:latest
  command: ["--sbi-addr", "172.23.0.30", "--sbi-port", "7777", "--nrf-uri", "http://172.23.0.10:7777"]
  volumes:
    - ./configs/5gc/nwdaf.yaml:/etc/nextgcore/nwdaf.yaml:ro
  depends_on:
    nrf: {condition: service_healthy}
```

The existing `k8s/manifests/*.yaml` files for other NFs can serve as templates for the manifest structure.

### 5. No Pre-Built Container Images on Any Registry

All NextGCore images must be built from source using the `docker/rust/build.sh` script and `Dockerfile.builder` + `Dockerfile.core` + `Dockerfile.nf` pipeline. Build time: ~20 minutes on ARM64.

**Impact on Plan 04:** Plan 04 must include steps to:
1. Build images locally (or in CI)
2. Tag and push to the OpenShift internal registry or an external registry
3. Reference the registry path in Deployment manifests

### 6. NF_LOAD is the Only Working Event Type

| Event ID | HTTP Status | Data Returned |
|----------|-------------|---------------|
| NF_LOAD | 200 | Yes -- per-NF load metrics (8 NFs) |
| LOAD_LEVEL_INFORMATION | 204 | No |
| ABNORMAL_BEHAVIOUR | 204 | No |
| UE_MOBILITY | 204 | No |

**Impact on Plan 04:** The `check-nwdaf.sh` verification script must query `event-id=NF_LOAD` (not `LOAD_LEVEL_INFORMATION` as previously assumed). Example working command:
```bash
curl --http2-prior-knowledge -s \
  "http://nextgcore-nwdaf:7777/nnwdaf-analyticsinfo/v1/analytics?event-id=NF_LOAD"
```

### 7. Subscriptions are Memory-Only (Confirmed)

NWDAF logs: `"NWDAF durable state disabled (no --state-file / NEXTGCORE_NWDAF_STATE_FILE): analytics and ML-provision subscriptions are memory-only and lost on restart"`

**Impact on Plan 04:** Use one-shot GET queries only, not POST subscriptions. If subscriptions are needed later, they must be re-established after any pod restart. Consider setting `NEXTGCORE_NWDAF_STATE_FILE` with a PVC for durable state.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Podman VM volume mount path**
- **Found during:** Task 1, Step 4
- **Issue:** Repos cloned to `/tmp/` were not accessible from the Podman VM on macOS (only `/Users/` is shared by default with the libkrun VM).
- **Fix:** Moved repos from `/tmp/nextgcore` and `/tmp/nextgsim` to `/Users/ravsharm/nextg-validation/` where the Podman VM can access them.
- **Files modified:** None (operational fix, not code change)

**2. [Rule 3 - Blocking] No `docker` CLI available**
- **Found during:** Task 1, Step 4
- **Issue:** The build script (`build.sh`) uses `docker` commands, but only `podman` is installed. The `docker` CLI is not available on this machine.
- **Fix:** Created a `/tmp/docker-shim/docker` wrapper that delegates to `podman`. Then ran the build steps individually using `podman` directly instead of through the build script.
- **Files modified:** None (operational fix)

**3. [Rule 3 - Blocking] Prometheus/Grafana mount failure**
- **Found during:** Task 1, Step 4
- **Issue:** Prometheus container failed to start with `OCI runtime error: Not a directory` on the config file mount.
- **Fix:** Excluded Prometheus and Grafana from the startup (not needed for NWDAF validation). Started only the 20 core NFs + MongoDB + Jaeger.
- **Files modified:** None (operational workaround)

**4. [Rule 1 - Bug] NWDAF port assumption was wrong**
- **Found during:** Task 1, Step 6
- **Issue:** RESEARCH.md Assumption A4 and the plan assumed NWDAF listens on port 8080. Actual port is 7777 (same SBI port as all NFs).
- **Fix:** Used correct port 7777 for all curl commands. Documented in findings for Plan 04.
- **Files modified:** None (documented, not code)

**5. [Rule 1 - Bug] HTTP/2 protocol requirement not anticipated**
- **Found during:** Task 1, Step 6
- **Issue:** All NextGCore SBI endpoints use HTTP/2 h2c. Standard curl (HTTP/1.1) returns "Received HTTP/0.9 when not allowed."
- **Fix:** Used `curl --http2-prior-knowledge` for all NWDAF requests. Documented as critical finding for Plan 04.
- **Files modified:** None (documented, not code)

## Known Stubs

None -- this plan produces documentation and a decision, not application code.

## Self-Check: PASSED

- [x] 01-02-nwdaf-validation-findings.md exists
- [x] 01-02-SUMMARY.md exists
- [x] Task 1 commit 7dd08d3 found in git log
