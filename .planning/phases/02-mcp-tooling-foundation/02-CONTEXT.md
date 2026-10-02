# Phase 2: MCP Tooling Foundation - Context

**Gathered:** 2026-10-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Build reusable OpenAPI-to-MCP conversion tooling and deploy MCP-Telecom's 60+ device-layer tools on OpenShift, so Phase 3 has both a proven conversion workflow and a working device-layer toolkit to build the 20 fault-prediction tools and the gateway composition on top of. This phase does NOT build the 20 curated TMF/NWDAF/CAMARA domain tools themselves (Phase 3), does NOT compose anything behind the Kuadrant MCP Gateway (Phase 3), and does NOT wire MCP-Telecom to real network devices (deferred — see D-06, D-13).

</domain>

<decisions>
## Implementation Decisions

### MCP-Telecom Transport
- **D-01:** MCP-Telecom ships stdio-only. We will **fork/patch it to add native HTTP transport** rather than front it with a stdio-to-HTTP proxy sidecar or stay stdio-only and defer bridging. MCP-Telecom is already built on FastMCP (same framework this project already uses for its own tools), so the patch is expected to be a small entrypoint/config change (FastMCP has native HTTP transport support), not a deep fork — confirmed with the user, who still wants it treated as a proper vendored+patched copy rather than a thin dependency wrapper.
- **D-02:** The patched server is **HTTP-only** — stdio support is stripped, not kept as a dual-mode toggle.
- **D-03:** The HTTP transport is **Streamable HTTP** (the current MCP 2026-07-28 protocol transport), not legacy SSE — matches FastMCP 4.x's native support and what Phase 3's Kuadrant gateway will expect.
- **D-04:** Service/port naming for the deployed MCP-Telecom is left to **Claude's discretion** (see below), consistent with whatever namespace comes out of D-09.

### MCP-Telecom Vendoring & Licensing
- **D-05:** The patched MCP-Telecom source is **vendored into this repo** (not a separate GitHub fork, not an upstream PR) — consistent with Phase 1's vendoring precedent (01-CONTEXT.md D-06: vendor OpenAPI specs rather than fetch at deploy time).
- **D-06:** The vendored copy **keeps its original MIT license**, isolated in its own directory (`mcp/mcp-telecom/` — see D-11), with a NOTICE/attribution file crediting the upstream project (github.com/Avinash-Amudala/MCP-Telecom). PROJECT.md's "Apache 2.0 for deliverables" constraint applies to code we author ourselves (e.g. the conversion CLI); MIT and Apache 2.0 can coexist per-subtree in one repo.

### MCP-Telecom Backend Data Source
- **D-07:** MCP-Telecom's tools (BGP, interfaces, syslog, safe CLI exec, config backup, etc.) will **point at nothing** for Phase 2 — no network device simulator is stood up. Tools are deployed and individually callable; invoking them against a real device target returns connection errors. This satisfies the literal Phase 2 success criterion (deployed + individually callable) and defers the realistic-device-data problem to whichever later phase actually needs it.
- **D-08:** Verification that tools are "individually callable via MCP protocol" is done with a **throwaway script that calls `tools/list` and invokes one representative tool** (not just `tools/list` alone) — proves the full MCP protocol round-trip (transport + deployment), not device functionality. Mirrors Phase 1's D-16 `verify-routing.sh` pattern.
- **D-09:** This gap (MCP-Telecom has no device backend) **must be flagged forward in STATE.md** as a Blocker/Concern for the Phase 4 SDG planner, the same way Phase 1 flagged the Prism realism issue (01-CONTEXT.md D-08) — not left implicit.
- **D-10:** Phase 2 **scaffolds the device-inventory config shape now** (e.g. `devices.yaml` or equivalent) with placeholder/empty entries, so Phase 4 only needs to fill in real device targets rather than invent the structure. Credential fields in this scaffold are represented as **OpenShift Secret references** (env var or mounted file), with the Secret itself left empty/placeholder — credentials never land in plain ConfigMaps or git.
- **D-10a:** MCP-Telecom's "safe CLI command execution" tool gets a **command-allowlisting scaffold now** too (config-driven, empty/permissive placeholder), added alongside the device-inventory scaffold from D-10 — the safety mechanism should exist structurally before any real device is wired in Phase 4, not be designed from scratch at that point.

### Conversion Tooling (MCP-07)
- **D-11:** The "reusable OpenAPI-to-MCP conversion tooling" is a **generic CLI/script** (e.g. `mcp/tooling/openapi_to_mcp.py`) — not a shared library Phase 3 imports inline, and not just a documented pattern. Phase 3 invokes it once per API spec (TMF642, TMF628, TMF621, NWDAF, CAMARA) to bootstrap each domain server.
- **D-12:** Operation selection (choosing specific operations instead of exposing the entire API surface) is expressed via a **YAML/JSON allowlist config** listing operationIds/tags, which the CLI applies through FastMCP's `RouteMap` — not CLI flags.
- **D-13:** The CLI's generation mode is **one-time codegen, then hand-curate**: it writes a `server.py` scaffold once, which Phase 3 then hand-edits directly (per STACK.md's documented workflow: auto-convert with `from_openapi()` → manually curate descriptions/names/params → test). This is NOT a dynamic runtime loader that re-reads the spec on every server startup.
- **D-14:** Phase 2 **smoke-tests the CLI against a real spec** — CAMARA Device Location (the smallest real spec, 2 operations) — confirming it produces a working FastMCP server that starts and lists its tools correctly. This is not deferred to Phase 3 as the first real usage.
- **D-15:** The CAMARA smoke-test server is run **locally only, not deployed to OpenShift**. Phase 3 deploys the real curated CAMARA server for real; Phase 2 doesn't build throwaway OpenShift manifests just for the smoke test.
- **D-16:** Every scaffold the CLI generates **bakes in file-watching boilerplate** for Phase 1's backend-routing ConfigMap contract (01-CONTEXT.md D-15: volume-mounted ConfigMap, file-watch for live switching, no `envFrom`). This makes BACK-03 compliance automatic for all 20 of Phase 3's generated servers rather than something each one re-implements.

### Deployment Layout
- **D-17:** Phase 2's MCP-layer workloads get a **new namespace, `otel25-mcp`** — not a reuse of Phase 1's `otel25-backends`. Matches STACK.md's own architecture sketch, which separates "mcp-servers" and "mock-backends" namespaces.
- **D-18:** Deployment continues with **plain `oc apply` YAML manifests** — no Helm introduced yet, consistent with Phase 1's precedent. Revisit if Phase 3's scale (20+ tools + gateway) makes templating worthwhile.
- **D-19:** New repo layout: a **top-level `mcp/` directory**, parallel to `backends/` — `mcp/tooling/` for the conversion CLI, `mcp/mcp-telecom/` for the vendored MCP-Telecom fork. This sets the directory pattern Phase 3's domain servers will also live under.
- **D-20:** OpenShift liveness/readiness probes for the deployed MCP-Telecom server check **process-up / MCP endpoint responds** (liveness: port alive; readiness: Streamable HTTP endpoint responds to a basic `tools/list` request) — they do NOT attempt to validate device connectivity, consistent with D-07.

### Claude's Discretion
- Exact Service/port naming for the deployed MCP-Telecom (D-04).
- Exact shape/filenames of the device-inventory scaffold and command-allowlist scaffold (D-10, D-10a), as long as credentials reference OpenShift Secrets.
- Exact YAML allowlist-config schema for the conversion CLI (D-12), as long as it supports operationId/tag selection.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Domain & tooling landscape
- `gaps/gap-1-tool-calling/mcp_toolkit_audit.md` — MCP-Telecom's tool inventory, transport (stdio), license (MIT), and the two-track approach (MCP-Telecom for infrastructure layer, new tools for BSS/OSS layer) that this phase's scope is built on.
- `OTel_2.5_MCP_and_Data_Landscape.md` — full landscape of MCP toolkits, SDG methodology, eval benchmarks, sandbox environments.
- `gaps/gap-1-tool-calling/fault_prediction_api_map.md` — API-by-API map of TMF642/628/621, NWDAF, CAMARA operations (informs what Phase 3's conversion CLI runs will target).

### Stack & architecture research (MANDATORY — governs FastMCP/conversion-tooling decisions above)
- `.planning/research/STACK.md` §"Why FastMCP Python over TypeScript MCP SDK", §"Post-conversion curation is mandatory" — grounds D-11/D-13's codegen-then-curate approach and the FastMCP version/compatibility matrix.
- `.planning/research/ARCHITECTURE.md` §"Anti-Pattern 1: Raw OpenAPI-to-MCP Auto-Conversion", §"Anti-Pattern 2: Single Monolithic MCP Server" — directly informs D-13 (curate, don't ship raw auto-conversion) and the domain-separated-servers rationale Phase 3 will follow.
- `.planning/research/PITFALLS.md` — no Phase-2-specific pitfall exists for MCP-Telecom's stdio transport or missing device backend; D-01/D-07 fill a gap the original research didn't cover and should be treated as newly-evidenced constraints, not oversights.

### Phase 1 contracts this phase must honor
- `.planning/phases/01-backend-infrastructure/01-CONTEXT.md` — D-06 (vendoring precedent for D-05), D-08 (Prism realism flag-forward precedent for D-09), D-15/D-16 (backend-routing ConfigMap contract that D-16 bakes into generated scaffolds).
- `backends/openshift/configmap-backend-routing.yaml` — the literal ConfigMap contract (volume-mount + file-watch requirement) that D-16's scaffolded file-watcher must satisfy.

### Project-level constraints
- `.planning/PROJECT.md` — "Constraints" section: OpenShift required, Apache 2.0 for deliverables (informs D-06's MIT-isolation approach), Oct 15 2026 deadline.
- `.planning/REQUIREMENTS.md` — MCP-06, MCP-07 (this phase's requirements).
- `.planning/ROADMAP.md` — Phase 2 success criteria (conversion tooling + MCP-Telecom deployment), Phase 3 dependency (gateway composition expects network-reachable servers, informing D-01/D-03).

No SPEC.md exists for this phase.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backends/openshift/configmap-backend-routing.yaml` — existing ConfigMap and its documented volume-mount/file-watch consumer contract; the conversion CLI's scaffolds (D-16) must implement a client matching this contract.
- `backends/scripts/verify-routing.sh` — Phase 1's verification-script pattern (D-16 in 01-CONTEXT.md) that this phase's MCP-Telecom callability check (D-08) and CAMARA smoke test (D-14) should follow stylistically.

### Established Patterns
- Vendoring over live-fetching (01-CONTEXT.md D-06) — extended in this phase to vendoring MCP-Telecom itself (D-05).
- Per-service OpenShift Deployment/Service pairs, plain YAML, no Helm (01-CONTEXT.md D-05 applied to Prism instances) — continued in D-18.
- Namespace-per-layer (Phase 1 used `otel25-backends` for all backend mocks) — extended with a new `otel25-mcp` namespace for the MCP layer (D-17).

### Integration Points
- MCP servers generated by the conversion CLI (Phase 3) will mount `backends/openshift/configmap-backend-routing.yaml`'s ConfigMap — the file-watching logic baked in per D-16 is the integration point.
- MCP-Telecom's deployment in `otel25-mcp` is a parallel, independent workload from `otel25-backends` — no direct integration with Phase 1's backends in this phase (MCP-Telecom doesn't call TMF/NWDAF/CAMARA APIs).

</code_context>

<specifics>
## Specific Ideas

- Fork MCP-Telecom to add Streamable HTTP transport, vendored under `mcp/mcp-telecom/`, since it's already FastMCP-based and the patch should be small.
- Conversion CLI lives at `mcp/tooling/`, generates one-time `server.py` scaffolds per spec, smoke-tested against CAMARA Device Location locally before Phase 3 relies on it.
- New `otel25-mcp` namespace, plain YAML manifests, parallel to Phase 1's `backends/openshift/` layout style.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Wiring MCP-Telecom to real network devices, the 20 curated domain tools, and the Kuadrant MCP Gateway composition were all explicitly recognized as Phase 3/4 work, not pulled forward.

</deferred>

---

*Phase: 2-MCP Tooling Foundation*
*Context gathered: 2026-10-02*
