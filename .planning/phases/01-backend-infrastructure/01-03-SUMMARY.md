---
phase: 01-backend-infrastructure
plan: 03
subsystem: infra
tags: [openshift, prism, deployment, tmf642, tmf628, tmf621, camara, mock-backends]

# Dependency graph
requires:
  - 01-01
provides:
  - "5 Prism mock pods running on OpenShift in otel25-backends namespace"
  - "6 OpenShift manifest files (1 namespace + 5 Deployment/Service pairs)"
  - "Internal registry images for all 5 Prism mocks"
  - "Validated mock endpoints: TMF642, TMF628, TMF621, CAMARA verify, CAMARA retrieval"
affects: [01-04]

# Tech tracking
tech-stack:
  added: [openshift-internal-registry]
  patterns: [deployment-service-clusterip, tcpsocket-probe-for-post-apis, multiprocess-false-prism-docker]

key-files:
  created:
    - backends/openshift/namespace.yaml
    - backends/openshift/prism-tmf642.yaml
    - backends/openshift/prism-tmf628.yaml
    - backends/openshift/prism-tmf621.yaml
    - backends/openshift/prism-camara.yaml
    - backends/openshift/prism-camara-retrieval.yaml
  modified:
    - backends/prism/Dockerfile
    - backends/scripts/validate-mocks.sh

key-decisions:
  - "Images pushed to OpenShift internal registry (not public fallback) -- registry route enabled via imageregistry operator patch"
  - "Prism multiprocess mode disabled (-m false) to fix cluster.isPrimary crash in stoplight/prism:5 Docker image"
  - "CAMARA validate-mocks.sh requests include Authorization Bearer token and spec-compliant request bodies (empty {} caused 422)"

patterns-established:
  - "Prism Dockerfile requires -m false flag to disable Node.js cluster module multiprocessing in container environments"
  - "CAMARA specs with OAuth2 security require Bearer token even for Prism mock responses"
  - "tcpSocket probes for POST-heavy API specs prevent crash-looping from 4xx/405 responses"

requirements-completed: [BACK-01]

# Metrics
duration: 13min
completed: 2026-10-02
---

# Phase 1 Plan 03: Deploy 5 Prism Mock Backends on OpenShift Summary

**5 Prism mock pods deployed on OpenShift with internal registry images, validated via port-forward curl tests and validate-mocks.sh returning all 5 endpoints PASS**

## Performance

- **Duration:** 13 min
- **Started:** 2026-10-02T15:25:18Z
- **Completed:** 2026-10-02T15:38:31Z
- **Tasks:** 2 (1 checkpoint auto-satisfied, 1 auto)
- **Files created:** 6
- **Files modified:** 2

## Accomplishments

- Verified OpenShift cluster access (admin user, cluster-admin SCC privilege, OpenShift 4.20 on AWS us-east-2)
- Created otel25-backends namespace with purpose label
- Created 5 Deployment+Service YAML manifests following RESEARCH.md Pattern 1 exactly
- TMF642/628/621 use httpGet probes on spec-defined GET endpoints (/alarm, /measurementCollectionJob, /troubleTicket)
- CAMARA verify/retrieval use tcpSocket probes on port 4010 (POST-heavy APIs, no safe GET endpoints)
- All Services are ClusterIP (no external Routes, per T-03-01 threat mitigation)
- Built 5 Prism container images with parameterized Dockerfile (SPEC_FILE build arg)
- Enabled OpenShift internal registry default route and pushed all 5 images
- All 5 pods Running with 1/1 READY status
- validate-mocks.sh passes with all 5 endpoints: HTTP 200, valid JSON, spec-specific fields present

## Task Commits

Each task was committed atomically:

1. **Task 1: Provision OpenShift cluster and establish oc CLI access** - Auto-satisfied (cluster already accessible: admin@api.cluster-wfhjs...sandbox1330.opentlc.com:6443, OpenShift 4.20, cluster-admin confirmed)
2. **Task 2: Create OpenShift manifests, build Prism images, deploy 5 mock backends** - `8a1fae4` (feat)

## Files Created/Modified

- `backends/openshift/namespace.yaml` - otel25-backends Namespace with purpose: phase-1-backends label
- `backends/openshift/prism-tmf642.yaml` - TMF642 Deployment (httpGet /alarm probe) + ClusterIP Service
- `backends/openshift/prism-tmf628.yaml` - TMF628 Deployment (httpGet /measurementCollectionJob probe) + ClusterIP Service
- `backends/openshift/prism-tmf621.yaml` - TMF621 Deployment (httpGet /troubleTicket probe) + ClusterIP Service
- `backends/openshift/prism-camara.yaml` - CAMARA verification Deployment (tcpSocket probe) + ClusterIP Service
- `backends/openshift/prism-camara-retrieval.yaml` - CAMARA retrieval Deployment (tcpSocket probe) + ClusterIP Service
- `backends/prism/Dockerfile` - Added `-m false` to CMD to disable multiprocess mode (fixes cluster.isPrimary crash)
- `backends/scripts/validate-mocks.sh` - Added Authorization Bearer header and spec-compliant request bodies for CAMARA POST endpoints

## Decisions Made

- **Internal registry used (no public fallback needed):** The OpenShift internal registry was accessible after enabling the default route via imageregistry operator patch. All 5 images pushed to `image-registry.openshift-image-registry.svc:5000/otel25-backends/prism-{api}:latest`. Plan 04 should use the same internal registry path.
- **Prism multiprocess disabled:** The `stoplight/prism:5` Docker image crashes on startup with `TypeError: Cannot read properties of undefined (reading 'isPrimary')` in `createMultiProcessPrism`. Adding `-m false` to the CMD disables Node.js cluster forking and resolves the crash. This flag should be carried forward to any future Prism deployments.
- **CAMARA request bodies required for Prism validation:** The CAMARA location verification spec requires `device` and `area` fields in the request body. Sending `{}` produces HTTP 422. The validation script was updated with spec-compliant request bodies.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Prism multiprocess mode crash in Docker**
- **Found during:** Task 2, Step 4 (image build/deploy)
- **Issue:** All 5 Prism pods crashed with `TypeError: Cannot read properties of undefined (reading 'isPrimary')` at `createMultiProcessPrism`. The Node.js `cluster` module's `isPrimary` property was undefined in the container environment.
- **Fix:** Added `-m false` flag to Dockerfile CMD to disable multiprocess forking
- **Files modified:** `backends/prism/Dockerfile`
- **Commit:** `8a1fae4`

**2. [Rule 1 - Bug] validate-mocks.sh CAMARA 401/422 errors**
- **Found during:** Task 2, Step 7 (validation)
- **Issue:** CAMARA verify endpoint returned 401 without auth token, and 422 with empty `{}` body (required fields missing per spec)
- **Fix:** Added `Authorization: Bearer mock-validation-token` header for POST endpoints and per-endpoint request bodies satisfying spec-required fields
- **Files modified:** `backends/scripts/validate-mocks.sh`
- **Commit:** `8a1fae4`

## Issues Encountered

- **Podman machine connection drops:** The Podman machine dropped its SSH connection mid-build session, requiring a `podman machine start` restart. This added ~30 seconds to the build cycle. Not a persistent issue.
- **Prism Docker image platform warning:** `WARNING: image platform (linux/amd64) does not match the expected platform (linux/arm64)` on Apple Silicon. This is cosmetic -- the amd64 image runs correctly on the OpenShift amd64 cluster nodes.

## Cluster Details

- **Cluster:** api.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com:6443
- **OpenShift version:** 4.20.39
- **Kubernetes version:** v1.33.13
- **User:** admin (cluster-admin)
- **Nodes:** 2 (1 control-plane+worker, 1 worker) in us-east-2
- **Registry:** Internal OpenShift registry via default-route-openshift-image-registry.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com
- **Registry auth:** Manual authfile with base64-encoded admin:token credentials (podman login basic auth was rejected; authfile approach worked)

## Self-Check: PASSED

- All 6 created files verified present on disk
- 2 modified files verified (Dockerfile, validate-mocks.sh)
- Task 2 commit `8a1fae4` found in git log
- 5 pods verified Running via `oc get pods` output
- validate-mocks.sh exits 0 with all 5 endpoints PASS

---
*Phase: 01-backend-infrastructure*
*Completed: 2026-10-02*
