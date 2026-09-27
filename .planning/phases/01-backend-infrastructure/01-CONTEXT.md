# Phase 1: Backend Infrastructure - Context

**Gathered:** 2026-09-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Deploy mock and live backends on OpenShift so every fault-prediction API (TMF642, TMF628, TMF621, CAMARA DeviceLocation, NWDAF) has something real to respond to tool calls — with a routing mechanism to switch each API between mock and live without redeploying. This phase does NOT build any MCP tools or servers (that's Phase 2/3) and does NOT run the SDG pipeline (Phase 4). It produces the backend layer those later phases will call.

</domain>

<decisions>
## Implementation Decisions

### OpenShift Cluster & Access
- **D-01:** Deploy to a personal/dev OpenShift cluster, not a shared team or WG cluster.
- **D-02:** `oc` CLI access is not yet set up — provisioning the cluster/login is in scope for Phase 1 setup work.
- **D-03:** User will provision a cluster with sufficient resources and admin-level access (not the free, quota-constrained Red Hat Developer Sandbox tier). This means SCC/quota limits are NOT expected to block NextGCore's deployment needs (custom SCCs, SCTP support).

### Mock Backend Tooling
- **D-04:** Use **Microcks** instead of Prism for mock backends. Rationale: Microcks is a CNCF project (Apache 2.0) with a native OpenShift Operator, which better fits the project's "Red Hat tools and platforms preferred" constraint than a raw Prism container. Everywhere ROADMAP.md/REQUIREMENTS.md say "Prism," read "Microcks" — this supersedes that text as an implementation choice, not a scope change (BACK-01 is still satisfied: mock backends for TMF642/628/621/CAMARA from their OpenAPI specs).
- **D-05:** Deploy a **single Microcks instance** (via its OpenShift Operator), with all 4 specs (TMF642, TMF628, TMF621, CAMARA DeviceLocation) imported as separate services within it — not 4 separate instances. This matches Microcks' intended usage model.
- **D-06:** Vendor the OpenAPI spec files into this repo (e.g. under `backends/specs/`) rather than fetching them at build/deploy time. Reproducible, pinned versions, no network dependency at deploy time.
- **D-07:** TMF628's Swagger 2.0 spec is mocked as-is — no conversion to OAS 3.0 needed for mocking purposes (Microcks/Prism-class tools handle Swagger 2.0 natively). Conversion only becomes relevant later for OpenAPI-to-MCP tooling (Phase 2).
- **D-08:** Mock responses should be **dynamically generated from the schema** (not static hand-authored examples) — this produces more response variety, which better serves the downstream SDG pipeline's need for diverse training examples.
- **D-09:** Verify mocks satisfy success criterion #1 ("valid HTTP responses matching their OpenAPI spec schemas") with an **automated schema validation script/test** that hits each mocked endpoint and validates the response against the spec's JSON schema — not a manual spot-check. This should be a durable, repeatable artifact.

### NextGCore / NWDAF
- **D-10:** Known risk (STATE.md): NextGCore's NWDAF may be non-functional. Handle with a **timebox-then-fallback** strategy: attempt validation for a bounded effort, and if it doesn't work, fall back to mocking NWDAF via Microcks (TS 29.520 spec) instead of blocking the phase on it.
- **D-11:** The specific timebox duration is left to the executing agent's judgment during execution — not locked to a specific number of days now.
- **D-12:** Validation sequence: validate NextGCore locally with **Podman** first (not Docker — consistent with Red Hat tooling preference), confirm NWDAF analytics endpoints actually respond, and only then invest effort adapting NextGCore's `k8s/` manifests for OpenShift (SCCs, SCTP). Don't spend OpenShift-adaptation effort before proving the NF works at all.
- **D-13:** Set up **nextgsim** (UE registration + PDU session establishment) as part of Phase 1, not deferred to Phase 4. The user wants NWDAF to return realistic (non-empty/non-default) analytics data from the start, not just prove the endpoint is reachable.

### Backend Routing Design
- **D-14:** Routing granularity is **per-API** (tmf642, tmf628, tmf621, camara_devicelocation, nwdaf) — not per individual tool. Per-tool granularity has no consumer yet since the 20 individual MCP tools don't exist until Phase 3.
- **D-15:** The routing mechanism is a **plain Kubernetes ConfigMap** holding a mock/live base URL per API. Future Phase 2/3 MCP servers will read it directly (env var or mounted file) to pick which backend to call. Phase 1 does **not** build a routing proxy/gateway service — that would be infra built without a real consumer to validate against.
- **D-16:** To verify success criterion #3 (routing switches without redeploy) without any real MCP server existing yet, build a **small throwaway test script** that reads the ConfigMap, calls the currently-configured backend, flips the ConfigMap value, and confirms the same script now hits the other backend — proving the contract works ahead of Phase 2/3.

### Claude's Discretion
- Exact timebox duration for NextGCore/NWDAF validation before falling back to mocking (D-11).
- Naming conventions for the OpenShift namespace/project, ConfigMap keys, and vendored spec directory structure.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Domain & tooling landscape
- `OTel_2.5_MCP_and_Data_Landscape.md` — full landscape of MCP toolkits, SDG methodology, eval benchmarks, and sandbox environment comparison (includes the OpenShift-readiness table for fenar/cnvopen5gcore, NextGCore, Open5GS, Free5GC).
- `gaps/gap-1-tool-calling/mcp_toolkit_audit.md` — audit of existing MCP toolkits (MCP-Telecom, mcp-camara-demo) and what's missing for fault prediction.
- `gaps/gap-1-tool-calling/fault_prediction_api_map.md` — API-by-API map of TMF642/628/621, NWDAF, and CAMARA operations needed for fault prediction, including the backend-per-API table (§"Backend for execution-verified SDG") and OpenAPI spec source URLs (§"OpenAPI spec sources").

### Project-level constraints
- `.planning/PROJECT.md` — "Constraints" section: OpenShift required, Red Hat tools preferred, Apache 2.0 for deliverables, Oct 15 2026 deadline.
- `.planning/REQUIREMENTS.md` — BACK-01, BACK-02, BACK-03 (this phase's requirements).
- `.planning/STATE.md` — "Blockers/Concerns": NextGCore NWDAF functional risk (Pitfall #6), TMF628 Swagger 2.0 format note (Pitfall #4).

No ADRs or SPEC.md exist for this phase yet.

</canonical_refs>

<code_context>
## Existing Code Insights

This is a greenfield repo — no existing infrastructure code, Kubernetes/OpenShift manifests, or backend services exist yet. `scout_codebase` found only planning/research markdown files (`OTel_2.5_MCP_and_Data_Landscape.md`, `gaps/gap-1-tool-calling/*.md`). There are no reusable assets, established patterns, or integration points to carry forward — Phase 1 planning starts from scratch.

</code_context>

<specifics>
## Specific Ideas

- Use Microcks (not Prism) specifically because of its native OpenShift Operator — a direct fit for the "Red Hat tools and platforms preferred" project constraint.
- Use Podman (not Docker) for local validation work, same rationale.
- Get nextgsim UE/PDU session simulation working in Phase 1 so NWDAF analytics data is realistic from day one, not deferred.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Per-tool routing granularity and a routing-proxy service were both considered and explicitly deferred as premature (no consumer exists yet), not because they're out of scope — future phases (2/3) may revisit if per-API granularity proves insufficient once real MCP servers exist.

</deferred>

---

*Phase: 1-Backend Infrastructure*
*Context gathered: 2026-09-27*
