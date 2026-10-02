---
phase: 01-backend-infrastructure
plan: 04
subsystem: nwdaf-routing
tags: [openshift, nwdaf, nextgcore, configmap, routing, backend-infrastructure, buildconfig, h2c]
dependency_graph:
  requires:
    - 01-02
    - 01-03
  provides:
    - "Real NextGCore NWDAF (Path A) running on OpenShift in otel25-backends namespace"
    - "Full 5G core stack: MongoDB, NRF, AUSF, UDM, UDR, AMF, SMF, UPF, NWDAF (9 pods)"
    - "In-cluster native amd64 build via OpenShift BuildConfig (Docker strategy)"
    - "ConfigMap backend-routing with 6 per-API base URLs (NWDAF at port 7777)"
    - "Documented mounted-file consumer contract for no-redeploy switching"
    - "D-16 switching contract verified"
  affects: [02-xx, 03-xx]
tech_stack:
  added: [nextgcore-runtime, openshift-buildconfig, nwdaf-bundled-spec]
  patterns: [configmap-mounted-file-routing, in-cluster-native-build, split-nf-topology, h2c-sbi]
key_files:
  created:
    - backends/openshift/nextgcore/deployment-nextgcore.yaml
    - backends/openshift/nextgcore/service-nwdaf.yaml
    - backends/openshift/nextgcore/Dockerfile.runtime
    - backends/openshift/nextgcore/configmap-nextgcore.yaml
    - backends/openshift/nextgcore/scc-nextgcore-upf.yaml
    - backends/openshift/configmap-backend-routing.yaml
    - backends/specs/nwdaf_analyticsinfo_bundled.yaml
  modified:
    - backends/scripts/check-nwdaf.sh
    - backends/scripts/verify-routing.sh
decisions:
  - "Path A (real NextGCore) deployed: cross-compilation solved via OpenShift BuildConfig native amd64 build"
  - "Unified runtime image: single nextgcore-runtime image with all NF binaries (avoids 8 separate BuildConfigs)"
  - "NEXTGCORE_SBI_PROFILE=dev required for cleartext HTTP/2 h2c (no TLS certificates in dev cluster)"
  - "NWDAF CLI args override config file: --sbi-port 7777 and --nrf-uri needed since NWDAF defaults differ from config"
  - "AMF binds SBI to 127.0.0.1 in dev mode: exec probe replaces tcpSocket probe for readiness"
  - "ConfigMap uses mounted-file-only consumer contract (not env vars) for no-redeploy compliance"
metrics:
  duration: 45 minutes
  completed: "2026-10-02T19:57:00Z"
---

# Phase 1 Plan 04: NWDAF Backend and Routing ConfigMap Summary

Real NextGCore NWDAF deployed on OpenShift via in-cluster BuildConfig (solving ARM64-to-amd64 cross-compilation), full 5G core stack with 9 pods all Running, NWDAF responding to NF_LOAD analytics on HTTP/2 h2c port 7777; ConfigMap backend-routing updated with 6 per-API URLs verified for live switching.

## Performance

- **Duration:** ~45 min (across two agent sessions; includes ~18 min builder compilation, ~1 min runtime build)
- **Completed:** 2026-10-02T19:57:00Z
- **Tasks:** 2 auto + 1 checkpoint (approved)
- **Files created:** 7
- **Files modified:** 2

## Accomplishments

- Built NextGCore natively on amd64 cluster via OpenShift BuildConfig (Docker strategy), solving ARM64 cross-compilation
- Two-stage build chain: `nextgcore-builder` (Rust compilation, 18 min) then `nextgcore-runtime` (runtime deps + binaries, 1 min)
- Deployed full 5G core stack: MongoDB, NRF, AUSF, UDM, UDR, AMF, SMF, UPF, NWDAF (9 pods, all 1/1 Running)
- NWDAF registered with NRF successfully, NRF NFStatusSubscribe active
- NWDAF analytics endpoint responds to `GET /nnwdaf-analyticsinfo/v1/analytics?event-id=NF_LOAD` with HTTP 204 (correct: no UE load data on fresh deployment)
- HTTP/2 h2c protocol confirmed via curl `--http2-prior-knowledge`
- Custom SCC for UPF: privileged + NET_ADMIN + SYS_ADMIN + /dev/net/tun
- ConfigMap backend-routing updated: NWDAF_BASE_URL now points to port 7777
- Scripts updated for NextGCore paths and HTTP/2
- User verified all 4 verification steps independently

## BACK-02 Status: Fully Satisfied (Path A)

**The real NextGCore NWDAF is deployed and responding.** This fully satisfies BACK-02 ("Deploy NextGCore on OpenShift with working NWDAF endpoints for execution-verified analytics tool calls").

**How the cross-compilation blocker was solved:**
1. Plan 02 GO decision confirmed NextGCore NWDAF returns real NF_LOAD analytics data
2. All Plan 02 images were ARM64 (built on Apple Silicon macOS); cluster is amd64
3. Local cross-compilation failed: Dockerfile.builder cargo config missing x86_64 linker entry
4. Solution: OpenShift BuildConfig with Docker strategy builds natively on cluster amd64 nodes
5. Two-stage build: `nextgcore-builder` (all Rust binaries, ~18 min) then `nextgcore-runtime` (single image with all NF binaries + runtime deps)
6. All 9 NFs deployed from the unified runtime image, each Deployment overriding the command to select its specific binary

**Build artifacts on cluster:**
- ImageStream `nextgcore-builder`: builder image with compiled binaries in /out/
- ImageStream `nextgcore-runtime`: runtime image with all NF binaries at /usr/local/bin/
- BuildConfig `nextgcore-builder`: Docker strategy, 8 CPU / 16Gi memory
- BuildConfig `nextgcore-runtime`: Docker strategy, 2 CPU / 4Gi memory

## Task Commits

1. **Task 1: Deploy real NextGCore NWDAF on OpenShift (Path A)** - `cb42be9` (feat)
2. **Task 2: Update backend-routing ConfigMap and scripts** - `a13cb1d` (feat)
3. **Task 3: Human verification** - checkpoint approved

**Prior commits (from earlier Path B session, now superseded):**
- `957b839` - Original Prism NWDAF deployment (superseded by cb42be9)
- `c5a9595` - Original ConfigMap backend-routing (superseded by a13cb1d)

## Files Created/Modified

- `backends/openshift/nextgcore/deployment-nextgcore.yaml` - Full NextGCore stack: 9 Deployments + Services (MongoDB, NRF, AUSF, UDM, UDR, AMF, SMF, UPF, NWDAF)
- `backends/openshift/nextgcore/service-nwdaf.yaml` - nextgcore-nwdaf ClusterIP Service on port 7777
- `backends/openshift/nextgcore/Dockerfile.runtime` - Multi-stage Dockerfile: extracts binaries from builder, adds runtime deps
- `backends/openshift/nextgcore/configmap-nextgcore.yaml` - NF configuration ConfigMap (NRF, AUSF, UDM, UDR, AMF, SMF, UPF, NWDAF)
- `backends/openshift/nextgcore/scc-nextgcore-upf.yaml` - Custom SCC for UPF (privileged, NET_ADMIN, SYS_ADMIN)
- `backends/openshift/configmap-backend-routing.yaml` - 6 per-API base URLs, NWDAF_BASE_URL at port 7777
- `backends/specs/nwdaf_analyticsinfo_bundled.yaml` - Self-contained NWDAF AnalyticsInfo spec (retained from Path B work)
- `backends/scripts/check-nwdaf.sh` - Updated: port 7777, NextGCore path, HTTP/2 h2c support
- `backends/scripts/verify-routing.sh` - Updated: NWDAF test path for NextGCore

## Decisions Made

- **OpenShift BuildConfig for native build:** Instead of fixing Dockerfile.builder cross-compilation (which failed twice), used OpenShift BuildConfig with Docker strategy to compile on amd64 cluster nodes. This avoids the ARM64-to-amd64 cross-compilation entirely.
- **Unified runtime image:** Single `nextgcore-runtime` image contains ALL NF binaries (not per-NF images). Each Deployment overrides `command` to select its binary. More efficient: 2 builds total instead of 10.
- **NEXTGCORE_SBI_PROFILE=dev:** Required for cleartext HTTP/2 h2c. Without it, NFs crash with "SBI production profile requires a TLS certificate." NRF, UDR, and UPF are unaffected (different TLS defaults).
- **NWDAF CLI args:** The NWDAF binary defaults to port 7815 and NRF at 127.0.0.1:7777. The config file does not override these. Explicit `--sbi-port 7777 --nrf-uri http://nrf.otel25-backends.svc.cluster.local:7777` CLI args are required.
- **AMF exec probe:** AMF binds SBI to 127.0.0.1 in dev mode, making tcpSocket probes (which connect via pod IP) fail. Changed to exec probe using `curl -sf http://127.0.0.1:7777/health`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] NFs crash with TLS certificate requirement**
- **Found during:** Task 1 (initial deployment)
- **Issue:** AUSF, UDM, AMF, SMF all crash with "SBI production profile requires a TLS certificate at /etc/nextgcore/tls/server.crt"
- **Fix:** Added `NEXTGCORE_SBI_PROFILE=dev` environment variable to all NF containers
- **Files modified:** `backends/openshift/nextgcore/deployment-nextgcore.yaml`
- **Commit:** `cb42be9`

**2. [Rule 1 - Bug] NWDAF uses wrong port and NRF address**
- **Found during:** Task 1 (initial deployment)
- **Issue:** NWDAF binary defaults to port 7815 and NRF at 127.0.0.1:7777 instead of reading from config file
- **Fix:** Added explicit CLI args `--sbi-port 7777 --nrf-uri http://nrf.otel25-backends.svc.cluster.local:7777`
- **Files modified:** `backends/openshift/nextgcore/deployment-nextgcore.yaml`
- **Commit:** `cb42be9`

**3. [Rule 1 - Bug] AMF readiness probe fails due to localhost binding**
- **Found during:** Task 1 (pods not becoming Ready)
- **Issue:** AMF binds SBI to 127.0.0.1 in dev mode; tcpSocket probe connects via pod IP (10.129.x.x), connection refused
- **Fix:** Changed AMF readiness/liveness probes from tcpSocket to exec (`curl -sf http://127.0.0.1:7777/health || ss -tln | grep -q 7777`)
- **Files modified:** `backends/openshift/nextgcore/deployment-nextgcore.yaml`
- **Commit:** `cb42be9`

**4. [Rule 3 - Blocking] BuildConfig runtime build fails with "no FROM image"**
- **Found during:** Task 1 (runtime image build)
- **Issue:** BuildConfig source spec had `dockerfile: ""` which overrode the Dockerfile from context with an empty string
- **Fix:** Removed the empty `dockerfile` field from BuildConfig source spec via `oc patch --type=json`; used `--from-dir` instead of `--from-file`
- **Files modified:** None (cluster-side fix only)
- **Commit:** N/A (cluster configuration, not repo files)

## Verification Results

### Pod Status (9/9 Running)
| NF | Pod | Ready | Status |
|----|-----|-------|--------|
| MongoDB | mongodb-56ddc7fd7f-ltvrg | 1/1 | Running |
| NRF | nrf-658fc59f76-lbqnw | 1/1 | Running |
| AUSF | ausf-579c79877c-phlt5 | 1/1 | Running |
| UDM | udm-6fb9dbb647-7mmcj | 1/1 | Running |
| UDR | udr-867444c4c9-nsdhg | 1/1 | Running |
| AMF | amf-7b86fdc5df-rnqmc | 1/1 | Running |
| SMF | smf-57ccd9f487-p2bbp | 1/1 | Running |
| UPF | upf-b4d49b599-nkkcm | 1/1 | Running |
| NWDAF | nwdaf-5d7b7bfb4-4hpkp | 1/1 | Running |

### NWDAF Endpoint Verification
- **URL:** `http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:7777/nnwdaf-analyticsinfo/v1/analytics?event-id=NF_LOAD`
- **Protocol:** HTTP/2 h2c (confirmed via `--http2-prior-knowledge`)
- **Response:** HTTP 204 No Content (correct for fresh deployment with no UE traffic)
- **NRF Registration:** "NWDAF registered with NRF successfully"
- **NRF NFStatusSubscribe:** Active

### ConfigMap Verification
- `NWDAF_BASE_URL`: `http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:7777` (confirmed)
- All 6 routing keys present: TMF642, TMF628, TMF621, CAMARA, CAMARA_RETRIEVAL, NWDAF

## NWDAF Endpoint Details (for downstream phases)

- **Service name:** nextgcore-nwdaf
- **Port:** 7777 (SBI)
- **Protocol:** HTTP/2 h2c (use `curl --http2-prior-knowledge`)
- **Analytics path:** `/nnwdaf-analyticsinfo/v1/analytics`
- **ConfigMap key:** `NWDAF_BASE_URL = http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:7777`
- **Working event type:** NF_LOAD
- **Expected response:** HTTP 204 (no load data) or HTTP 200 with analytics JSON (when NFs have load data)
- **Curl example:** `curl --http2-prior-knowledge "http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:7777/nnwdaf-analyticsinfo/v1/analytics?event-id=NF_LOAD"`

## Known Stubs

None -- NWDAF returns real analytics responses (HTTP 204 when no data, HTTP 200 with TS 29.520 analytics when load data exists).

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: elevated-privilege | scc-nextgcore-upf.yaml | Custom SCC grants privileged + NET_ADMIN + SYS_ADMIN to UPF ServiceAccount. Mitigated by: dedicated SA (not default), UPF in separate pod, internal-only ClusterIP, dev cluster (D-01). |

## Self-Check: PASSED

- [x] backends/openshift/nextgcore/deployment-nextgcore.yaml exists
- [x] backends/openshift/nextgcore/service-nwdaf.yaml exists
- [x] backends/openshift/nextgcore/Dockerfile.runtime exists
- [x] backends/openshift/nextgcore/configmap-nextgcore.yaml exists
- [x] backends/openshift/nextgcore/scc-nextgcore-upf.yaml exists
- [x] backends/openshift/configmap-backend-routing.yaml exists
- [x] backends/specs/nwdaf_analyticsinfo_bundled.yaml exists
- [x] Task 1 commit cb42be9 found in git log
- [x] Task 2 commit a13cb1d found in git log
- [x] 9 pods verified 1/1 Running via oc get pods
- [x] NWDAF responds HTTP 204 to NF_LOAD query
- [x] ConfigMap NWDAF_BASE_URL points to port 7777
- [x] NWDAF registered with NRF successfully
- [x] User independently verified all 4 verification steps

---
*Phase: 01-backend-infrastructure*
*Completed: 2026-10-02 (checkpoint approved)*
