# Phase 6: Domain Breadth Expansion - Research (Retroactive Audit)

**Researched:** 2026-10-12
**Domain:** Retroactive audit of already-shipped Phase 6 work (UDR + CAMARA Device Status MCP servers, gateway registration, curriculum scenarios) -- assessing correctness, completeness, and safety as a foundation for the upcoming SDG pipeline image rebuild
**Confidence:** HIGH

## Summary

Phase 6 is already fully shipped (3/3 plans executed, EXPAND-01/02/03 all marked Done, VERIFICATION.md shows 4/4 success criteria met after gap closure). This research is a skeptical, evidence-based audit conducted against the actual filesystem and git state -- not a forward-looking "how to build" investigation.

**Key conclusion: the shipped work is solid and safe to build on.** The UDR and CAMARA Device Status MCP servers are well-constructed, their gateway registrations are structurally correct (byte-identical to the NWDAF reference pattern modulo domain-specific names), all 9 new curriculum scenarios use tool names that match the gateway's confirmed-live tool list, and the IaC gap identified by the original verification (missing `mcp-udr-deployment.yaml` and ConfigMap keys) was correctly fixed in commit 39b2165. Two minor documentation inconsistencies were found (a stale comment in `mcp/udr/server.py` and a ConfigMap-watcher pattern mismatch between servers) -- neither is a functional issue or a pipeline-rebuild blocker.

**Primary recommendation:** Rebuild `sdg-pipeline:latest` from the current `sdg/` directory (`oc start-build --from-dir=.`) with no code changes needed, then run with `--no-cache` to bypass stale KFP cache. The pipeline code is already generic enough to handle the 9 new scenarios without modification.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXPAND-01 | Evaluate AMF, SMF, UDM/UDR as MCP server candidates; build the viable one | VERIFIED: AMF/SMF/UDM evaluated with distinct, documented non-viability reasons (loopback bind, NAS passthrough, NRF self-registration bug). UDR built with 1 tool (`get_authentication_subscription`), confirmed live against NextGCore with real 3GPP data. Server code, spec, Dockerfile, gateway registration all committed. [VERIFIED: git filesystem + VERIFICATION.md cross-check] |
| EXPAND-02 | Build a CAMARA Device Status MCP server (3 tools, Prism-mocked, verified E2E) | VERIFIED: `mcp/camara-device-status/server.py` has 3 `@mcp.tool()` functions (`get_roaming_status`, `get_reachability_status`, `get_connected_network_type`), each backed by a dedicated Prism instance. Full file set (server.py, 3 specs, 3 allowlists, Dockerfile, pyproject.toml, uv.lock) plus deployment manifest committed. [VERIFIED: git filesystem] |
| EXPAND-03 | Register both behind Kuadrant MCP Gateway + add matching curriculum scenarios | VERIFIED: 6 gateway files committed (httproute/mcpsr/mcpvs x 2 domains), structurally byte-identical to NWDAF reference. 9 new scenarios in seed-scenarios.yaml across 4 tiers, all tool_subset names confirmed matching live gateway tool names. [VERIFIED: git filesystem + programmatic cross-reference] |
</phase_requirements>

## Audit Findings

### Finding 1: IaC Gap Fix -- VERIFIED CORRECT

**Claim under test:** Commit 39b2165 fixed the VERIFICATION.md gap (UDR's deployment manifest and ConfigMap keys missing from git).

**Verdict: CONFIRMED.** [VERIFIED: git log + filesystem]

Evidence:
- `mcp/openshift/mcp-udr-deployment.yaml` exists (1435 bytes, committed Oct 11 23:28)
- `diff` against `mcp-camara-device-status-deployment.yaml` shows only domain-specific name substitutions -- structure byte-identical (Deployment+Service, image from internal registry, healthz probe on 8000, backend-routing ConfigMap volume mount)
- `backends/openshift/configmap-backend-routing.yaml` lines 97-104 contain `UDR_BASE_URL` and `UDR_PROTOCOL` with correct values (`http://udr.otel25-backends.svc.cluster.local:7777/nudr-dr/v2` and `h2c`)
- Commit message explicitly references the verification finding and describes fixing both the UDR gap and a related NWDAF_BASE_URL drift

### Finding 2: Server Code Quality -- SOLID

**UDR server (`mcp/udr/server.py`, 335 lines):** [VERIFIED: source inspection]
- Substantive `get_authentication_subscription` tool with real HTTP call construction via `_H2CClient` (drives `httpcore2` pool directly, correctly bypassing the httpx2/httpcore2 `.decode()` bug)
- Proper 404 handling (returns structured "not_found" JSON, does not raise)
- ConfigMap watcher uses SHA-256 content hashing (correct for K8s ConfigMap atomic symlink swaps)
- URL validation (rejects non-http/https URLs)
- Health endpoint at `/healthz`
- `h2>=4.1.0` declared in pyproject.toml (the dependency NWDAF was missing)

**CAMARA Device Status server (`mcp/camara-device-status/server.py`, 230 lines):** [VERIFIED: source inspection]
- 3 clean `@mcp.tool()` functions, each with dedicated ConfigMap-watched httpx2 client
- Generic `_make_backend()` factory avoids code duplication across 3 backends
- Bearer token hardcoded as `"prism-mock-token"` -- correct for Prism mocks, would need updating if ever pointed at a real operator sandbox (out of scope for v1)
- Health endpoint at `/healthz`

### Finding 3: Stale Comment in UDR server.py -- COSMETIC ONLY

**What:** Line 19 says "UDR_BASE_URL ConfigMap key, host:port only (no path component). The tool function appends the API-relative path in code."

**Reality:** The ConfigMap value IS `http://udr.otel25-backends.svc.cluster.local:7777/nudr-dr/v2` (includes the `/nudr-dr/v2` base path). This was intentionally changed during the path-base-mismatch fix documented in 06-03-PLAN.md, but the server.py header comment was not updated.

**Impact: NONE.** The code works correctly: `_H2CClient.get()` concatenates `self._base_url` + `path`, producing the correct full URL `http://....:7777/nudr-dr/v2/subscription-data/{supi}/authentication-data/authentication-subscription`. The stale comment is misleading to a future reader but has no functional effect.

**Recommendation:** Fix the comment in a future housekeeping pass. Not worth a standalone commit.

### Finding 4: ConfigMap Watcher Pattern Inconsistency -- NON-BLOCKING

**What:** UDR and NWDAF servers use SHA-256 content hashing for ConfigMap change detection. CAMARA Device Status and CAMARA Device Location servers use `st_mtime` polling.

**Why it matters (or doesn't):** The UDR server's own header comment explains: "Kubernetes ConfigMap volume updates are atomic symlink swaps, and st_mtime on the resolved file isn't reliably updated across every CRI/storage driver combination." This means the mtime-based servers *might* miss a ConfigMap hot-swap on certain storage drivers.

**Impact: MINIMAL.** This would only matter during a live backend URL change without pod restart, and pod restart would always pick it up. The CAMARA Device Status backends are Prism mocks unlikely to change URLs. Not a pipeline-rebuild blocker.

### Finding 5: Tool Name Cross-Reference -- ALL MATCH

**Method:** Programmatic cross-reference of every `tool_subset` entry across all 30 scenarios in `seed-scenarios.yaml` against every tool name in all 8 `gateway/openshift/mcpvs-*.yaml` files.

**Result:** All 16 unique tool names resolve. All 9 new scenario names present in the correct tiers. Zero mismatches. [VERIFIED: programmatic cross-reference against git-tracked files]

Specifically for the new tools:
| Scenario tool_subset name | Gateway MCPVirtualServer | Match |
|---|---|---|
| `udrget_authentication_subscription` | `mcpvs-udr.yaml` | YES |
| `devicestatusget_roaming_status` | `mcpvs-camara-device-status.yaml` | YES |
| `devicestatusget_reachability_status` | `mcpvs-camara-device-status.yaml` | YES |
| `devicestatusget_connected_network_type` | `mcpvs-camara-device-status.yaml` | YES |

### Finding 6: Gateway Registration Structure -- BYTE-IDENTICAL TO REFERENCE

**Method:** `diff` of each new gateway file against its NWDAF equivalent.

**Result:** Both UDR and CAMARA Device Status gateway triads (httproute/mcpsr/mcpvs) differ from the NWDAF reference only in domain-specific names, hostnames, prefixes, and tool lists. Structure is byte-identical. [VERIFIED: diff output]

### Finding 7: Curriculum Scenario Coherence -- WELL-FORMED

All 9 new scenarios reviewed for narrative coherence:

| Scenario | Tier | Tools | Assessment |
|---|---|---|---|
| `single_check_authentication_subscription` | single_tool | 1 (UDR) | Correct: single-tool baseline |
| `single_check_roaming_status` | single_tool | 1 (Device Status) | Correct: single-tool baseline |
| `single_check_reachability_status` | single_tool | 1 (Device Status) | Correct: single-tool baseline |
| `single_check_network_type` | single_tool | 1 (Device Status) | Correct: single-tool baseline |
| `parallel_roaming_and_location` | parallel | 2 (Device Status + CAMARA Location) | Coherent: both are independent device lookups |
| `sequential_analytics_to_auth_check` | sequential | 2 (NWDAF + UDR) | Coherent: anomaly detection -> identity verification |
| `sequential_alarm_to_roaming_check` | sequential | 2 (TMF642 + Device Status) | Coherent: alarm -> affected device status check |
| `closed_loop_device_connectivity_investigation` | closed_loop | 5 (TMF642 + 2x Device Status + NWDAF + TMF621) | Coherent: full connectivity complaint investigation |
| `closed_loop_device_security_anomaly_investigation` | closed_loop | 5 (TMF642 + UDR + CAMARA Location + Device Status + TMF621) | Coherent: suspicious-alarm identity verification workflow |

**No multi_turn scenarios were added for the new tools.** This was a documented, deliberate decision in 06-03-PLAN.md ("no multi_turn narrative felt as natural as the other tiers for these specific tools"). This is acceptable -- the existing 3 multi_turn scenarios provide sufficient training signal for multi-turn patterns, and the new tools are exercised across 3 other tiers.

## Pipeline Rebuild Risk Assessment

This section directly addresses the question: "Is there anything about these new tools/scenarios that could break or needs adjustment when rebuilding `sdg-pipeline:latest`?"

### Risk 1: Image Rebuild is the ONLY Required Step -- LOW RISK

The pipeline code (`run-generation.py`, `materialize_seeds.py`, `tool_coverage_report.py`) is already fully generic:

- `materialize_seeds.py` resolves tool names dynamically from the live gateway's `tools/list` response at runtime (no hardcoded tool names). It raises `ValueError` loudly if any `tool_subset` name doesn't match -- a deliberate fail-fast design. [VERIFIED: source inspection, lines 298-327]
- `run-generation.py`'s `sample_tools.num_samples` derives from `min(tool_list_sizes)` within each tier. Phase 6's new scenarios do NOT change any tier's minimum:
  - `single_tool`: still min=1 (new scenarios all have 1 tool)
  - `parallel`: still min=2 (new scenario has 2 tools)
  - `sequential`: still min=2 (new scenarios have 2 tools; the pre-existing min=2 from `sequential_perf_job_to_tracking`)
  - `closed_loop`: still min=5 (new scenarios have 5 tools, same as existing)
- `tool_coverage_report.py` reads `intended_tools` passthrough columns with no hardcoded assumptions about which tools exist. [VERIFIED: source inspection]

**Conclusion:** No code changes needed. The image rebuild (`oc start-build --from-dir=.`) to bake in the updated `sdg/config/seed-scenarios.yaml` is the only required step.

### Risk 2: KFP Cache Must Be Busted -- KNOWN, SOLVED

The `--no-cache` flag was added to `sdg_production_pipeline.py`'s `--submit` path during the 2026-10-12 session (documented in 04-LEARNINGS.md). Without it, KFP would reuse cached tier outputs from the old image's runs (cache keys don't include resolved image digest, only declared component inputs). [VERIFIED: 04-LEARNINGS.md 2026-10-12 entry]

**Action:** Use `--no-cache` on the first run after rebuild.

### Risk 3: Gateway Registrations Must Be Alive -- MEDIUM RISK

`materialize_seeds.py` resolves tool names against the live gateway at runtime. If the MCPServerRegistrations for `udr` or `camara-device-status` are not READY when the pipeline runs, their tool names won't appear in `tools/list`, and `materialize_seeds.py` will raise `ValueError` for every scenario referencing those tools (12 of the 30 total scenarios reference at least one new-domain tool). This is fail-fast by design, not silent corruption.

**Mitigation:** Before submitting the pipeline run, verify: `oc get mcpserverregistrations -A` shows both `udr` (READY=True, 1 tool) and `camara-device-status` (READY=True, 3 tools). If the cluster was redeployed, re-apply the 6 gateway files from `gateway/openshift/`.

### Risk 4: No Prism Mock for UDR -- KNOWN LIMITATION

UDR's backend is live NextGCore only. If NextGCore is down, the `udrget_authentication_subscription` tool will fail with a connection error. This would cause tool-coverage gate failures for the 4 scenarios using UDR (1 single_tool, 1 sequential, 2 closed_loop), but would NOT crash the pipeline -- failures are recorded in `coverage_failed.jsonl` and the pipeline continues with other tiers/scenarios.

This is a pre-existing, documented design choice (06-03-PLAN.md), not a new risk.

### Risk 5: NWDAF Interaction -- ALREADY FIXED

The NWDAF h2c fix (discovered while building UDR, backported to NWDAF) means `nwdafget_nwdaf_analytics` now works against live NextGCore for the first time. This is a positive change for the 2 new scenarios that include NWDAF (`sequential_analytics_to_auth_check`, `closed_loop_device_connectivity_investigation`), as well as all pre-existing NWDAF-using scenarios.

## PCF Verdict

06-01-PLAN.md's one-line verdict on PCF is correct and sufficient: PCF's binary is present and deployable, but it almost certainly hits the same NRF self-registration bug (`0.0.0.0` as advertised address) that blocks UDM's inter-NF communication. Not worth pursuing without first confirming NRF is fixed. This is correctly left alone. [VERIFIED: 06-01-PLAN.md cross-referenced against the NRF bug description]

## Things NOT Done That the Phase Goal Might Imply

| Item | Status | Assessment |
|---|---|---|
| Multi_turn scenarios for new tools | Not built | Deliberate, documented, acceptable |
| Prism mock for UDR | Not built | Deliberate -- UDR targets live NextGCore, not Prism |
| PCF evaluation | Verdict only | Correct -- blocked by NRF bug, documented |
| AUSF evaluation | Not mentioned | Not in requirements, correctly omitted |
| CAMARA Device Status subscription APIs | Not wrapped | Correct -- subscription/webhook APIs are event shapes, not tool-calling shapes (same reasoning as CAMARA Location) |

## Common Pitfalls

### Pitfall 1: Forgetting --no-cache on First Post-Rebuild Run
**What goes wrong:** KFP silently returns cached tier outputs from the old image, producing 0 rows for new scenarios.
**Why it happens:** KFP cache keys include declared component inputs (tier name, gateway URL, etc.) but NOT the resolved image digest.
**How to avoid:** Always use `--no-cache` on the first run after any image rebuild.
**Warning signs:** Run completes suspiciously fast (<2 minutes); `closed_loop_raw.jsonl` shows 0 rows for new scenarios.

### Pitfall 2: Stale MCPServerRegistrations After Cluster Rebuild
**What goes wrong:** `materialize_seeds.py` raises `ValueError` for scenarios referencing `udr*`/`devicestatus*` tools.
**Why it happens:** MCPServerRegistrations are cluster state, not automatically re-applied from git on cluster rebuild.
**How to avoid:** `oc get mcpserverregistrations -A` before submitting pipeline; re-apply from `gateway/openshift/` if needed.
**Warning signs:** `tools/list` returns fewer than ~83 tools (was 80 before Phase 6, should be 84 with UDR+Device Status).

### Pitfall 3: ConfigMap Namespace Drift
**What goes wrong:** Backend URLs in `otel25-mcp` namespace diverge from the canonical `otel25-backends` copy.
**Why it happens:** Two copies of the ConfigMap exist across namespaces; editing one doesn't auto-sync the other.
**How to avoid:** Always run `scripts/sync-backend-routing.sh` after any ConfigMap edit. The file's own header comment documents this contract.
**Warning signs:** UDR/NWDAF tools return connection errors or 404s despite the canonical ConfigMap looking correct.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (Python, pipeline-side) |
| Config file | None detected for Phase 6 specifically |
| Quick run command | `python -m pytest sdg/scripts/test_run_generation_coverage_gate.py -x` |
| Full suite command | `python -m pytest sdg/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXPAND-01 | UDR server returns real data for valid SUPI | integration (live cluster) | manual: `fastmcp.Client` against port-forwarded mcp-udr | N/A (live test) |
| EXPAND-02 | CAMARA Device Status 3 tools return Prism responses | integration (live cluster) | manual: `fastmcp.Client` against port-forwarded mcp-camara-device-status | N/A (live test) |
| EXPAND-03 | All 9 scenario tool names resolve against gateway | unit | `python -c "from sdg.scripts.materialize_seeds import ..."` (needs live gateway) | N/A (runtime validation) |

### Wave 0 Gaps
None -- Phase 6 is already complete. Validation was performed live during execution.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Gateway tools/list will return ~84 tools after cluster rebuild | Pipeline Rebuild Risk 3 | materialize_seeds.py will ValueError; fixable by re-applying gateway configs |
| A2 | NextGCore UDR endpoint still serves real data for `imsi-999700000000001` | Pipeline Rebuild Risk 4 | UDR scenarios produce connection errors in coverage_failed.jsonl; non-blocking |

## Open Questions

1. **Will the test subscriber still be provisioned after cluster lifecycle events?**
   - What we know: `imsi-999700000000001` was provisioned via `nextgcore-webui` into MongoDB. If MongoDB's PVC survives, the subscriber persists.
   - What's unclear: Whether sandbox cluster lifecycle (scale-down, rebuild) preserves the PVC.
   - Recommendation: If UDR's `get_authentication_subscription` returns 404 for the test SUPI during pipeline run, re-provision via `nextgcore-webui` using the procedure documented in 06-01-PLAN.md.

2. **Should the stale comment in UDR server.py be fixed before the pipeline rebuild?**
   - What we know: The comment is cosmetically wrong but functionally harmless.
   - Recommendation: Fix opportunistically if already touching the file; not worth a standalone change.

## Sources

### Primary (HIGH confidence)
- Git filesystem: `mcp/udr/server.py`, `mcp/camara-device-status/server.py`, all gateway YAML files, `backends/openshift/configmap-backend-routing.yaml`, `mcp/openshift/mcp-udr-deployment.yaml` -- direct source inspection
- Git log: commit 39b2165 stat and message -- confirms IaC gap fix
- `sdg/config/seed-scenarios.yaml` -- full 30-scenario curriculum, programmatic cross-reference against gateway MCPVirtualServer configs
- `sdg/scripts/materialize_seeds.py`, `run-generation.py`, `tool_coverage_report.py` -- pipeline code source inspection
- `.planning/phases/06-domain-breadth-expansion/VERIFICATION.md` -- prior verification findings and gap closure documentation
- `.planning/phases/04-sdg-pipeline-and-dataset-production/04-LEARNINGS.md` -- NWDAF h2c fix history, KFP caching behavior, pipeline image staleness discovery

### Secondary (MEDIUM confidence)
- 06-01/02/03-PLAN.md status updates -- execution documentation (cross-verified against filesystem state)

## Metadata

**Confidence breakdown:**
- IaC gap fix: HIGH -- verified against git log, filesystem, and diff
- Server code correctness: HIGH -- source inspection of both servers
- Tool name resolution: HIGH -- programmatic cross-reference, zero mismatches
- Pipeline rebuild compatibility: HIGH -- source inspection of all 3 pipeline scripts, tier size analysis
- Gateway registration: HIGH -- diff against reference pattern
- Scenario coherence: HIGH -- manual review of all 9 scenarios

**Research date:** 2026-10-12
**Valid until:** 2026-11-12 (stable -- infrastructure patterns, not fast-moving library ecosystem)
