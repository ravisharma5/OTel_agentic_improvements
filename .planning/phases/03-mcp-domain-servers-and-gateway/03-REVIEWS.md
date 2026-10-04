---
phase: 3
reviewers: [gemini, cursor]
reviewed_at: 2026-10-04T21:38:10Z
plans_reviewed: [03-01-PLAN.md, 03-02-PLAN.md, 03-03-PLAN.md, 03-04-PLAN.md, 03-05-PLAN.md, 03-06-PLAN.md]
---

# Cross-AI Plan Review — Phase 3

> `claude` (this CLI) was skipped for independence — the orchestrating session runs on Claude Code.
> `ollama` (local qwen3.8:27b) was also requested but did not return a response within the allotted time (~45K-token prompt is too large for the local model's throughput); it has been launched as a long-running background job and will be appended to this file if it completes. Proceeding with gemini + cursor.

## Gemini Review

```markdown
# Phase 3 Implementation Plan Review

## Summary
The Phase 3 plans are exceptionally well-structured and demonstrate a deep understanding of OpenShift, RHCL MCP Gateway, and FastMCP. The approach to split multi-spec domains into explicit `@mcp.tool()` decorators elegantly sidesteps tool-naming collisions, and the cross-namespace ConfigMap copying is handled with proper operational documentation. The plans robustly address the phase requirements, including comprehensive end-to-end verification and infrastructure provisioning.

## Strengths
- **Multi-Spec Domain Handling:** Using explicit `@mcp.tool()` functions for NWDAF and CAMARA (03-03) smartly avoids the double-prefixing issue that `FastMCP.mount()` would introduce when interacting with RHCL's `MCPServerRegistration`.
- **ConfigMap Workaround:** Copying the `backend-routing` ConfigMap from `otel25-backends` to `otel25-mcp` (03-05) and explicitly documenting the dual-patching requirement in `STATE.md` is a mature operational solution to Kubernetes' namespace boundaries.
- **Idempotent Keycloak Setup:** The creation of `configure-keycloak.sh` (03-04) to manage Keycloak's ephemeral state and k8s secrets is highly resilient and accounts for pod lifecycle events.
- **Two-Phase Docker Builds:** Generating `uv.lock` before finalizing the `Dockerfile` with `--frozen` (03-05) ensures reproducible container builds.
- **Thorough Verification:** The parameterized scripts `verify-domain-tools.sh` and `verify-gateway.sh` (03-01) integrated into the Wave 3/4 plans provide excellent behavioral coverage.

## Concerns
- **MEDIUM - Keycloak Ephemeral State Check (03-06):** In Plan 06 Task 2 Step 3, the instruction states: "If the Secret is missing (e.g., Keycloak pod restarted and ephemeral storage was lost), re-run the idempotent configuration script". Because K8s Secrets outlive pod restarts, the Secret will likely still exist even if Keycloak's ephemeral database is wiped. You cannot rely on the existence of the Secret to trigger a script re-run.
- **MEDIUM - Dual Istio / Non-Mesh Backend Routing (03-04 / 03-06):** Pitfall 2 notes potential dual-Istio conflicts. Since the `otel25-mcp` backend pods do not have Istio sidecars (they are not mesh-enrolled), the Gateway API's Envoy proxy must route plain HTTP to them. You must ensure that the auto-provisioned `openshift-default` Gateway Class does not default to enforcing mTLS for backend routes.
- **LOW - Untracked `uv.lock` Files (03-05):** Task 2 runs `uv lock` to generate lockfiles for the 5 domain servers but doesn't explicitly mention adding/tracking them in git. While they are copied into the Docker image, they should be tracked in version control for future deterministic builds.

## Suggestions
- **Refine Keycloak Recovery:** In Plan 03-06, modify the verification in Task 2 Step 3 to attempt fetching the JWT first. If the `curl` command fails or returns an authentication error (indicating the ephemeral Keycloak lost its realm/client config), *then* re-run `configure-keycloak.sh` and retry the token fetch.
- **Track Lockfiles:** In Plan 03-05, explicitly add a minor step to stage (`git add`) the newly generated `uv.lock` files to ensure they are tracked.
- **Verify Plaintext Routing:** In Plan 03-04/03-06, double-check if RHCL's HTTPRoute implementation requires any specific annotations to reliably route to non-mesh ClusterIP services, or if it handles plaintext fallback implicitly.

## Risk Assessment
**LOW**
The risks identified are localized to testing (Keycloak restart) and edge-case Gateway API configurations. The overall architecture, sequencing, and fallback mechanisms are extremely sound, and the plan is ready for execution.
```

---

## Cursor Review

## Overall
The phase is well-scoped and generally aligned to the stated Phase 3 goal: build the 20 tools, deploy them, and federate them behind RHCL. The biggest weaknesses are not in the decomposition, but in the execution assumptions: the current verification strategy can overstate success, the NWDAF live-path model is still underspecified, and the gateway wave takes on a lot of infrastructure risk at once.

### Top findings
- **HIGH:** The planned verification scripts mostly prove MCP protocol reachability, not that tools successfully hit backends with valid payloads. The existing analog (`scripts/verify-mcp-telecom.sh` from Phase 2) already chooses "easy" tools heuristically and treats several error classes (invalid params, connection refused) as PASS rather than FAIL.
- **HIGH — CONFIRMED by orchestrator against the actual repo:** Plan 03-03 (line ~135) states "For NextGCore, the ConfigMap URL already includes /nnwdaf-analyticsinfo/v1 (per 03-RESEARCH.md Pitfall 4)." This is factually false against the current `backends/openshift/configmap-backend-routing.yaml`, which sets `NWDAF_BASE_URL: "http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:7777"` (host:port only, no path) and explicitly documents in its own "NWDAF PATH NOTE" comment block: *"NextGCore NWDAF (Path A) serves at /nnwdaf-analyticsinfo/v1/analytics. Consumers should use the NWDAF_BASE_URL + the appropriate path for their backend."* 03-RESEARCH.md's Pitfall 4 actually *recommends* baking the path into the ConfigMap value for NextGCore going forward — it does not claim this has already been done. The plan conflated a recommendation with an already-applied fact. **Scope note:** D-11 limits Phase 3's required verification to Prism only, so this does not block Phase 3's literal pass/fail — but if left uncorrected, whoever flips the ConfigMap to live NextGCore (likely Phase 4) will hit silent 404s on the analytics endpoint.
- **HIGH:** The gateway wave (03-04) bundles OSSM, cert-manager, Keycloak, and the RHCL operator into one wave — if any one of those slips, the whole phase bottlenecks on a single wave.

## Per-plan findings

**03-01** (verification scripts): MEDIUM — script design allows empty/synthetic arguments and treats validation failures as pass, so it doesn't prove "returns valid responses from backends," only "protocol reachable." Suggest separating "protocol reachable" from "backend semantically working" into distinct checks, and adding one curated known-good payload per tool family.

**03-02** (TMF642/628/621): MEDIUM — TMF642's acknowledge/clear/comment tools depend on exact PATCH payload schemas; current verification is smoke-level and doesn't require a successful Prism-backed call per server. Suggest adding contract tests for the three TMF642 PATCH bodies and requiring at least one successful `tools/call` per server with known-good arguments.

**03-03** (NWDAF/CAMARA): HIGH (see NWDAF path bug above) — also notes the allowlist YAMLs are "documentation only" and may drift from the hand-written implementation since nothing enforces consistency.

**03-04** (gateway infra): HIGH — acknowledges the dual-Istio/mesh risk in its own threat model but still hardcodes `gatewayClassName: openshift-default` without an explicit mesh-trust-domain compatibility check; suggests adding a minimal gateway→dummy-service route test before layering MCP-specific registrations on top.

**03-05** (deploy + verify 20 tools): HIGH — the ConfigMap dual-namespace copy creates two sources of truth for backend routing (flagged independently by the plan-checker in iteration 1 and still only mitigated with documentation, not a sync mechanism); verification inherits 03-01's "protocol-only" weakness, so all 20 tools can be marked "verified" without a real backend-semantic check.

**03-06** (gateway composition): MEDIUM-HIGH — hand-authoring `MCPVirtualServer` tool lists from discovery output (across 78 tools, mixed generated/hand-written names) is error-prone; suggests generating virtual-server tool lists from `MCPServerRegistration` discovery output instead of maintaining them by hand.

## Bottom Line
The plans are thoughtfully decomposed and mostly achieve the right shape for Phase 3. Three things worth fixing before/during execution:
1. Strengthen verification so "pass" means a real backend-semantic success (at least one known-good payload per tool), not just MCP protocol round-trip success.
2. Correct Plan 03-03's false claim about the NWDAF ConfigMap already containing the NextGCore path — fix the plan text (and flag it forward in STATE.md for Phase 4 if not fixed now, since it doesn't block Phase 3's Prism-only success criteria).
3. De-risk the gateway wave (03-04) by adding an explicit mesh/routing checkpoint before stacking MCP-specific registrations on top, and reduce manual drift risk in 03-06's hand-authored virtual-server tool lists.

---

## Ollama Review

*Not available at time of writing — local qwen3.8:27b did not return a response for this ~45K-token prompt within the allotted time. See note at top of this document.*

---

## Consensus Summary

### Agreed Strengths (both reviewers)
- The core architectural decisions are sound: RHCL as the real gateway product (not DIY FastMCP mount()), hand-written NWDAF/CAMARA tools to avoid double-prefixing (D-10a), idempotent Keycloak config script, two-phase Dockerfile lockfile finalization, and namespace/deployment layout all read as well-reasoned and consistent with locked CONTEXT.md decisions.
- Overall phase decomposition (6 plans / 4 waves) correctly delivers the phase goal's three success criteria.

### Agreed Concerns (both reviewers, independently)
- **Verification strength is the single most-repeated concern.** Both reviewers flaged that `verify-domain-tools.sh` / `verify-gateway.sh` (and their Phase 2 analog) risk proving only "MCP protocol round-trip succeeded" rather than "tool call produced a semantically valid backend response." This affects the credibility of Phase 3's own stated success criterion #1 ("20 tools... return valid responses from their backends") — a tool could show as PASS while actually hitting a schema-validation error or synthetic no-op call.
- **Gateway wave (03-04) is the highest-risk single point of failure** — bundling Service Mesh, cert-manager, Keycloak, and the RHCL operator install into one wave means any one component failing stalls Waves 2-4 behind it.
- **ConfigMap dual-namespace copy (03-05) remains a real concern even after the iteration-1 revision** — documentation of the dual-patch requirement reduces but doesn't eliminate the two-sources-of-truth risk for BACK-03 compliance going forward (Phase 4 will need to actually act on this, not just read a warning).

### Divergent / Reviewer-Specific Findings
- **Cursor only:** found and the orchestrator independently confirmed against the repo that Plan 03-03 misstates the current NWDAF ConfigMap contract (claims the NextGCore path is "already included" when it isn't). Gemini's review did not flag this specific line-level discrepancy — it focused more on infrastructure/mesh-layer concerns (dual-Istio mTLS enforcement, Keycloak Secret-vs-ephemeral-DB state mismatch) that Cursor did not independently surface in the same terms, though both converged on "Keycloak recovery logic is unreliable" from different angles (Gemini: Secret existence isn't a valid signal; Cursor: realm/client state is disposable and destabilizes downstream debugging).
- **Gemini rated overall risk LOW**; **Cursor rated several individual plans HIGH** (03-03, 03-04, 03-05) with an overall tone of "achievable but currently overstates verification confidence." This is a genuine disagreement in overall risk framing, not just emphasis — worth weighing when deciding whether to replan now (`/gsd:plan-phase 3 --reviews`) or execute and treat these as watch-items during execution.
