# Phase 3: MCP Domain Servers and Gateway - Context

**Gathered:** 2026-10-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Build 20 curated fault-prediction MCP tools (TMF642 alarm mgmt x6, TMF628 performance x5, TMF621 trouble ticket x4, NWDAF TS 29.520 analytics x3, CAMARA Device Location x2) using Phase 2's conversion CLI, deploy them on OpenShift, and compose them plus MCP-Telecom (Phase 2's 58 device-layer tools) behind Red Hat Connectivity Link's MCP Gateway so an MCP client reaches everything through one endpoint. This phase does NOT run the SDG pipeline (Phase 4), does NOT wire MCP-Telecom to real network devices (still deferred per 02-CONTEXT.md D-07/D-09), and does NOT fix the three dormant security gaps in MCP-Telecom flagged forward from Phase 2's code review (CR-01/02/03 — still deferred to whichever phase wires real devices).

</domain>

<decisions>
## Implementation Decisions

### Gateway Product Identity
- **D-01:** The "Kuadrant MCP Gateway" named in ROADMAP.md/REQUIREMENTS.md (MCP-08) is **Red Hat Connectivity Link (RHCL) MCP Gateway** — a Technology Preview OpenShift Operator (OLM-installed), not a hand-rolled FastMCP `mount()` composition layer. Confirmed against official docs: `https://docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/install_the_mcp_gateway/` and `.../register_mcp_servers_and_create_policies/`. This corrects the original project research (`.planning/research/ARCHITECTURE.md`), which designed the gateway as a DIY FastMCP proxy/mount() server — that design predates the roadmap's RHCL decision and should be treated as superseded for the gateway component specifically (FastMCP mount() may still be relevant for whatever composes the 5 new domain servers' individual tool sets, a separate concern from gateway federation).
- **D-02:** Version: pin to **RHCL 1.4.1 or later** — the docs explicitly state 1.4.0 is deprecated due to known bugs (authentication failures, API key management errors, gateway instability, gateway pod memory pressure).
- **D-03:** RHCL's MCP Gateway is **Technology Preview** (no Red Hat production SLA) per its own docs. This is **accepted as-is** for this project — it's a WG training-data pipeline, not a production service. No fallback architecture is being pre-built; if it breaks during execution, that's an execution-time blocker to raise, not something Phase 3 plans around defensively.
- **D-04:** RHCL's Operator, Gateway API provider, and Istio-based data plane are **not yet installed** on the cluster. Provisioning this infrastructure (OLM Operator install, Gateway API, Service Mesh) is **in scope for Phase 3**, following the same pattern as Phase 1's cluster/CLI provisioning (01-CONTEXT.md D-01/D-02).

### Gateway Composition & Backend Registration
- **D-05:** MCP-Telecom (Phase 2's separately-deployed 58-tool server) **is registered as a backend** behind the same RHCL MCP Gateway, alongside the 5 new domain servers — all 78 tools reachable through one gateway endpoint, per the literal "single endpoint" success criterion.
- **D-06:** Backend registration uses RHCL's **`MCPServerRegistration` custom resource** (confirmed in `register_mcp_servers_and_create_policies` docs) — one per backend MCP server (5 new domain servers + MCP-Telecom = 6 registrations). Exact registration flow (in-cluster vs. the heavier "external MCP server" flow involving ServiceEntry/TLS/Secret) is a research question — the 6 backends are in-cluster services, which may use a simpler path than the external-server docs describe.
- **D-07:** Tool exposure uses **per-domain Virtual MCP Servers** (RHCL's `Virtual MCP Servers for curating tools and prompts` feature) — separate virtual servers per domain (TMF, NWDAF, CAMARA, infra/MCP-Telecom), not one single unified virtual server exposing all 78 tools as one flat list. Clients select which domain's tools they want. Exact tool-naming/collision-handling mechanics within this model are a research question (the docs reference "Virtual MCP server authorization and filtering" and "tool access revocation" without field-level detail fetched yet).
- **D-08:** Auth is **configured now**, not deferred — RHCL's MCP-gateway-specific `AuthPolicy` (confirmed distinct from generic Kuadrant AuthPolicy; docs reference dedicated "Configure MCP gateway authentication/authorization with an AuthPolicy" sections) should be set up in Phase 3. This closes the ClusterIP-only exposure gap flagged in Phase 2's threat model (02-02-PLAN.md T-02-01: "Phase 3 adds Kuadrant gateway with auth").

### Deployment Layout
- **D-09:** The 5 new domain MCP servers (TMF642/628/621, NWDAF, CAMARA) deploy into **`otel25-mcp`** — the same namespace as MCP-Telecom (Phase 2), continuing the namespace-per-layer pattern (02-CONTEXT.md D-17). Only the gateway itself (RHCL Gateway + MCPGatewayExtension resources) gets a **new, separate namespace**.
- **D-10:** Each domain server is built via Phase 2's conversion CLI (`mcp/tooling/openapi_to_mcp.py`), one server per API spec, hand-curated after generation — per 02-CONTEXT.md D-11/D-13 (one-time codegen then hand-curate, not a dynamic runtime loader). This phase is the CLI's first real production use beyond the CAMARA smoke test.
- **D-10a (amendment, 2026-10-04):** **Exemption for multi-spec domains.** NWDAF (2 specs: AnalyticsInfo + EventsSubscription → 3 tools) and CAMARA (2 specs: verify + retrieve → 2 tools) are exempt from D-10's CLI-generation step. These servers hand-write explicit `@mcp.tool()` functions directly instead of running the CLI and curating its output. Reason: merging multiple CLI-generated scaffolds for one logical domain server (via FastMCP `mount()`) collides with RHCL's own `MCPServerRegistration` tool-name prefixing, producing double-prefixed tool names (e.g. `nwdaf_analytics_nwdaf_get_analytics`). Hand-writing avoids this with no loss of fidelity, since both domains have small tool counts (2-3) where the CLI's main value — bulk operation filtering across large API surfaces — doesn't apply. TMF642/628/621 (single spec each, D-10's original CLI-then-curate flow) are unaffected.

### Verification
- **D-11:** Per-tool verification (success criterion #1: "individually callable and return valid responses from backends") runs against **Prism mocks for all 20 new tools** — matches Phase 1/2 precedent (schema-valid responses, not necessarily realistic; see 01-CONTEXT.md D-08 on Prism's known unrealistic-data caveat). Live NextGCore verification for the 3 NWDAF tools is a stretch goal, not a blocker — consistent with STATE.md's flagged nextgsim/traffic-generation gap (no realistic NWDAF data on the OpenShift cluster yet).

### Claude's Discretion
- Exact `MCPServerRegistration` and `MCPGatewayExtension` resource naming/field values, as long as they follow RHCL's documented schema.
- New gateway namespace name.
- Whether the in-cluster backend registration flow needs the full "external MCP server" steps (ServiceEntry, TLS, Secret) or a lighter in-cluster path — resolve during research/planning.
- Exact tool-naming scheme within each per-domain Virtual MCP Server.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Gateway product (MANDATORY — supersedes ARCHITECTURE.md's FastMCP-gateway design for the gateway component)
- `https://docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/install_the_mcp_gateway/` — RHCL MCP Gateway installation: OLM Operator install, Gateway object/listeners, `MCPGatewayExtension` CR, HTTPRoute auto-creation, DNS management, endpoint verification. Confirms Technology Preview status and the 1.4.0-deprecated / 1.4.1+ guidance (D-02, D-03).
- `https://docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/register_mcp_servers_and_create_policies/` — `MCPServerRegistration` CRD, Virtual MCP Servers (curation/filtering/authorization), MCP-gateway-specific `AuthPolicy` (authN + authZ), tool access revocation. Grounds D-05 through D-08. **Researcher must fetch full body content of this guide's subpages** (not just the TOC) before planning — field-level schema wasn't available during discussion.
- `https://docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/red_hat_connectivity_link/` — RHCL overview, for general product/version context.

### Stack & architecture research (read with the correction in D-01 in mind)
- `.planning/research/ARCHITECTURE.md` §"Pattern 1: Domain-Separated MCP Servers, Composed via Gateway" — the domain-separation rationale (keep each API family under 20 tools, avoid tool-count bloat) is still valid; **its specific FastMCP `mount()` gateway mechanics are superseded by D-01** for the gateway component itself.
- `.planning/research/STACK.md` — FastMCP version/compatibility matrix, still governs how the 5 domain servers themselves are built (via Phase 2's conversion CLI).
- `.planning/research/SUMMARY.md` §"MCP Gateway + Domain Servers" — critical-path framing (Phase 2 MCP Gateway gates Phase 4 SDG Pipeline) still applies; gateway *technology* choice is updated per D-01.

### Phase 1/2 contracts this phase must honor
- `.planning/phases/02-mcp-tooling-foundation/02-CONTEXT.md` — D-11 through D-16 (conversion CLI behavior, ConfigMap file-watch baked into every generated scaffold), D-17 (namespace-per-layer pattern extended by D-09 above), D-07/D-09 (MCP-Telecom has no device backend — still true in Phase 3).
- `.planning/phases/01-backend-infrastructure/01-CONTEXT.md` — D-08 (Prism unrealistic-data caveat informing D-11 above), D-15 (backend-routing ConfigMap contract every domain server must implement).
- `backends/openshift/configmap-backend-routing.yaml` — the ConfigMap contract each of the 5 new domain servers' generated scaffold must consume.
- `.planning/STATE.md` "Blockers/Concerns" — the **FastMCP `from_openapi()` base_url propagation risk** (unverified whether ConfigMap-driven backend-URL mutation actually reaches FastMCP-dispatched tool requests) is still open and MUST be validated by Phase 3's planner before relying on BACK-03 compliance for the 20 new servers (see 02-RESEARCH.md Open Question 1). Same section also carries forward the Phase 2 code-review security gaps (CR-01/02/03) as dormant-but-flagged, and the nextgsim/NWDAF-realism gap informing D-11 above.

### Project-level constraints
- `.planning/PROJECT.md` — "Constraints": OpenShift required, Red Hat tools preferred (RHCL satisfies this directly), Apache 2.0 for deliverables, Oct 15 2026 deadline.
- `.planning/REQUIREMENTS.md` — MCP-01 through MCP-05 (the 20 tools), MCP-08 (gateway composition with tool namespacing).
- `.planning/ROADMAP.md` — Phase 3 success criteria (3 criteria: 20 tools individually callable, gateway composes with namespacing presenting a single endpoint, correct backend response routing through the gateway).

No SPEC.md exists for this phase.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mcp/tooling/openapi_to_mcp.py` — Phase 2's conversion CLI, proven against a real spec (CAMARA) and a synthetic fixture; this phase runs it 5 times (once per API spec) to bootstrap each domain server's scaffold.
- `mcp/tooling/allowlist_schema.py` — YAML/JSON allowlist schema for operation selection (02-CONTEXT.md D-12); each domain server's spec needs its own allowlist config.
- `backends/openshift/configmap-backend-routing.yaml` — ConfigMap contract; generated scaffolds already bake in the file-watcher per 02-CONTEXT.md D-16.
- `mcp/mcp-telecom/` — vendored, patched MCP-Telecom, already deployed to `otel25-mcp` with Streamable HTTP transport; this phase registers its existing endpoint as an RHCL backend (D-05/D-06), no redeployment needed.
- `mcp/openshift/` — existing Phase 2 OpenShift manifests (namespace.yaml, mcp-telecom-deployment.yaml, mcp-telecom-secret.yaml) — the 5 new domain servers' manifests follow this same layout/style in the same namespace (D-09).

### Established Patterns
- Namespace-per-layer (`otel25-backends` Phase 1, `otel25-mcp` Phase 2) — extended with a dedicated gateway namespace for RHCL resources (D-09), not folded into `otel25-mcp`.
- Plain `oc apply` YAML manifests, no Helm (01-CONTEXT.md D-18, carried through Phase 2) — RHCL's own install docs use OLM Subscription/OperatorGroup CRs, which is a different (operator-install) mechanism layered on top of this pattern, not a replacement for it.
- One-time codegen then hand-curate for MCP servers (02-CONTEXT.md D-13) — applies to all 5 new domain servers.

### Integration Points
- The 5 new domain servers each mount `backends/openshift/configmap-backend-routing.yaml`'s ConfigMap (inherited scaffold behavior) to pick Prism mock vs. live backend per API.
- RHCL's `MCPServerRegistration` CRs point at the 6 backend MCP servers' in-cluster Services (5 new + MCP-Telecom), all already running in `otel25-mcp`.
- RHCL's per-domain Virtual MCP Servers are the integration point Phase 4's SDG pipeline will call against instead of hitting individual domain servers directly.

</code_context>

<specifics>
## Specific Ideas

- Gateway product is specifically Red Hat Connectivity Link's MCP Gateway (not generic/upstream Kuadrant, not a DIY FastMCP composition) — user supplied the exact docs URL confirming this.
- Per-domain Virtual MCP Servers (TMF, NWDAF, CAMARA, infra), not one flat unified tool list.
- Technology Preview status is a known, accepted constraint — not a blocker, no fallback plan being pre-built.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Wiring MCP-Telecom to real devices, fixing the Phase 2 code-review security gaps (CR-01/02/03), and running the SDG pipeline were all reaffirmed as later-phase work, not pulled forward.

</deferred>

---

*Phase: 3-MCP Domain Servers and Gateway*
*Context gathered: 2026-10-04*
