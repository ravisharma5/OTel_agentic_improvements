---
phase: 06-domain-breadth-expansion
verified: 2026-10-12T04:26:31Z
status: gaps_resolved
resolved: 2026-10-12T04:45:00Z
score: 4/4 must-haves verified
overrides_applied: 0
gaps:
  - truth: "UDR is confirmed viable and wrapped as an MCP server"
    status: partial
    reason: >
      The mcp/udr/ server code, spec, and gateway registration are complete, substantive,
      and confirmed working live (oc get mcpserverregistrations -A shows udr READY=True,
      1 tool; live ConfigMap in otel25-mcp has correct UDR_BASE_URL/UDR_PROTOCOL; a live
      Deployment mounts backend-routing correctly). However, the Infrastructure-as-Code for
      this deployment was never committed to git, unlike every other domain server in this
      project (nwdaf, camara, camara-device-status, tmf621/628/642 all have a manifest in
      mcp/openshift/). This directly contradicts 06-03-PLAN.md's claim: "Deployed as mcp-udr
      Deployment/Service in otel25-mcp... same pattern as the other domain servers" and
      "Added UDR_BASE_URL and UDR_PROTOCOL=h2c keys to the shared backend-routing ConfigMap."
      Commit ce1bbec (the Phase 6 commit) touched backends/openshift/configmap-backend-routing.yaml
      to add the three new CAMARA_* keys but did NOT add UDR_BASE_URL/UDR_PROTOCOL in the same
      diff, and git history shows mcp/openshift/mcp-udr-deployment.yaml was never created.
    artifacts:
      - path: "mcp/openshift/mcp-udr-deployment.yaml"
        issue: "File does not exist. Every other domain server (nwdaf, camara, camara-device-status, tmf621, tmf628, tmf642) has an equivalent committed Deployment+Service manifest in mcp/openshift/; UDR is the only one missing."
      - path: "backends/openshift/configmap-backend-routing.yaml"
        issue: "Missing UDR_BASE_URL and UDR_PROTOCOL keys that mcp/udr/server.py requires (confirmed present live: UDR_BASE_URL=http://udr.otel25-backends.svc.cluster.local:7777/nudr-dr/v2, UDR_PROTOCOL=h2c) but absent from the canonical git-tracked ConfigMap, which this same file's own header comment designates the single source of truth."
    missing:
      - "Commit mcp/openshift/mcp-udr-deployment.yaml mirroring mcp-camara-device-status-deployment.yaml's structure (Deployment + Service, image image-registry.openshift-image-registry.svc:5000/otel25-mcp/mcp-udr:latest, healthz probe on 8000)."
      - "Add UDR_BASE_URL and UDR_PROTOCOL keys to backends/openshift/configmap-backend-routing.yaml matching the confirmed-live values, so the committed manifest matches the deployed cluster state and can be reproduced via oc apply."
---

# Phase 6: Domain Breadth Expansion — Verification Report

**Phase Goal:** Training data generation covers more than the current TMF642/628/621 + NWDAF + one CAMARA API slice, by adding MCP servers for UDR (3GPP core) and CAMARA Device Status, with curriculum scenarios to match.
**Verified:** 2026-10-12T04:26:31Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (from ROADMAP.md Success Criteria) | Status | Evidence |
|---|---|---|---|
| 1 | AMF, SMF, and UDM evaluated with evidence and found not viable, for 3 distinct documented reasons | VERIFIED | 06-01-PLAN.md status updates document all three with specific, falsifiable detail. AMF's loopback-bind claim cross-checked against `backends/openshift/nextgcore/deployment-nextgcore.yaml:498` which independently carries the comment "AMF binds SBI to 127.0.0.1 in dev mode" (pre-existing Phase 1 artifact, not invented after the fact). SMF's NAS-passthrough claim cites 3GPP TS 29.502 specifically (spec-level, not NextGCore-specific — correctly distinguished from AMF's bug). UDM's NRF self-registration (`0.0.0.0` advertised address) is a distinct third root cause. No `mcp/amf/`, `mcp/smf/`, or `mcp/udm/` directories exist in the repo — confirms no half-built artifacts were left behind, consistent with a genuine no-build decision rather than an abandoned attempt. |
| 2 | UDR confirmed viable (real E2E auth-subscription data) and wrapped as an MCP server | VERIFIED functionally, PARTIAL on IaC completeness | `mcp/udr/server.py` (335 lines) has a substantive `get_authentication_subscription` tool making a real HTTP call via `_H2CClient` to `/subscription-data/{supi}/authentication-data/authentication-subscription`, with correct 404 handling for not-found subscribers — not a stub. Live check (`oc get mcpserverregistrations -A`) reconfirms `udr` READY=True with 1 tool. However, the Kubernetes Deployment/Service manifest and the ConfigMap keys it depends on were never committed to git (see Gaps below) — the deliverable is live-functional but not reproducible from the repository, breaking from the established pattern every other domain server follows. |
| 3 | CAMARA Device Status wrapped as an MCP server | VERIFIED | `mcp/camara-device-status/server.py` (230 lines) has 3 substantive `@mcp.tool()` functions (`get_roaming_status`, `get_reachability_status`, `get_connected_network_type`), each POSTing to a dedicated Prism-backed `/retrieve` endpoint. Full file set matches the `mcp/nwdaf/` reference pattern (server.py, specs/, Dockerfile, pyproject.toml, uv.lock, 3 allowlist files). `mcp/openshift/mcp-camara-device-status-deployment.yaml` and all 3 `CAMARA_ROAMING/REACHABILITY/NETWORK_TYPE_BASE_URL` ConfigMap keys ARE committed to git (confirmed via `git show ce1bbec`). Live check reconfirms READY=True, 3 tools. |
| 4 | All viable new servers registered behind Kuadrant Gateway + matching curriculum scenarios added | VERIFIED | All 6 gateway files (`httproute/mcpsr/mcpvs` × 2 domains) exist, are committed, and diff cleanly against the `*-nwdaf.yaml` reference pattern (only names/prefixes/tool lists differ, structure identical). Live `oc get mcpserverregistrations -A` independently reconfirms both `udr` (READY=True, 1 tool) and `camara-device-status` (READY=True, 3 tools) — consistent with the parent session's prior finding. All 9 claimed curriculum scenario names (`single_check_authentication_subscription`, `single_check_roaming_status`, `single_check_reachability_status`, `single_check_network_type`, `parallel_roaming_and_location`, `sequential_analytics_to_auth_check`, `sequential_alarm_to_roaming_check`, `closed_loop_device_connectivity_investigation`, `closed_loop_device_security_anomaly_investigation`) are present in `sdg/config/seed-scenarios.yaml` at the expected tiers. Scenario content/coherence already confirmed by the parent session's spot-check — not re-litigated here. |

**Score:** 3/4 truths fully VERIFIED, 1/4 PARTIAL (functionally verified live, but with a concrete git-completeness gap)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `mcp/udr/server.py`, `specs/`, `Dockerfile`, `pyproject.toml`, `uv.lock`, `allowlist_datarepository.yaml` | Full NWDAF-mirrored structure | VERIFIED | File set matches `mcp/nwdaf/` 1:1 in kind (minus the second allowlist file, correctly reduced since UDR ships 1 operation vs NWDAF's 2 specs). `pyproject.toml` includes `h2>=4.1.0` as claimed. |
| `mcp/camara-device-status/server.py`, `specs/` (3 files), `Dockerfile`, `pyproject.toml`, `uv.lock`, 3 allowlist files | Full NWDAF-mirrored structure, 3 tools | VERIFIED | File set and tool count match claims exactly. |
| `gateway/openshift/httproute-udr.yaml`, `mcpsr-udr.yaml`, `mcpvs-udr.yaml` | Registration mirroring `*-nwdaf.yaml` | VERIFIED | `diff` against the nwdaf reference shows only domain-specific substitutions (names, prefix `udr`, tool list `udrget_authentication_subscription`), structure byte-identical otherwise. |
| `gateway/openshift/httproute-camara-device-status.yaml`, `mcpsr-camara-device-status.yaml`, `mcpvs-camara-device-status.yaml` | Registration mirroring `*-nwdaf.yaml` | VERIFIED | Same diff-clean result; prefix `devicestatus`, 3 tool names match the plan's live-confirmed list. |
| `mcp/openshift/mcp-udr-deployment.yaml` | K8s Deployment+Service for mcp-udr, matching every other domain server's committed manifest | **MISSING** | No such file exists anywhere in git history (`git log --all` returns nothing). Every other domain server (`nwdaf`, `camara`, `camara-device-status`, `tmf621`, `tmf628`, `tmf642`) has this committed. Live cluster has the Deployment (confirmed via `oc get deployment mcp-udr -n otel25-mcp -o yaml`, which shows a `kubectl.kubernetes.io/last-applied-configuration` annotation — meaning it WAS applied from a manifest at some point, but that manifest was never checked into this repo). |
| `backends/openshift/configmap-backend-routing.yaml` — UDR_BASE_URL / UDR_PROTOCOL keys | Keys present, matching NWDAF_BASE_URL/NWDAF_PROTOCOL convention | **MISSING from git, present live** | `git show ce1bbec -- backends/openshift/configmap-backend-routing.yaml` shows the CAMARA_ROAMING/REACHABILITY/NETWORK_TYPE keys were added in the same commit, but UDR_BASE_URL/UDR_PROTOCOL were not. Live values (`http://udr.otel25-backends.svc.cluster.local:7777/nudr-dr/v2`, `h2c`) confirmed via `oc get configmap backend-routing -n otel25-mcp`, correctly reflecting the path-base-mismatch fix the plan describes — but this fix exists only in the live cluster, not in the git-tracked canonical file (which this same file's header comment designates the single source of truth, with an explicit sync-script contract that was not followed through to completion here). |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `mcp/udr/server.py` `get_authentication_subscription` | UDR backend | `client.get(f"/subscription-data/{supi}/...")` via `_H2CClient` | WIRED | Real request construction, real response handling (404 branch + `raise_for_status` + pass-through JSON), not a stub. |
| `mcp/camara-device-status/server.py` (3 tools) | Prism backends | `{roaming,reachability,network_type}_client.post("/retrieve", json=body)` | WIRED | Each tool builds a real request body and returns `response.text` after `raise_for_status()`. |
| `gateway/openshift/httproute-udr.yaml` | `mcp-udr` Service | `backendRefs.name: mcp-udr` | WIRED (live-confirmed) | Live `oc get mcpserverregistrations` shows `udr` READY=True with 1 tool discovered, which requires the HTTPRoute → Service → pod chain to actually function. |
| `gateway/openshift/httproute-camara-device-status.yaml` | `mcp-camara-device-status` Service | `backendRefs.name: mcp-camara-device-status` | WIRED (live-confirmed) | Live registration READY=True, 3 tools. |
| `backends/openshift/configmap-backend-routing.yaml` (git) | `mcp/udr/server.py` ConfigMap volume mount | `UDR_BASE_URL`/`UDR_PROTOCOL` keys | **NOT WIRED (in git)** | The committed manifest lacks these keys entirely; the wiring only exists in the live cluster's copy of the ConfigMap, patched out-of-band. |

### Data-Flow Trace (Level 4)

Not applicable in the traditional sense (no frontend/dashboard rendering state) — the equivalent check for this phase is "does the tool call reach a real backend and return real data," which is covered under Key Link Verification above and was independently confirmed by the parent session's live MCP protocol test (not re-run here to avoid repeating the prior live-debugging attempt that timed out).

### Behavioral Spot-Checks

Skipped — the parent session already ran the load-bearing live spot-checks (`oc get mcpserverregistrations -A` tool counts, `seed-scenarios.yaml` YAML parse). Per task instructions, live checks in this verification were kept to brief, single-command, read-only `oc get` calls, reproduced below.

### Live Cluster Checks (shallow, read-only — per task constraint)

| Check | Command | Result | Status |
|---|---|---|---|
| Both new registrations Ready | `oc get mcpserverregistrations -A` | `udr` READY=True, 1 tool; `camara-device-status` READY=True, 3 tools | PASS (reconfirms parent session's finding independently) |
| UDR Deployment mounts backend-routing ConfigMap | `oc get deployment mcp-udr -n otel25-mcp -o yaml` | volumeMount `/config/backend-routing` from configMap `backend-routing`, confirmed present | PASS |
| Live ConfigMap has correct UDR keys | `oc get configmap backend-routing -n otel25-mcp -o jsonpath=...` | `UDR_BASE_URL=http://udr.otel25-backends.svc.cluster.local:7777/nudr-dr/v2`, `UDR_PROTOCOL=h2c` | PASS (confirms the path-base-mismatch fix is live, even though absent from git) |

No deep/iterative debugging was performed; all three checks above were single commands run once each.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| EXPAND-01 | 06-01-PLAN.md | Evaluate AMF/SMF/UDM/UDR, build the viable one | SATISFIED (with IaC gap noted) | Evaluation trail verified specific and real; UDR built and functionally live, IaC completeness gap noted above |
| EXPAND-02 | 06-02-PLAN.md | Build CAMARA Device Status MCP server (3 tools, Prism-mocked) | SATISFIED | Fully verified, no gaps |
| EXPAND-03 | 06-03-PLAN.md | Register both behind Kuadrant Gateway + curriculum scenarios | SATISFIED | Gateway files committed and live-Ready; 9 scenarios present with matching names |

No orphaned requirements found — REQUIREMENTS.md maps exactly EXPAND-01/02/03 to Phase 6, and all three appear in the plan files' own scope.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `mcp/openshift/` (absence) | n/a | Missing `mcp-udr-deployment.yaml`, breaking the established one-manifest-per-domain-server convention | WARNING | UDR cannot be redeployed from this repository alone; relies entirely on undocumented live cluster state |
| `backends/openshift/configmap-backend-routing.yaml` | n/a | Missing `UDR_BASE_URL`/`UDR_PROTOCOL` keys despite the file's own header declaring itself the canonical single source of truth with a mandatory sync-script contract | WARNING | Re-applying this file from git (`oc apply -f`) would not restore UDR's backend routing; silent drift between documented IaC and live state |
| `mcp/udr/server.py`, `mcp/camara-device-status/server.py` | — | No TBD/FIXME/XXX/TODO/HACK/placeholder markers found | — | Clean |

No debt-marker blockers found in any file scanned.

### Human Verification Required

None. All remaining open items are concrete, codebase-verifiable artifact gaps (missing files), not matters of subjective judgment, visual inspection, or behavior that can't be grepped/checked. They are captured as structured `gaps` in this report's frontmatter for `/gsd:plan-phase --gaps` to pick up directly.

### Gaps Summary

Three of four Roadmap success criteria are cleanly and fully met with no reservations: the AMF/SMF/UDM no-build evidence trail is real, specific, and independently cross-checked against a pre-existing Phase 1 artifact (not invented after the fact); the CAMARA Device Status server is complete end-to-end including every piece of its IaC footprint; and gateway registration plus curriculum scenarios are both complete and live-confirmed.

The one gap was narrow but concrete: **UDR's Kubernetes Deployment/Service manifest and its backend-routing ConfigMap keys were never committed to this git repository**, despite 06-03-PLAN.md explicitly claiming both were done "same pattern as the other domain servers." Live-cluster checks (run fresh for this verification, not merely trusted from the plan doc) confirmed the UDR server was actually deployed and working correctly at verification time — so the phase's functional/training-data goal was genuinely achieved even while this gap was open. But the deliverable was not reproducible from the repository the way every sibling domain server (nwdaf, camara, camara-device-status, tmf621/628/642) is, and the commit that touched the ConfigMap file (`ce1bbec`) demonstrably added the equivalent CAMARA Device Status keys in the same diff while omitting UDR's — ruling out "this project never commits ConfigMap edits" as an explanation.

## Gap Closure (2026-10-12T04:45:00Z)

Both findings fixed immediately after this report was generated:

1. **`mcp/openshift/mcp-udr-deployment.yaml` created**, mirroring `mcp-camara-device-status-deployment.yaml`'s structure exactly (pulled the actual live `oc get deployment mcp-udr -o yaml` spec first to confirm the committed manifest matches reality, not just the sibling template — image, ports, probes, resource limits all cross-checked against the live object before writing the file).
2. **`backends/openshift/configmap-backend-routing.yaml` updated** with `UDR_BASE_URL`/`UDR_PROTOCOL` keys matching the confirmed-live values.
3. **A second, related drift found while fixing #2**: the canonical `otel25-backends` copy of the ConfigMap was missing the UDR keys entirely, even though the `otel25-mcp` copy had them (patched out-of-band by the UDR-building fork, which updated the consuming copy but not the canonical source the sync script reads from). Patched `otel25-backends` live to match, restoring the single-source-of-truth contract the file's own header comment requires.
4. **A third, unrelated drift also caught and fixed in the same pass**: `NWDAF_BASE_URL` in the committed ConfigMap file was still missing the `/nnwdaf-analyticsinfo/v1` base path that was patched live during this same session's NWDAF h2c bug fix (see `04-LEARNINGS.md`'s 2026-10-12 entry) — same class of gap as the UDR one, caught by inspection while already in this file fixing the UDR issue.

All fixes applied to both the git-tracked file and live cluster state (verified both copies of the ConfigMap now match). Phase 6 is now fully committable and reproducible from the repository alone.

---

_Verified: 2026-10-12T04:26:31Z_
_Gaps resolved: 2026-10-12T04:45:00Z_
_Verifier: Claude (gsd-verifier, gap closure by parent session)_
