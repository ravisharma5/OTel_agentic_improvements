---
phase: 04-sdg-pipeline-and-dataset-production
plan: 03
subsystem: backends
tags: [openapi, prism, tmf628, tmf642, tmf621, camara, spec-enrichment, mock-data]

# Dependency graph
requires:
  - phase: 01-backend-infrastructure
    provides: "Vendored OpenAPI spec files and Prism mock deployments"
provides:
  - "Enriched TMF628 spec with 135 schema-level example values for performance management"
  - "Enriched TMF642 spec with 70+ schema-level example values for alarm management"
  - "Enriched TMF621 spec with 40+ schema-level example values for trouble ticket management"
  - "Enriched CAMARA location verification and retrieval specs with GPS coordinates and device identifiers"
affects: [sdg-pipeline, prism-mocks, training-data-quality]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Schema-level example enrichment pattern for Prism dynamic mock generation"
    - "Preserving existing examples while adding new ones (additive-only edits)"

key-files:
  created: []
  modified:
    - "backends/specs/tmf628_performance_v4.0.0.swagger.json"
    - "backends/specs/tmf642_alarm_v5.0.1.oas.yaml"
    - "backends/specs/tmf621_troubleticket_v5.0.1.oas.yaml"
    - "backends/specs/camara_location_verification.yaml"
    - "backends/specs/camara_location_retrieval.yaml"

key-decisions:
  - "Preserved CAMARA verification Latitude/Longitude existing examples (50.735851/7.10066) instead of overwriting with plan-suggested values (51.5074/-0.1278) -- plan instruction to not modify existing examples takes precedence"
  - "Added examples to enum schemas (AlarmType, PerceivedSeverity, TroubleTicketStatusType) since Prism uses these for dynamic mock generation even though they are ref-only in parent schemas"
  - "Mapped plan's PerformanceMeasurementJob to actual schema name MeasurementCollectionJob; MeasureThresholdRuleViolation does not exist in TMF628 v4.0.0 spec"

patterns-established:
  - "Spec enrichment: add example values at schema property level for Prism consumption, not at response level"
  - "Enum schemas: add example value to enum type definitions so $ref consumers inherit realistic defaults"

requirements-completed: [SDG-01]

# Metrics
duration: 7min
completed: 2026-10-05
---

# Phase 4 Plan 03: Spec Enrichment Summary

**Enriched 5 vendored OpenAPI specs with 265+ realistic telecom example values (KPI names, alarm types, ticket priorities, GPS coordinates) so Prism mocks return domain-appropriate data instead of Lorem Ipsum**

## Performance

- **Duration:** 7 min
- **Started:** 2026-10-05T22:07:36Z
- **Completed:** 2026-10-05T22:14:45Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- TMF628 Performance Management spec enriched from 3 to 138 example keys across all major definitions (MeasurementCollectionJob, PerformanceIndicatorSpecification, OnDemandCollection, TrackingRecord, ScheduleDefinition, and 15+ supporting schemas)
- TMF642 Alarm Management spec enriched with 70+ examples including alarm types (environmentalAlarm), probable causes (rectifierLowVoltage), severity levels, timestamps, and crossed threshold information
- TMF621 Trouble Ticket spec enriched with 40+ examples including priorities (P1-Critical), ticket types (networkAlarm), severity levels, and status change tracking
- CAMARA Location specs enriched with GPS coordinates (NYC 40.7128/-74.0060 for retrieval), phone numbers, device identifiers, and accuracy values
- All existing example values preserved unchanged (additive-only edits verified)

## Task Commits

Each task was committed atomically:

1. **Task 1: Enrich TMF628 Performance Management spec** - `33393b9` (feat)
2. **Task 2: Enrich TMF642, TMF621, and CAMARA specs** - `ca570a2` (feat)

## Files Created/Modified
- `backends/specs/tmf628_performance_v4.0.0.swagger.json` - Added 135 examples across all definition schemas (was 3, now 138)
- `backends/specs/tmf642_alarm_v5.0.1.oas.yaml` - Added 70+ examples to Alarm, CrossedThresholdInformation, Comment, EntityRef, and enum schemas
- `backends/specs/tmf621_troubleticket_v5.0.1.oas.yaml` - Added 40+ examples to TroubleTicket, StatusChange, EntityRef, and enum schemas
- `backends/specs/camara_location_verification.yaml` - Added examples to PhoneNumber, MaxAge, VerificationResult, MatchRate, Port, Circle radius
- `backends/specs/camara_location_retrieval.yaml` - Added Latitude (40.7128), Longitude (-74.0060), PhoneNumber, LastLocationTime, Circle radius, Ellipse axes

## Decisions Made
- Preserved CAMARA verification spec's existing Latitude/Longitude examples (50.735851/7.10066) rather than overwriting with the plan's suggested London coordinates (51.5074/-0.1278). The plan's instruction "Do NOT modify existing example values" took precedence over the suggested coordinate values.
- Plan referenced "PerformanceMeasurementJob" and "MeasureThresholdRuleViolation" but the actual TMF628 v4.0.0 spec uses "MeasurementCollectionJob" and has no threshold violation schema. Enriched the actual schemas that exist.
- Added examples to enum type schemas (AlarmType, PerceivedSeverity, TroubleTicketStatusType) in addition to object property schemas, since Prism resolves $ref to these enum schemas and uses their example values for dynamic mock generation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added examples to enum schemas referenced via $ref**
- **Found during:** Task 2 (TMF642/TMF621 enrichment)
- **Issue:** Alarm.alarmType and Alarm.perceivedSeverity are $ref to AlarmType and PerceivedSeverity enum schemas -- adding examples to the Alarm properties alone would not work since $ref overrides inline properties in OpenAPI
- **Fix:** Added example values directly to the AlarmType enum schema ("environmentalAlarm"), PerceivedSeverity enum schema ("major"), and TroubleTicketStatusType enum schema ("inProgress")
- **Files modified:** backends/specs/tmf642_alarm_v5.0.1.oas.yaml, backends/specs/tmf621_troubleticket_v5.0.1.oas.yaml
- **Verification:** grep confirmed "example: environmentalAlarm" present; YAML validation passed
- **Committed in:** ca570a2 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Auto-fix was necessary for Prism to correctly use enum examples via $ref resolution. No scope creep.

## Issues Encountered
- Plan referenced schema names that differ from actual TMF628 v4.0.0 spec names ("PerformanceMeasurementJob" vs "MeasurementCollectionJob", "MeasureThresholdRuleViolation" does not exist). Resolved by mapping to actual schema names and enriching all available schemas comprehensively.
- CAMARA verification spec already had Latitude/Longitude examples (50.735851/7.10066 for Bonn, Germany). The plan's acceptance criteria expected 51.5074 (London) but the "do not modify existing examples" instruction was followed. Retrieval spec had no existing examples so received the plan's requested NYC coordinates (40.7128/-74.0060).

## User Setup Required
None - no external service configuration required. Redeploying Prism mocks with the enriched specs will automatically use the new example values.

## Next Phase Readiness
- All five vendored specs are enriched with realistic telecom example values
- Prism mock backends will return domain-appropriate data when redeployed with these specs (D-16 prerequisite satisfied)
- SDG pipeline can now generate training data against Prism mocks that return realistic KPI names, alarm types, ticket priorities, and GPS coordinates instead of Lorem Ipsum values

## Self-Check: PASSED

- [x] backends/specs/tmf628_performance_v4.0.0.swagger.json exists
- [x] backends/specs/tmf642_alarm_v5.0.1.oas.yaml exists
- [x] backends/specs/tmf621_troubleticket_v5.0.1.oas.yaml exists
- [x] backends/specs/camara_location_verification.yaml exists
- [x] backends/specs/camara_location_retrieval.yaml exists
- [x] Commit 33393b9 exists (Task 1)
- [x] Commit ca570a2 exists (Task 2)
- [x] All specs validate as valid JSON/YAML

---
*Phase: 04-sdg-pipeline-and-dataset-production*
*Completed: 2026-10-05*
