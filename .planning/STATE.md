---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 4 context gathered
last_updated: "2026-10-05T22:04:07.710Z"
last_activity: 2026-10-05 -- Phase 4 execution started
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 20
  completed_plans: 13
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-26)

**Core value:** OTel 2.5 can correctly call telecom tools (TMF, CAMARA, NWDAF) to complete fault prediction workflows -- measured by improvement on ZTE-AIM/TFCE benchmark over OTel 2.0.
**Current focus:** Phase 4 — SDG Pipeline and Dataset Production

## Current Position

Phase: 4 (SDG Pipeline and Dataset Production) — EXECUTING
Plan: 1 of 7
Status: Executing Phase 4
Last activity: 2026-10-05 -- Phase 4 execution started

Progress: [..........] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 13
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 4 | - | - |
| 2 | 3 | - | - |
| 3 | 6 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Horizontal layers structure -- backends, tooling foundation, domain tools, SDG pipeline, gaps doc
- [Roadmap]: Phase 5 (Industry Gaps) runs as parallel track with no dependencies on Phases 1-4
- [Roadmap]: Eval/baseline is out of scope -- Farbod's team owns it

### Pending Todos

None yet.

### Blockers/Concerns

- OSFT data format specification needed from Farbod's team in week 1 (Pitfall #5)
- NextGCore NWDAF may be non-functional -- needs hands-on validation in Phase 1 (Pitfall #6)
- TMF628 is Swagger 2.0 only -- FastMCP from_openapi() needs OAS 3.0 conversion path (Pitfall #4)
- NextGCore NWDAF on OpenShift returns HTTP 204 (empty, spec-correct) for NF_LOAD queries because nextgsim (the UE/gNB traffic simulator) was not deployed to the cluster -- only run locally via Podman during Plan 02's validation. Does not fail Phase 1's literal success criteria (204 is a valid response), but means the live OpenShift NWDAF has no real analytics data yet. Flagged by Phase 1 verification as a non-blocking follow-up: deploy nextgsim to otel25-backends (or otherwise drive UE/PDU traffic against the cluster) before Phase 4's SDG pipeline needs realistic NWDAF data.
- Prism mock responses confirmed unrealistic in practice (Pitfall #3) -- observed during Phase 1 execution: deployed NWDAF mock returned Lorem Ipsum `nsiId` values (e.g. "sunt sit", "dolor pariatur laboris proident") and nonsensical negative `loadLevelInformation` values (e.g. -60465668) for TS 29.520 LOAD_LEVEL_INFORMATION analytics. Confirmed this affects all Prism-backed mocks (TMF642, TMF628, TMF621, CAMARA verify, CAMARA retrieve), not just NWDAF. Scoped intentionally as Phase 4's job (enrich vendored OpenAPI specs with realistic `example` values from TM Forum user guides before SDG generation) per existing PITFALLS.md mitigation and CONTEXT.md D-08 -- not addressed in Phase 1, which only requires schema-valid (not realistic) mock responses. Phase 4 planner should treat this as a known, evidenced requirement rather than a hypothetical risk.
- MCP-Telecom (60+ device-layer tools, Phase 2) will be deployed with no network device backend configured -- by Phase 2 decision (02-CONTEXT.md D-07), its tools point at nothing and return connection errors when invoked. Phase 2 scaffolds the device-inventory config shape and a command-allowlist placeholder (D-10, D-10a) so the structure exists, but no real device data flows through MCP-Telecom until something wires real (or simulated) devices to it. Phase 4's SDG planner should treat "MCP-Telecom has no device backend" as a known, evidenced requirement to resolve before generating device-layer training examples, not a surprise discovered mid-pipeline.
- ~~FastMCP from_openapi()'s internal request dispatch may freeze the httpx client's base_url at tool-construction time~~ **RESOLVED by Phase 3 research (03-RESEARCH.md):** `OpenAPITool.run()` reads `self._client.base_url` fresh on every tool call (confirmed via FastMCP 4.0.11 source inspection + runtime test); `httpx2.AsyncClient.base_url` is a mutable property. BACK-03 compliance is confirmed for all 20 new domain servers.
- Phase 3 confirmed there is **no Prism mock for NWDAF** -- NWDAF_BASE_URL in `backends/openshift/configmap-backend-routing.yaml` has only ever pointed at live NextGCore (Phase 1 never stood up a Prism NWDAF instance; Prism only mocks TMF642/628/621 and CAMARA verify/retrieve). Phase 3's locked decision (03-CONTEXT.md D-11) treated "Prism verification" as the required baseline for all 20 tools with "live NextGCore" as a stretch goal for NWDAF specifically -- but since no Prism NWDAF mock exists, NWDAF's 3 tools only got MCP-protocol-level verification in Phase 3 (listed, respond with valid JSON-RPC), not semantic/backend-response verification. The one real semantic attempt (`get_nwdaf_analytics` against live NextGCore) failed with "illegal request line" -- NextGCore's NWDAF API serves HTTP/2 cleartext (h2c) but the httpx2 client sends HTTP/1.1. Phase 4's SDG planner should treat "NWDAF tools are protocol-verified only, not semantically verified against any backend" as a known, evidenced gap -- not a surprise discovered mid-pipeline. Fixing requires either an h2c-capable client (e.g. httpx2 with an HTTP/2 transport) or standing up a Prism NWDAF mock from the TS 29.520 spec.
- Phase 3's 5 new domain servers in `otel25-mcp` read a **copy** of the `backend-routing` ConfigMap (Kubernetes ConfigMap volumes are namespace-scoped, so it was copied from `otel25-backends`). The two copies are not synced -- to switch backends for ALL tools (MCP-Telecom + the 5 new domain servers), operators must patch BOTH `otel25-backends/backend-routing` AND `otel25-mcp/backend-routing`. The `otel25-mcp` copy carries an annotation documenting this. Phase 4 (switching NWDAF to live NextGCore, or re-pointing any Prism-backed tool) must patch both namespaces.
- RHCL's MCPVirtualServer controller (Technology Preview) writes virtual-server config secrets to a `mcp-system` namespace it expects to already exist (Phase 3 had to create it), but the gateway broker actually reads its config from `otel25-gateway/mcp-gateway-config` -- a different secret in a different namespace. Phase 3 manually merged the `virtualServers` section into the broker's config secret to work around this. **Risk:** if any `MCPServerRegistration` is re-reconciled later (e.g. Phase 4 adds/removes a backend), RHCL's controller may overwrite `otel25-gateway/mcp-gateway-config` from its own `mcp-system` copy, silently dropping the `virtualServers` section and breaking all 4 per-domain Virtual MCP Servers. Whoever touches `MCPServerRegistration` objects after Phase 3 must re-merge `virtualServers` into `otel25-gateway/mcp-gateway-config` afterward, or verify RHCL has fixed this in a later Tech Preview build.
- Phase 2's code review (02-REVIEW.md) found 3 confirmed security gaps in the vendored MCP-Telecom server (`mcp/mcp-telecom/src/mcp_telecom/`) that are dormant only because Phase 2 deliberately has no real device backend wired (D-07) -- they must be fixed before Phase 4 (or whichever phase first wires a real/simulated network device) exposes MCP-Telecom to actual device access: (1) **CR-01** -- `command_allowlist.yaml`'s documented "deny-by-default" guarantee is never enforced; `run_command`'s only real gate is an independent regex check in `safety.py` that has no knowledge of the allowlist file, and `tests/test_allowlist.py` tests a copy-pasted reimplementation rather than production code (this specific gap is observable today, since `validate_command()` runs before any device connection attempt). (2) **CR-02** -- `show_interface_detail`'s `interface` argument is formatted unsanitized into a vendor CLI template and sent over SSH with no call to `validate_command()`, a command-injection path requiring a live device connection to trigger. (3) **CR-03** -- `compare_configs`' `backup_file` argument is passed to `Path(...).read_text()` with no containment to the `backups/` directory, an arbitrary local file read requiring a live device connection to reach. User decision (2026-10-04): flag forward rather than fix now, since Phase 2 scope (D-07) means nothing reaches a real device yet. Whoever wires real devices (Phase 4 or a dedicated gap-closure phase) must treat these as an evidenced pre-requisite, not a surprise found mid-pipeline.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-10-05T19:36:51.391Z
Stopped at: Phase 4 context gathered
Resume file: .planning/phases/04-sdg-pipeline-and-dataset-production/04-CONTEXT.md
