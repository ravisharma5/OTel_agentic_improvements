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
- **D-04:** Use **Prism** (5.16.0) for mock backends, per ROADMAP.md/REQUIREMENTS.md and confirmed by prior research (`.planning/research/STACK.md` §"Why Prism over Microcks"). Microcks was raised and briefly selected mid-discussion for its native OpenShift Operator, but reverted after finding that the existing stack research already evaluated and rejected it for this use case: Microcks requires MongoDB + Keycloak + the Microcks server, which is unnecessary operational weight for lightweight, fast-startup, pipeline-internal mocks. Prism runs as a single stateless Node.js process per spec — no extra dependencies.
- **D-05:** Deploy **one Prism instance per API spec** — 4 separate Deployments/Services (`prism-tmf642`, `prism-tmf628`, `prism-tmf621`, `prism-camara`), each `prism mock -h 0.0.0.0 /specs/<spec>.yaml` on its own port (matches the layout already sketched in `.planning/research/ARCHITECTURE.md` and `STACK.md`). Not a single shared instance.
- **D-06:** Vendor the OpenAPI spec files into this repo (e.g. under `backends/specs/`) rather than fetching them at build/deploy time. Reproducible, pinned versions, no network dependency at deploy time. Mount into each Prism container via ConfigMap.
- **D-07:** TMF628's Swagger 2.0 spec is mocked as-is — no conversion to OAS 3.0 needed for mocking purposes (Prism natively supports both OAS 3.0 and Swagger 2.0). Conversion only becomes relevant later for OpenAPI-to-MCP tooling (Phase 2, FastMCP's `from_openapi()`).
- **D-08:** Mock responses should be **dynamically generated from the schema** (Prism's dynamic mode), not static hand-authored examples — more response variety for the downstream SDG pipeline. **Caveat carried from `.planning/research/PITFALLS.md` Pitfall 3:** dynamic mode on TMF's generic "characteristic pattern" schemas can produce syntactically valid but semantically meaningless data (random strings for alarm types, nonsense timestamps). PITFALLS.md's mitigation — enrich specs with realistic `example` values pulled from TMF user guides before Phase 4 SDG generation — is out of scope for Phase 1 itself but should be flagged to the Phase 4 planner.
- **D-09:** Verify mocks satisfy success criterion #1 ("valid HTTP responses matching their OpenAPI spec schemas") with an **automated schema validation script/test**. Where possible, prefer Prism's own **validation-proxy mode** (request/response validation against the spec) over a hand-rolled validator, per `.planning/research/FEATURES.md`. This should be a durable, repeatable artifact, not a manual spot-check.

### NextGCore / NWDAF
- **D-10:** Known risk (STATE.md / `.planning/research/PITFALLS.md` Pitfall #6 — NWDAF subscriptions are memory-only, container restarts silently drop them, possible identity-pinning issues in the OAuth2 overlay): NextGCore's NWDAF may be non-functional. Handle with a **timebox-then-fallback** strategy: attempt validation for a bounded effort, and if it doesn't work, fall back to mocking NWDAF via Prism (TS 29.520 spec) instead of blocking the phase on it.
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

### Stack & architecture research (MANDATORY — read before planning Phase 1; these directly govern Prism/NextGCore/routing decisions above)
- `.planning/research/STACK.md` §"Why Prism over Microcks", §"Why Prism over WireMock" — the tool-selection rationale D-04 is grounded in. Also has exact versions (Prism 5.16.0) and CLI usage.
- `.planning/research/ARCHITECTURE.md` §"Prism Mock Servers", §resource sizing tables, §deployment sequencing — per-API Prism instance layout, ConfigMap shape (`TMF642_BASE_URL` etc.), and the "don't embed backend URLs in tool code" anti-pattern that motivates D-15.
- `.planning/research/PITFALLS.md` Pitfall #3 (Prism unrealistic responses), Pitfall #6 (NextGCore NWDAF may be non-functional), Pitfall #4 (TMF628 Swagger 2.0 / FastMCP conversion), Pitfall #8 (SCTP/SCC sequencing) — all directly inform this phase's risk handling (D-08, D-10, D-12).
- `.planning/research/FEATURES.md` — Prism validation-proxy mode, error-simulation via `Prefer` header, health check requirements, three-tier backend verification model.
- `.planning/research/SUMMARY.md` — phase sequencing rationale ("Phase 1 first because Prism, vLLM, and OpenShift setup are zero-dependency").

### Project-level constraints
- `.planning/PROJECT.md` — "Constraints" section: OpenShift required, Red Hat tools preferred, Apache 2.0 for deliverables, Oct 15 2026 deadline.
- `.planning/REQUIREMENTS.md` — BACK-01, BACK-02, BACK-03 (this phase's requirements).
- `.planning/STATE.md` — "Blockers/Concerns": NextGCore NWDAF functional risk (Pitfall #6), TMF628 Swagger 2.0 format note (Pitfall #4).

No ADRs or SPEC.md exist for this phase yet.

</canonical_refs>

<code_context>
## Existing Code Insights

This is a greenfield repo — no existing infrastructure code, Kubernetes/OpenShift manifests, or backend services exist yet. There are no reusable assets, established patterns, or integration points to carry forward — Phase 1 planning starts from scratch.

**Correction:** the original scout only checked `OTel_2.5_MCP_and_Data_Landscape.md` and `gaps/gap-1-tool-calling/*.md`, and missed `.planning/research/*.md` (STACK.md, ARCHITECTURE.md, PITFALLS.md, FEATURES.md, SUMMARY.md) — pre-existing research produced during roadmap creation that already contains a resolved Prism-vs-Microcks decision, concrete resource-sizing tables, ConfigMap shape, and a per-Prism-instance architecture sketch for this exact phase. These are now added to Canonical References above and should be treated as the primary technical grounding for planning, not just background reading.

</code_context>

<specifics>
## Specific Ideas

- Use Prism (confirmed, not Microcks) — see D-04 correction above.
- Use Podman (not Docker) for local validation work, consistent with the "Red Hat tools preferred" constraint.
- Get nextgsim UE/PDU session simulation working in Phase 1 so NWDAF analytics data is realistic from day one, not deferred.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Per-tool routing granularity and a routing-proxy service were both considered and explicitly deferred as premature (no consumer exists yet), not because they're out of scope — future phases (2/3) may revisit if per-API granularity proves insufficient once real MCP servers exist.

</deferred>

---

*Phase: 1-Backend Infrastructure*
*Context gathered: 2026-09-27*
