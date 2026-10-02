# NWDAF Local Validation Findings

**Date:** 2026-10-02
**Plan:** 01-02 (NextGCore NWDAF Local Validation)
**Status:** Task 1 complete, awaiting GO/NO-GO decision (Task 2 checkpoint)

## Environment

- **Machine:** macOS ARM64 (Apple Silicon)
- **Podman:** 5.6.1 with libkrun VM
- **docker-compose:** v5.0.2 (standalone binary against Podman socket)
- **NextGCore:** cloned from github.com/NextgCoreLab/nextgcore (HEAD at time of clone)
- **nextgsim:** cloned from github.com/NextgCoreLab/nextgsim (HEAD at time of clone)

## Build Process

All 22 NF images were built from source:
1. Rust binaries compiled inside a Docker builder container (rust:1.95.0-bookworm)
2. Individual NF images built from debian:bookworm-slim + extracted binary
3. gNB and UE simulator images built from nextgsim Dockerfiles
4. Total build time: ~20 minutes (Rust compilation + image creation)

No pre-built images exist on public registries -- build from source is required.

## Stack Startup Results

All 22 containers started successfully (20 NFs + MongoDB + Jaeger):

| Container | Status | Notes |
|-----------|--------|-------|
| nextgcore-mongodb | Running | MongoDB 6.0 for subscriber data |
| nextgcore-nrf | Running (healthy) | NRF registered successfully |
| nextgcore-ausf | Running | Auth server function |
| nextgcore-udm | Running | Unified data management |
| nextgcore-udr | Running | Unified data repository |
| nextgcore-pcf | Running | Policy control function |
| nextgcore-nssf | Running | Network slice selection |
| nextgcore-bsf | Running | Binding support function |
| nextgcore-amf | Running | Access and mobility management |
| nextgcore-smf | Running | Session management function |
| nextgcore-upf | Running | User plane function (privileged, NET_ADMIN) |
| nextgcore-nwdaf | Running | NWDAF analytics -- the validation target |
| nextgcore-ees | Running | Edge enabler server |
| nextgcore-lmf | Running | Location management function |
| nextgcore-mbsmf | Running | Multicast/broadcast SMF |
| nextgcore-nsacf | Running | Network slice admission control |
| nextgcore-pin | Running | Personal IoT network |
| nextgcore-dccf | Running | Data collection coordination |
| nextgcore-scp | Running | Service communication proxy |
| nextgcore-sepp | Running | Security edge protection proxy |
| nextgsim-gnb | Running | gNB simulator |
| nextgsim-ue | Running | UE simulator |

**Issue resolved during startup:** Containers needed to be in a directory under `/Users/`
(not `/tmp/`) because macOS Podman VMs only share `/Users/` by default. The repos were
moved from `/tmp/` to `/Users/ravsharm/nextg-validation/` to resolve volume mount failures.

**Monitoring stack (Prometheus/Grafana) skipped:** Prometheus had a volume mount issue
(`OCI runtime error: Not a directory`). Since monitoring is not needed for NWDAF validation,
these containers were excluded from the startup.

## UE Registration and PDU Session (D-13)

Both markers found on the first check (no polling loop needed -- NFs started quickly):

**UE Registration:**
```
Registration Accept: UE is now MM[RM-REGISTERED, CM-CONNECTED, 5GMM-REGISTERED.NORMAL-SERVICE, U1-UPDATED]
```

**PDU Session:**
```
PDU Session 1 is now ACTIVE (IPv4: Some([10, 45, 0, 2]))
```

## NWDAF Analytics Endpoint Testing

### Key Finding: SBI port is 7777, not 8080

The NWDAF SBI server listens on port **7777** (same as all other NFs), not port 8080
as assumed in RESEARCH.md (Assumption A4). The NWDAF config (`nwdaf.yaml`) confirms:
```yaml
nwdaf:
  sbi:
    server:
      - address: 0.0.0.0
        advertise: 172.23.0.30
        port: 7777
```

### Key Finding: SBI uses HTTP/2 (h2c), not HTTP/1.1

All NextGCore SBI endpoints use HTTP/2 cleartext (h2c). curl requires
`--http2-prior-knowledge` flag. Without it, curl reports "Received HTTP/0.9 when not allowed."

### Test Results

| Endpoint | Event ID | HTTP Status | Response |
|----------|----------|-------------|----------|
| /nnwdaf-analyticsinfo/v1/analytics | NF_LOAD | **200 OK** | Full JSON with nfLoadLevelInfos for 8 NFs |
| /nnwdaf-analyticsinfo/v1/analytics | LOAD_LEVEL_INFORMATION | 204 No Content | No analytics data available |
| /nnwdaf-analyticsinfo/v1/analytics | ABNORMAL_BEHAVIOUR | 204 No Content | No analytics data available |
| /nnwdaf-analyticsinfo/v1/analytics | UE_MOBILITY | 204 No Content | No analytics data available |
| /nnwdaf-eventssubscription/v1/subscriptions | N/A (GET) | 405 | Endpoint exists, requires POST |
| /nnwdaf-mlmodelprovision/v1/subscriptions | N/A (GET) | 405 | Endpoint exists, requires POST |

### NF_LOAD Response (full JSON)

```json
{
  "nfLoadLevelInfos": [
    {"nfType":"DCCF","nfInstanceId":"2b26face-408d-44e2-b07c-7abb2d4c4ba9","nfStatus":{"statusRegistered":100},"nfCpuUsage":0,"nfLoadLevelAverage":0,"nfLoadLevelpeak":0,"confidence":0},
    {"nfType":"UDM","nfInstanceId":"4d61703d-32bb-409b-ba05-91f5caf7f7d3","nfStatus":{"statusRegistered":100},"nfCpuUsage":0,"nfLoadLevelAverage":0,"nfLoadLevelpeak":0,"confidence":0},
    {"nfType":"AUSF","nfInstanceId":"515c18b0-a0e8-4320-9e20-db5321df71e4","nfStatus":{"statusRegistered":100},"nfCpuUsage":0,"nfLoadLevelAverage":0,"nfLoadLevelpeak":0,"confidence":0},
    {"nfType":"BSF","nfInstanceId":"687b1fb7-af8d-4920-a9f1-9275c74becef","nfStatus":{"statusRegistered":100},"nfCpuUsage":0,"nfLoadLevelAverage":0,"nfLoadLevelpeak":0,"confidence":0},
    {"nfType":"AMF","nfInstanceId":"91cf4faf-3a2b-4256-a6a9-a0b8bb130297","nfStatus":{"statusRegistered":100},"nfCpuUsage":0,"nfLoadLevelAverage":0,"nfLoadLevelpeak":0,"confidence":0},
    {"nfType":"UDR","nfInstanceId":"9ec25708-935f-42be-a9e8-369a2e661fb0","nfStatus":{"statusRegistered":100},"nfCpuUsage":1,"nfLoadLevelAverage":1,"nfLoadLevelpeak":1,"confidence":100},
    {"nfType":"LMF","nfInstanceId":"a0ae5d3f-7a2c-4394-b573-d3429e53269e","nfStatus":{"statusRegistered":100},"nfCpuUsage":0,"nfLoadLevelAverage":0,"nfLoadLevelpeak":0,"confidence":0},
    {"nfType":"SMF","nfInstanceId":"b4682ea4-2647-4821-b32e-3efe830ac21d","nfStatus":{"statusRegistered":100},"nfCpuUsage":0,"nfLoadLevelAverage":0,"nfLoadLevelpeak":0,"confidence":0}
  ],
  "start":"2026-10-02T15:00:41.233377889+00:00",
  "expiry":"2026-10-02T16:00:41.233377889+00:00",
  "timeStampGen":"2026-10-02T15:00:41.233377889+00:00"
}
```

## k8s/ Directory Assessment (Assumption A1)

The `k8s/` directory contains **real Kubernetes manifests** written for Kind:

```
k8s/
  base/namespace.yaml
  kustomization.yaml          # Kustomize base
  manifests/
    amf.yaml, ausf.yaml, bsf.yaml, configmap.yaml,
    mongodb-init.yaml, mongodb.yaml, nrf.yaml, nssf.yaml,
    pcf.yaml, smf.yaml, udm.yaml, udr.yaml, upf.yaml
  monitoring/
  deploy.sh, e2e-test.sh, teardown.sh, kind-config.yaml
```

**Critical finding: NO NWDAF manifest exists in `k8s/`.** The kustomization.yaml only
includes the core 5G NFs (NRF, AUSF, UDM, UDR, PCF, NSSF, BSF, AMF, SMF, UPF).
The NWDAF, EES, LMF, MBSMF, NSACF, PIN, DCCF, SCP, SEPP are only defined in
docker-compose.yml. OpenShift deployment of NWDAF would require writing manifests
from scratch, not adapting existing k8s/ manifests.

## Known Limitations for OpenShift Deployment

1. **No pre-built images:** Must build from source (~20 min), push to cluster registry
2. **No NWDAF k8s manifest:** Must write from scratch for OpenShift
3. **UPF needs privileged + NET_ADMIN + SYS_ADMIN + /dev/net/tun:** Confirmed from docker-compose.yml
4. **HTTP/2 (h2c) on all SBI endpoints:** Probes and curl commands need HTTP/2 support
5. **NWDAF subscriptions are memory-only (issue #192):** Confirmed in NWDAF logs ("durable state disabled")
6. **NF_LOAD is the only event type returning data:** LOAD_LEVEL_INFORMATION, ABNORMAL_BEHAVIOUR, UE_MOBILITY all return 204

## Assessment for GO/NO-GO Decision

**Evidence FOR go-nextgcore:**
- NWDAF endpoint exists and returns real analytics data (HTTP 200 for NF_LOAD)
- NF_LOAD response includes per-NF load metrics with nfType, nfInstanceId, nfStatus, cpuUsage, loadLevels
- All 22 NFs start and run stable
- UE registration and PDU session establishment work correctly
- Event subscription and ML model provision endpoints exist (405 on GET = endpoint exists, needs POST)
- Data includes timestamps, confidence values, and NF status -- usable for downstream SDG

**Evidence FOR nogo-prism-fallback:**
- Most event types return 204 (no data) -- only NF_LOAD produces real results
- No NWDAF k8s manifest exists -- must write from scratch
- Build-from-source is required (no pre-built images)
- UPF requires privileged containers with NET_ADMIN/SYS_ADMIN on OpenShift (complex SCC)
- HTTP/2 requirement adds complexity for downstream tool integration
- NWDAF subscriptions are memory-only (no persistence across restarts)
- OpenShift porting of 22-NF stack is significant effort beyond just NWDAF
