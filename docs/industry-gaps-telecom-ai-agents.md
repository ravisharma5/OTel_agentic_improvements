# Industry Gaps: Deploying Telecom AI Agents in Production

Author: Ravi Sharma

This project (OTel 2.5's tool-calling infrastructure and SDG pipeline, Phases 1-4) spent five weeks building MCP servers against real TM Forum/3GPP/CAMARA APIs, composing them behind a gateway, and running a synthetic-data pipeline against them end to end. Along the way we hit the same category of problem repeatedly, independently, across unrelated phases and reviewers. That repetition is the actual finding: these aren't one-off mistakes, they're gaps in what the ecosystem currently gives you.

Three areas, each with our own evidence plus what currently exists (and doesn't) industry-wide.

## 1. MCP conformance testing framework

### The gap

Every phase of this project built its own tool-verification scripts, and every phase's independent reviewers caught the same flaw: the scripts proved the MCP protocol round-tripped (a tool call returned *some* JSON), not that the response was a schema-valid, semantically plausible answer from the actual backend.

- **Phase 1** (`01-REVIEWS.md`): both independent reviewers flagged that `validate-mocks.sh`/`check-nwdaf.sh` "mostly prove reachability and JSON parseability, not OpenAPI conformance or realistic analytics behavior."
- **Phase 2** (`02-REVIEWS.md`): the verify script's "discover first tool, synthesize minimal args from inputSchema" strategy is brittle against nested/enum/union schemas; a CAMARA allowlist smoke test didn't actually test filtering, because the fixture spec exposed only one operation — a broken filter would still have passed.
- **Phase 3** (`03-REVIEWS.md`): two independent reviewers converged on the identical conclusion, three separate times across three different plans: "a tool could show as PASS while actually hitting a schema-validation error or synthetic no-op call."
- **Phase 4**: `osft_validation.py`'s `validate_tool_output_against_schema` exists specifically because a Prism mock in dynamic mode returned syntactically valid JSON with garbled property names and flipped discriminator types for a `oneOf` schema — valid JSON, wrong shape, and nothing upstream caught it until we added a dedicated check.

Four phases, multiple reviewers, one recurring verdict. This isn't a skill gap on our end — it's evidence that "protocol conformance" and "response conformance" are being treated as the same problem when they aren't, and nothing freely available tests the second one.

### What exists today

The official MCP conformance suite (`modelcontextprotocol/conformance` on GitHub) is real and has matured quickly through 2026 — a `tier-check` CLI scores servers/clients against versioned requirement sets, and as of SEP-2484 a spec change can't reach "Final" status without a matching conformance scenario. A community tool (`studiomeyer-io/mcp-protocol-conformance`) covers JSON-RPC 2.0, OAuth 2.1 PKCE, and tool-schema/capability checks for earlier spec versions.

Both test the same layer: handshake, transport, auth flow, tool-list shape. **Neither tests whether a tool's actual response content matches its declared output schema when called against a real (or realistically mocked) backend.** That's precisely the gap all four of our phases hit. We found no Red Hat-specific MCP conformance tooling — RHCL/Kuadrant's MCP Gateway and RHOAI's `MCPServer` CRD route and deploy MCP servers, they don't verify them.

### What's needed

A conformance layer above the protocol level: given a tool's declared `outputSchema` and a live (or recorded) backend response, assert the response actually validates — including `oneOf`/`discriminator` polymorphism, which is exactly where Prism's dynamic mode failed us. `validate_tool_output_against_schema` in this project's `sdg/lib/osft_validation.py` is a minimal, single-purpose version of this; it's not a framework, but it's a concrete starting shape for one.

## 2. Standard telco API simulators

### The gap

Generic OpenAPI mocking tools don't produce telecom-realistic data, and the standard conformance tooling that does exist has gaps of its own.

- **Confirmed directly**: Prism-backed mocks for TMF642, TMF628, TMF621, and CAMARA all returned nonsense values from the training-data perspective — Lorem Ipsum `nsiId` strings ("sunt sit", "dolor pariatur laboris proident") and a negative `loadLevelInformation` (-60465668) for a TS 29.520 analytics query. Root cause: TM Forum's APIs lean on generic name-value "characteristic" bags, which give a generic OpenAPI mocker nothing to infer realistic values from.
- **No Prism mock exists for NWDAF at all.** `NWDAF_BASE_URL` always pointed at live NextGCore. The one real semantic call we attempted against it failed outright — NextGCore's NWDAF API serves HTTP/2 cleartext (h2c), but the client sent HTTP/1.1, producing "illegal request line." NWDAF's 3 tools ended up protocol-verified only, never semantically verified against any backend.
- **NextGCore's own limitations**: NWDAF subscriptions are memory-only with no durable store (an open upstream issue); a restart silently drops them with no termination signal to a client watching for one.
- **Spec fragmentation**: TMF642 ships both Swagger 2.0 and OAS 3.0 versions with different resource models; TMF628 is Swagger-2.0-only. TM Forum's own conformance profile documentation states plainly that full compliance "does not guarantee out-of-the-box interoperability" between implementations.

### What exists today

TM Forum publishes an official Conformance Test Kit (CTK) — Docker-based, runs a reference "Virtual Service" implementation, scores conformance, and produces a certification submission file. Per-API repos live under the `tmforum-rand` GitHub org (`CTK-TMF641-ServiceOrder`, `CTK-TMF629-CustomerManagement`, etc.), plus a lighter static variant (`tmforum-apis/APITestEngineStaticCTK`) that scores a Swagger doc against the canonical spec without running anything.

Even the CTK has documented weaknesses: third-party analysis (Specmatic) found CTK v5.0.0 can pass an implementation that's drifted from the published OpenAPI spec, doesn't validate its own request payloads against that spec, and skips error-response schemas and field optionality/nullability checks. So the realism gap isn't unique to ad hoc mocking — it exists in the standard tooling too.

For 5G core simulation, there's no single standard tool — it's a DIY assembly: Open5GS or Free5GC for core network functions, UERANSIM for the gNB/UE simulation layer, with NWDAF bolted on separately (`DFevereiro/open5gs-nwdaf` is a notable open, 3GPP TS 23.288-compliant NWDAF for Open5GS with 120 tests; `M-Baraa-Mardini/NWDAF` is a vendor-agnostic plugin-architecture alternative with Free5GC support still in development). We found no Red Hat-branded 5G core simulator — Red Hat's published telco reference architectures target production CNF deployment, not simulation for development/testing.

Prism itself is explicit about its own limits: dynamic mode generates from schema shape, not meaning (a bare `type: string` comes back as the literal string `"string"` unless the spec supplies an `example`), it's fully stateless (a POST then GET won't round-trip), and it has no SSE/streaming, persistence, or auth story. It's documented as "for development only," which matches exactly how we ended up using it — enriching vendored specs with realistic `example` values was Phase 4's own mitigation, not something the tool gave us for free.

### What's needed

Nothing changes the fundamental tradeoff: realistic telco mock data currently requires manually enriching OpenAPI specs with representative `example` values (what we did), or running a real/near-real core (NextGCore) with its own immaturity (memory-only subscriptions, protocol mismatches). An operator evaluating this space should budget for spec-enrichment work up front rather than expect a mocking tool to produce telecom-plausible data out of the box — and should test the CTK's own gaps (spec drift, error-response schemas) before trusting a "passed CTK" claim as proof of real interoperability.

## 3. Agent deployment reference architecture on OpenShift

### The gap

We hit the same class of deployment problem twice, in unrelated phases, months apart, with no shared pattern available to prevent the repeat:

- **OpenShift's arbitrary-UID requirement bit us twice.** Phase 2's MCP-Telecom Dockerfile used `USER mcpuser`, which isn't sufficient on OpenShift — it needed `chgrp -R 0 /app && chmod -R g=u /app` to let an arbitrary dynamically-assigned UID (always in group 0) actually write to the directory. The exact same fix was independently needed again in Phase 4's SDG pipeline image, which hit `PermissionError: [Errno 13] Permission denied: 'sdg/data'` for the identical underlying reason. Nothing documented the pattern between the two phases.
- **Agent configuration has no infrastructure-as-code story.** Langflow's Agent component system prompt lives only in the running flow's own database/UI state. It's reachable only via a direct API `PATCH` call — not version-controlled, not reproducible from a manifest, and invisible in any `git diff`. We hit this directly: patching the production system prompt (twice, during an experiment) required a live API call against the running flow, and reverting required another. A production agent-deployment reference architecture needs an answer for this; none exists today for Langflow-on-OpenShift.
- **DataSciencePipelinesApplication (DSPA) ships incomplete RBAC by design.** The operator creates the `Role` an in-cluster pod needs to submit pipeline runs via `kfp.Client()`, but never creates the matching `RoleBinding` — that's left to whoever deploys it. Worse, the standard verification tools (`oc auth can-i`, `oc policy who-can`) gave false negatives for this exact CRD-subresource shape; only a raw `SubjectAccessReview` gave the correct answer.
- **RHCL's MCP Gateway (Technology Preview) has an undocumented reconciliation hazard.** Its `MCPVirtualServer` controller writes to a secret in a `mcp-system` namespace, but the broker actually reads a *different* secret (`otel25-gateway/mcp-gateway-config`). We manually merged the two; any future reconciliation of `MCPServerRegistration` objects risks silently overwriting that manual merge with no warning.
- **KFP's build cache has a silent-staleness edge.** The cache key is the literal image tag string, not the resolved image digest — resubmitting a pipeline against a `:latest`-tagged image with genuinely new content inside it silently cache-hits the *old* content. We confirmed this in practice; there's no built-in warning when it happens.

### What exists today

Red Hat's published pattern is Llama Stack (via the RHOAI-managed Llama Stack Operator) as the single agent abstraction over vLLM inference and in-cluster MCP servers, sitting behind an AI gateway where credentials are configured once centrally rather than per-agent (the "agentic software factory" pattern, documented on `docs.redhat.com`). RHOAI 3.5 Early Access adds an "Agent-as-a-Service" runtime: a client names a goal and required MCP servers, the runtime advertises tool schemas, executes calls, iterates, and persists every step to durable storage, all behind a Responses API. The MCP Gateway (RHCL/Kuadrant-based) is positioned as the security control point — every tool call authorized by token claims rather than by the model itself — which matches the architecture we built by hand in Phase 3.

Red Hat's own roadmap names the next piece explicitly: **MCP-as-a-Service (MCPaaS)**, a centrally hosted, observed, and audited MCP server model, paired with an "AI Hub" unifying models, agents, guardrails, and MCP servers. We found early, concrete evidence of this already landing — the RHOAI `MCPServer` CRD (`mcp.x-k8s.io`, container-image-source only as of 3.5.1) and an "AI Hub → MCP servers → Registry" UI we confirmed only in a not-yet-released 3.6 screenshot — but confirmed hands-on that neither is a finished reference architecture yet: the CRD can't register an already-running remote server (only deploy a fresh one from an image), and the Registry UI isn't installed on any cluster we could test against.

Maturity levels, where stated by Red Hat: the MCP server for OpenShift (cluster access for agents via OAuth/OIDC) is Technology Preview; the OGX/Llama Stack Agent-as-a-Service pattern on RHOAI 3.5 is Early Access; MCPaaS and the unified AI Hub are roadmap items, not shipped.

We found no published connection between this agentic architecture work and Red Hat's existing telco 5G Core/RAN reference architectures — those remain infrastructure/CNF-focused, with no AI-agent content. The academic literature has a name for the missing piece ("e-NWDAF": NWDAF plus OSS/BSS northbound integration plus an AI-agent layer) but its own authors flag it as lacking empirical validation. **No one has published a production-grade pattern connecting 3GPP NWDAF to an agentic AI layer** — which is exactly the space this project's own NWDAF MCP tool sits in, and exactly why we had to work out the OpenShift deployment patterns above ourselves rather than following an existing one.

### What's needed

An operator deploying telecom AI agents on OpenShift today is assembling Technology-Preview and Early-Access components (MCP Gateway, Llama Stack Operator, RHOAI's MCP tooling) without a single reference architecture that covers the full path from a 3GPP/TMF backend through an MCP server, a gateway, an agent runtime, and a fine-tuned or prompted model — and without a documented answer for agent-configuration-as-code, which matters as much as the infrastructure pieces once more than one team touches the same agent.

## Summary

| Area | What's missing | What exists | Maturity |
|---|---|---|---|
| MCP conformance | Response-content validation against declared schema, against a real/realistic backend | Protocol/transport/auth conformance (official MCP suite, community tools) | Protocol layer: maturing fast (2026). Response layer: nonexistent |
| Telco API simulators | Realistic, stateful, spec-faithful mocks for TMF/3GPP APIs | TM Forum CTK (has its own documented gaps); DIY 5G core assembly (Open5GS/Free5GC + UERANSIM + bolted-on NWDAF) | CTK: official, imperfect. 5G simulation: fragmented, no single standard |
| Agent deployment on OpenShift | End-to-end reference pattern (backend → MCP → gateway → agent → model); agent-config-as-code | Llama Stack Operator, RHCL/Kuadrant MCP Gateway, RHOAI Agent-as-a-Service, MCPaaS/AI Hub roadmap | Technology Preview to Early Access; MCPaaS/AI Hub not yet shipped |

Every gap in this document traces back to something we actually hit building this project, not a hypothetical. The pattern worth remembering: when the same category of problem shows up independently in unrelated phases, caught independently by different reviewers, that's a signal the gap is in the ecosystem, not in the team.
