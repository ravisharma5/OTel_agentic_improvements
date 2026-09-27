# Phase 1: Backend Infrastructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-27
**Phase:** 1-Backend Infrastructure
**Areas discussed:** OpenShift cluster & access, Prism mock deployment shape, NextGCore validation & fallback, Backend routing design

---

## OpenShift Cluster & Access

| Option | Description | Selected |
|--------|-------------|----------|
| Personal/dev sandbox | Fastest iteration, no shared-resource coordination | ✓ |
| Red Hat internal shared cluster | Existing team/org cluster | |
| WG-shared cluster | Dedicated to this LFN WG project | |

**User's choice:** Personal/dev sandbox.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, already logged in | oc CLI configured and authenticated | |
| No, need to set up first | Cluster/login needs provisioning before deployment | ✓ |
| Not sure yet | Confirm before execution | |

**User's choice:** No, need to set up first.

| Option | Description | Selected |
|--------|-------------|----------|
| OpenShift Local (CRC) | Single-node local cluster, free, offline-capable | |
| Red Hat Developer Sandbox | Free hosted OpenShift sandbox, time-limited, shared infra | ✓ |
| Not decided yet | Open pre-flight decision | |

**User's choice:** Red Hat Developer Sandbox.

| Option | Description | Selected |
|--------|-------------|----------|
| Design around default SCCs only | Avoid privileged/custom SCC requirements entirely | |
| Flag as a risk, decide during NextGCore work | Capture as known constraint, resolve later | |

**User's choice:** Neither — free text: "I will create a cluster with more resources." Superseded the premise of the question; user will provision a cluster with admin-level access and sufficient resources instead of using the constrained free Developer Sandbox tier.

**Notes:** This effectively reverses the "Red Hat Developer Sandbox" answer above — the sandbox tier's quota/SCC constraints won't apply because a more capable cluster will be provisioned.

---

## Prism Mock Deployment Shape

| Option | Description | Selected |
|--------|-------------|----------|
| One Prism deployment per API | 4 separate Deployments/Services/Routes | ✓ (initially) |
| One shared Prism instance, multiple specs | Single instance, path-routed | |

**User's choice:** One Prism deployment per API (later superseded by the tool switch to Microcks — see below).

| Option | Description | Selected |
|--------|-------------|----------|
| Vendored into this repo | Committed under e.g. backends/specs/ | ✓ |
| Fetched at build/deploy time | Pulled from upstream GitHub repos | |

**User's choice:** Vendored into this repo.

| Option | Description | Selected |
|--------|-------------|----------|
| Mock TMF628 as-is from Swagger 2.0 | No conversion needed for mocking | ✓ |
| Convert to OAS 3.0 first, then mock | Consistent format across all 4 mocks | |

**User's choice:** Mock TMF628 as-is from Swagger 2.0.

| Option | Description | Selected |
|--------|-------------|----------|
| Official Prism CLI image + mounted spec | Minimal custom build | |
| Custom image baking in the spec | One more image per API | |

**User's choice:** Neither — free text question: "Is Prism opensource and are there any other alternatives?" Claude answered (Prism is MIT OSS; alternatives include Microcks, WireMock, Mockoon) and highlighted Microcks' native OpenShift Operator as a fit for the "Red Hat tools preferred" constraint.

| Option | Description | Selected |
|--------|-------------|----------|
| Microcks | CNCF project, Apache 2.0, OpenShift Operator, better fit for Red Hat constraint | ✓ |
| Prism | Stick with original research, MIT, simpler | |

**User's choice:** Microcks. This decision supersedes the earlier "one Prism deployment per API" answer above.

| Option | Description | Selected |
|--------|-------------|----------|
| Single Microcks instance, all 4 specs imported | Matches Microcks' intended usage model | ✓ |
| Separate Microcks instance per API | Stronger isolation, unusual for this tool | |

**User's choice:** Single Microcks instance, all 4 specs imported.

| Option | Description | Selected |
|--------|-------------|----------|
| Dynamic schema-based generation | More response variety for SDG | ✓ |
| Static examples added to specs | More control, more upfront authoring work | |

**User's choice:** Dynamic schema-based generation.

| Option | Description | Selected |
|--------|-------------|----------|
| Automated schema validation script/test | Repeatable pass/fail check | ✓ |
| Manual spot-check via curl/Postman | Faster now, not durable | |

**User's choice:** Automated schema validation script/test.

---

## NextGCore Validation & Fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Timebox validation, fall back to mocking NWDAF too | Bounded effort, documented fallback | ✓ |
| Validate first, no fallback — block on it working | Treat as hard requirement | |

**User's choice:** Timebox validation, fall back to mocking NWDAF too.

| Option | Description | Selected |
|--------|-------------|----------|
| 1-2 days | Quick spike | |
| 3-5 days | More thorough attempt including OpenShift adaptation | |
| You decide during execution | Don't lock a number now | ✓ |

**User's choice:** You decide during execution.

| Option | Description | Selected |
|--------|-------------|----------|
| Validate locally via Docker Compose first, then port to OpenShift | Fast feedback before OpenShift adaptation effort | |
| Go straight to OpenShift adaptation | Skip local validation | |

**User's choice:** Neither exactly — free text: "Validate locally with Podman first and then port to OpenShift." Same sequencing, Podman substituted for Docker (Red Hat tooling preference).

| Option | Description | Selected |
|--------|-------------|----------|
| Defer nextgsim/UE simulation to Phase 4 | Keep Phase 1 scoped to reachability | |
| Set up nextgsim now in Phase 1 | Realistic analytics data from day one | ✓ |

**User's choice:** Set up nextgsim now in Phase 1.

---

## Backend Routing Design

| Option | Description | Selected |
|--------|-------------|----------|
| Per-API routing | One entry per API, matches current mock/backend granularity | ✓ |
| Per-tool routing | Finer control, but no tools exist yet (Phase 3) | |

**User's choice:** Per-API routing.

| Option | Description | Selected |
|--------|-------------|----------|
| Plain ConfigMap, consumed directly by future MCP servers | No extra moving parts | ✓ |
| ConfigMap + lightweight routing proxy | Centralizes routing logic, more infra to validate early | |

**User's choice:** Plain ConfigMap, consumed directly by future MCP servers.

| Option | Description | Selected |
|--------|-------------|----------|
| Small test script that reads ConfigMap and calls backend | Proves the contract before any real MCP server exists | ✓ |
| Defer verification to Phase 2/3 when real MCP servers exist | Wait for a real consumer | |

**User's choice:** Small test script that reads ConfigMap and calls backend.

---

## Post-Discussion Correction: Prism vs. Microcks

After the discussion concluded and CONTEXT.md was written, a check of `.planning/research/STACK.md` (produced during roadmap creation, not consulted during this discussion) revealed an existing "Why Prism over Microcks" analysis: Microcks requires MongoDB + Keycloak + the Microcks server, which is unnecessary operational weight for lightweight, pipeline-internal mocks. This directly contradicted the mid-discussion decision to switch to Microcks (made on the basis of its native OpenShift Operator alone, without this research loaded).

Presented to the user as a follow-up question:

| Option | Description | Selected |
|--------|-------------|----------|
| Revert to Prism | Go with the original research recommendation | ✓ |
| Keep Microcks anyway | Accept the operational overhead for the OpenShift Operator fit | |
| Let me look at the trade-off myself first | Show full STACK.md context before deciding | |

**User's choice:** Revert to Prism.

**Resulting changes to CONTEXT.md:** D-04 through D-09 rewritten to specify Prism (one instance per API spec, per `ARCHITECTURE.md`'s layout) instead of Microcks. D-10 updated to reference Prism (not Microcks) as the NWDAF mocking fallback. Canonical refs expanded to include all of `.planning/research/*.md`, which had been missed by the initial codebase scout.

**Lesson:** `.planning/research/*.md` should be checked during `load_prior_context`/`scout_codebase` for phases that follow a `/gsd:new-project` roadmap creation — it contains resolved technical trade-offs that should not be re-litigated blind during discussion.

---

## Claude's Discretion

- Exact timebox duration for NextGCore/NWDAF validation before falling back to mocking it.
- Naming conventions for the OpenShift namespace/project, ConfigMap keys, and vendored spec directory structure.

## Deferred Ideas

None — discussion stayed within phase scope. Per-tool routing granularity and a routing-proxy service were considered and explicitly deferred as premature (no consumer exists yet), not as out-of-scope ideas.
