---
phase: 01-backend-infrastructure
plan: 01
subsystem: infra
tags: [openapi, prism, tmf642, tmf628, tmf621, camara, nwdaf, docker, bash]

# Dependency graph
requires: []
provides:
  - "7 vendored OpenAPI specs (TMF642, TMF628, TMF621, CAMARA verify/retrieval, NWDAF AnalyticsInfo/EventsSubscription)"
  - "Parameterized Prism Dockerfile with SPEC_FILE build arg"
  - "validate-mocks.sh with per-endpoint field validation for 5 Prism backends"
  - "verify-routing.sh with 6-key ConfigMap routing verification and switching contract test"
  - "check-nwdaf.sh with TS 29.520 analytics field assertions"
affects: [01-02, 01-03, 01-04]

# Tech tracking
tech-stack:
  added: [stoplight/prism:5 (Docker image)]
  patterns: [parameterized-dockerfile-build-arg, standalone-validation-script, configmap-routing-verification]

key-files:
  created:
    - backends/specs/tmf642_alarm_v5.0.1.oas.yaml
    - backends/specs/tmf628_performance_v4.0.0.swagger.json
    - backends/specs/tmf621_troubleticket_v5.0.1.oas.yaml
    - backends/specs/camara_location_verification.yaml
    - backends/specs/camara_location_retrieval.yaml
    - backends/specs/nwdaf_analyticsinfo_rel16.yaml
    - backends/specs/nwdaf_eventssubscription_rel16.yaml
    - backends/specs/SPEC_MANIFEST.md
    - backends/prism/Dockerfile
    - backends/scripts/validate-mocks.sh
    - backends/scripts/verify-routing.sh
    - backends/scripts/check-nwdaf.sh
  modified: []

key-decisions:
  - "TMF specs downloaded from main branch (no release tags exist); commit SHAs recorded in SPEC_MANIFEST.md for reproducibility"
  - "CAMARA specs pinned to r3.2 release tag; NWDAF specs pinned to Rel-16 frozen branch"
  - "Field validation in scripts uses soft warnings (not hard failures) since Prism dynamic mode may omit optional fields"

patterns-established:
  - "Parameterized Prism Dockerfile: FROM stoplight/prism:5 with ARG SPEC_FILE and COPY into /specs/api.yaml"
  - "Validation script pattern: three-level checks (HTTP status, JSON parse, spec-specific fields) with configurable env var URLs"
  - "SPEC_MANIFEST.md for tracking vendored spec provenance and pinning strategy"

requirements-completed: [BACK-01, BACK-02, BACK-03]

# Metrics
duration: 5min
completed: 2026-10-02
---

# Phase 1 Plan 01: Spec Vendoring and Validation Scripts Summary

**Vendored 7 OpenAPI specs (TMF642/628/621, CAMARA verify/retrieval, NWDAF) with parameterized Prism Dockerfile and 3 validation scripts with per-endpoint field assertions**

## Performance

- **Duration:** 5 min
- **Started:** 2026-10-02T14:34:04Z
- **Completed:** 2026-10-02T14:39:25Z
- **Tasks:** 2
- **Files created:** 12

## Accomplishments
- Vendored all 7 OpenAPI spec files from pinned sources (TMF from main with SHA tracking, CAMARA r3.2, NWDAF Rel-16)
- Created parameterized Prism Dockerfile that builds successfully (verified with podman build)
- Built validate-mocks.sh testing 5 endpoints with spec-derived field validation (id for TMF, verificationResult for CAMARA verify, lastLocationTime/area for CAMARA retrieval)
- Built verify-routing.sh with 6-key ConfigMap verification and switching contract demonstration
- Built check-nwdaf.sh with TS 29.520 analytics field assertions (nfLoadLevelInfos, sliceLoadLevelInfos, etc.)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create directory structure and vendor 7 OpenAPI spec files** - `0a1333b` (feat)
2. **Task 2: Create Prism Dockerfile and three validation scripts** - `1d43031` (feat)

## Files Created/Modified
- `backends/specs/tmf642_alarm_v5.0.1.oas.yaml` - TMF642 Alarm Management v5.0.1 OAS 3.0 spec
- `backends/specs/tmf628_performance_v4.0.0.swagger.json` - TMF628 Performance v4.0.0 Swagger 2.0 spec
- `backends/specs/tmf621_troubleticket_v5.0.1.oas.yaml` - TMF621 Trouble Ticket v5.0.1 OAS 3.0 spec
- `backends/specs/camara_location_verification.yaml` - CAMARA Device Location Verification r3.2 spec
- `backends/specs/camara_location_retrieval.yaml` - CAMARA Device Location Retrieval r3.2 spec
- `backends/specs/nwdaf_analyticsinfo_rel16.yaml` - NWDAF AnalyticsInfo Rel-16 spec
- `backends/specs/nwdaf_eventssubscription_rel16.yaml` - NWDAF EventsSubscription Rel-16 spec
- `backends/specs/SPEC_MANIFEST.md` - Download provenance and commit SHA tracking
- `backends/prism/Dockerfile` - Parameterized Prism mock image builder (FROM stoplight/prism:5)
- `backends/scripts/validate-mocks.sh` - 5-endpoint mock validation with field-level checks
- `backends/scripts/verify-routing.sh` - ConfigMap routing verification with switching contract
- `backends/scripts/check-nwdaf.sh` - NWDAF analytics smoke test with TS 29.520 field assertions

## Decisions Made
- TMF repos have no release tags matching spec versions (v5.0.1, v4.0.0). Downloaded from main branch and recorded commit SHAs in SPEC_MANIFEST.md per T-01-01 threat mitigation.
- Used parameterized Dockerfile with ARG SPEC_FILE rather than per-spec Dockerfiles, enabling a single image definition for all Prism instances.
- Field validation assertions use soft warnings (not hard failures) because Prism dynamic mode may omit optional fields. HTTP 2xx and valid JSON remain hard gates.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- TMF repos do not publish release tags matching their spec versions (tried v5.0.1 for TMF642, v4.0.0 for TMF628, v5.0.1 for TMF621 -- all returned 404). Fell back to main branch per plan's fallback strategy and recorded commit SHAs in SPEC_MANIFEST.md.
- Prism Docker image platform warning (linux/amd64 vs expected linux/arm64 on Apple Silicon) -- this is cosmetic for build verification and does not affect functionality.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 7 vendored specs ready for Prism deployment (01-03)
- Dockerfile verified with podman build -- ready for per-API image creation
- Validation scripts ready to run against deployed Prism pods
- Directory structure (backends/openshift/, backends/nextgcore/) ready for manifest creation

## Self-Check: PASSED

- All 12 created files verified present on disk
- Task 1 commit `0a1333b` found in git log
- Task 2 commit `1d43031` found in git log

---
*Phase: 01-backend-infrastructure*
*Completed: 2026-10-02*
