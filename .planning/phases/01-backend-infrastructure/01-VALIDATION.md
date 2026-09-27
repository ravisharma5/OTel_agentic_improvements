---
phase: 1
slug: backend-infrastructure
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Bash scripts (curl + jq) for HTTP validation — no test framework needed for infra-only phase |
| **Config file** | none — Wave 0 creates the scripts |
| **Quick run command** | `bash backends/scripts/validate-mocks.sh` |
| **Full suite command** | `bash backends/scripts/validate-mocks.sh && bash backends/scripts/verify-routing.sh && bash backends/scripts/check-nwdaf.sh` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `bash backends/scripts/validate-mocks.sh` (quick — curls the 4 Prism mock endpoints)
- **After every plan wave:** Run the full suite (validate-mocks + verify-routing + check-nwdaf)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-0X | 01-01 | 0 | BACK-01 | — | N/A | unit | `test -f backends/scripts/validate-mocks.sh` | ❌ W0 | ⬜ pending |
| 01-01-XX | 01-01 | 1 | BACK-01 | — | N/A | smoke + integration | `bash backends/scripts/validate-mocks.sh` | ❌ W0 | ⬜ pending |
| 01-0X-0X | TBD | 0 | BACK-03 | — | N/A | unit | `test -f backends/scripts/verify-routing.sh` | ❌ W0 | ⬜ pending |
| 01-0X-XX | TBD | 1/2 | BACK-03 | — | N/A | integration | `bash backends/scripts/verify-routing.sh` | ❌ W0 | ⬜ pending |
| 01-0X-0X | TBD | 0 | BACK-02 | — | N/A | unit | `test -f backends/scripts/check-nwdaf.sh` | ❌ W0 | ⬜ pending |
| 01-0X-XX | TBD | 2/3 | BACK-02 | — | N/A | smoke | `bash backends/scripts/check-nwdaf.sh` (or manual curl if NWDAF falls back to Prism per CONTEXT.md D-10) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Exact task IDs are placeholders — the planner assigns final plan/task numbering; this map's Req ID → script mapping is the durable contract.*

---

## Wave 0 Requirements

- [ ] `backends/scripts/validate-mocks.sh` — curls each of the 4 Prism mock endpoints (tmf642, tmf628, tmf621, camara) and validates the JSON response against its OpenAPI spec schema; covers BACK-01
- [ ] `backends/scripts/verify-routing.sh` — reads the per-API ConfigMap, calls the currently-configured backend, flips the ConfigMap value, confirms the call now hits the other backend without redeploy; covers BACK-03 (this is the CONTEXT.md D-16 test script)
- [ ] `backends/scripts/check-nwdaf.sh` — curls the NWDAF analytics endpoint (`GET /analytics?event-id=LOAD_LEVEL_INFORMATION`) and checks for a 200 with non-empty analytics payload; covers BACK-02. If NWDAF validation fails and falls back to Prism mocking (CONTEXT.md D-10), this script points at the Prism NWDAF mock instead and the fallback is noted in the script's output.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| NextGCore NWDAF returns realistic (non-default) analytics after nextgsim UE registration | BACK-02 | Realism of analytics values (vs. just HTTP 200) requires human judgment of whether ABNORMAL_BEHAVIOUR/LOAD_LEVEL_INFORMATION payloads look plausible, not just schema-valid | After running nextgsim to register a UE and establish a PDU session, curl the NWDAF analytics endpoint and manually inspect the response body for plausible (non-zero, non-placeholder) values |
| OpenShift cluster has sufficient resources and admin-level access (CONTEXT.md D-03) | BACK-02, BACK-03 | Cluster provisioning is an out-of-band human action (Red Hat Developer Sandbox was explicitly rejected in favor of a self-provisioned cluster), not something a script can create | `oc whoami --show-console` succeeds and `oc auth can-i create sccs` returns yes, before any deployment task begins |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — confirmed by gsd-plan-checker Dimension 8 pass across 01-01..01-04
- [x] Sampling continuity: no 3 consecutive tasks without automated verify — confirmed by gsd-plan-checker
- [x] Wave 0 covers all MISSING references — 01-01 creates validate-mocks.sh, verify-routing.sh, check-nwdaf.sh before any plan that depends on them
- [x] No watch-mode flags
- [ ] Feedback latency < 30s — to be confirmed once scripts run against real deployed backends (Wave 0/1 execution)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending — planning-time checks pass; final approval waits on Wave 0 script execution confirming actual runtime and `wave_0_complete: true`.
