---
phase: 1
reviewers: [gemini, cursor]
reviewed_at: 2026-10-02T00:20:00Z
plans_reviewed: [01-01-PLAN.md, 01-02-PLAN.md, 01-03-PLAN.md, 01-04-PLAN.md]
---

# Cross-AI Plan Review — Phase 1

## Gemini Review

Here is the review of the Phase 1 implementation plans for the OTel 2.5 Telecom Tool-Calling Training project.

### 1. Summary
The Phase 1 plans are exceptionally well-structured, thoroughly researched, and perfectly sequenced to prevent dependency deadlocks. The explicit adoption of a "timebox-then-fallback" strategy for the NextGCore NWDAF deployment demonstrates mature engineering judgment, effectively isolating the biggest project risk. The plans strictly adhere to the requested constraints (OpenShift, zero-dependency start, security best practices). However, while the mock-tier deployments (Prism) are highly resilient, the "happy path" for the live-tier deployment (NextGCore on OpenShift) underestimates the complexity of Kubernetes pod topology and local resource constraints, which could lead to false negatives during validation or deployment failures.

### 2. Strengths
- **Excellent Risk Mitigation:** The explicit branching logic between Plan 02 (validation) and Plan 04 (deployment) ensures the phase won't stall if the experimental 5G core is broken.
- **Security by Default:** The plans enforce `ClusterIP` services (avoiding accidental public exposure of mock endpoints) and minimal-privilege custom SCCs (`NET_ADMIN` only for the UPF), strictly avoiding the `privileged: true` anti-pattern.
- **Zero-Dependency Foundation:** Plan 01 elegantly vendors the upstream OpenAPI specs, ensuring reproducible builds and removing live network dependencies from the deployment pipeline.
- **Durable Test Artifacts:** Instead of manual validation, the plans build robust bash scripts (`validate-mocks.sh`, `verify-routing.sh`) that become reusable CI assets for future phases.
- **Strict Scope Management:** The plans successfully resist scope creep, explicitly rejecting the creation of a routing proxy/gateway in favor of a simpler, consumer-less `ConfigMap` for Phase 1.

### 3. Concerns
- **[HIGH] NextGCore OpenShift Topology (Plan 04):** Cramming 22 Network Functions (NFs) plus a UE/gNB simulator into a *single OpenShift Pod* is highly problematic. OpenShift `initContainers` run strictly sequentially, meaning startup could take excessively long. Furthermore, 24 containers sharing a single network namespace can lead to port conflicts, and the combined resource requests will likely violate default namespace quotas.
- **[MEDIUM] OpenShift Internal Registry Access (Plan 03):** Step 4 requires pushing custom Prism images to the OpenShift internal registry. This process is notoriously brittle, often failing due to missing default routes, DNS resolution issues on the host machine, or untrusted self-signed TLS certificates (even with `--tls-verify=false`).
- **[MEDIUM] False Negatives in Local Validation (Plan 02):** A fixed `sleep 30` timer is used to wait for a 22-NF 5G core to initialize and for the UE to register via Podman. On a local developer machine, cold-starting 22 containers and establishing PDU sessions can easily take 1-3 minutes. A strict 30-second wait may result in a false "NO-GO" decision.
- **[LOW] Health Check Ambiguity (Plan 03):** The plan instructs the agent to dynamically inspect the OpenAPI specs to find a valid GET path for readiness/liveness probes. If a spec relies heavily on required query parameters or headers, standard `httpGet` probes might return 4xx errors, causing a crash-loop state.

### 4. Suggestions
- **Refine the NextGCore Pod Topology:** If Plan 04 proceeds with Path A, do not use a single pod. Split it into at least two pods: one for the UPF (requiring the `nextgcore-upf` ServiceAccount and custom SCC) and one for the Control Plane NFs. Better yet, aggressively prune the `docker-compose.yml` to only the 6-8 NFs strictly required to support NWDAF, dropping unused subscriber/policy functions if possible.
- **Implement a Wait Loop in Plan 02:** Replace `sleep 30` with a timeout loop that checks the `nextgsim-ue` logs every 10 seconds for up to 3 minutes. This will prevent a slow machine from triggering a premature NO-GO decision.
- **Provide a Registry Fallback:** Update Plan 03 to allow pushing to a personal public registry namespace (e.g., `quay.io/youruser/` or `docker.io`) if the `oc patch` command to expose the internal registry fails. This bypasses OpenShift registry networking headaches entirely.
- **Hardcode Probe Paths:** Rather than having the agent guess health check paths at execution time in Plan 03, extract and specify the exact paths in the plan instructions (e.g., TMF642 = `/alarm`, TMF628 = `/measurementCollectionJob`, TMF621 = `/troubleTicket`). For CAMARA, which is POST-heavy, explicitly mandate a `tcpSocket` probe on port `4010` to avoid HTTP 4xx validation failures.

### 5. Risk Assessment
**Overall Risk Level: MEDIUM**

*Justification:* The foundational setup (Plan 01), mock deployments (Plan 03), and ConfigMap routing (Plan 04) are extremely low risk and virtually guaranteed to succeed. The complexity of porting a pure-Rust 5G core to OpenShift carries a traditionally HIGH risk. However, because the plans include an explicit "timebox-then-fallback" safety valve (Path B), the actual risk to the *project timeline and Phase 1 completion* is downgraded to MEDIUM. As long as the execution agent respects the fallback trigger, Phase 1 will successfully deliver the required backend endpoints on schedule.

---

## Cursor Review

### Overall
The Phase 1 planning is strong on sequencing, research grounding, and separating low-risk Prism work from high-risk NextGCore work. The biggest gaps are not about missing tasks so much as mismatches between what the plans *prove* and what the phase requirements *claim*: the fallback NWDAF path does not currently satisfy `BACK-02` as written, the routing contract does not yet guarantee no-redeploy switching for future consumers, and the mock validation scripts are too weak to prove schema conformance.

### Top Findings
The most important requirement mismatch is the NWDAF fallback. `Plan 04` treats a Prism NWDAF mock as satisfying `BACK-02`, but the repo requirements and roadmap explicitly say Phase 1 succeeds only if `NextGCore` itself is running on OpenShift:

```
- [ ] **BACK-01**: Deploy Prism mock backends on OpenShift for TMF642, TMF628, TMF621, and CAMARA APIs from their OpenAPI specs
- [ ] **BACK-02**: Deploy NextGCore on OpenShift with working NWDAF endpoints for execution-verified analytics tool calls
- [ ] **BACK-03**: Configure backend routing via ConfigMap (swap between Prism mocks and live backends without code changes)
```

```
**Goal**: Mock and live backends are deployed on OpenShift and return valid API responses for all fault-prediction APIs
**Depends on**: Nothing (first phase)
**Requirements**: BACK-01, BACK-02, BACK-03
**Success Criteria** (what must be TRUE):
  1. Prism mock servers for TMF642, TMF628, TMF621, and CAMARA APIs return valid HTTP responses matching their OpenAPI spec schemas
  2. NextGCore is running on OpenShift with NWDAF endpoints responding to TS 29.520 analytics requests
  3. Backend routing ConfigMap allows switching any MCP tool between Prism mock and live backend without redeploying services
```

The second structural issue is the routing contract. The plan says future MCP servers may consume the ConfigMap via env var *or* mounted file, but env vars will not update live, so that does not actually meet "switch without redeploying services" for consumers:

```
- **D-15:** The routing mechanism is a **plain Kubernetes ConfigMap** holding a mock/live base URL per API. Future Phase 2/3 MCP servers will read it directly (env var or mounted file) to pick which backend to call. Phase 1 does **not** build a routing proxy/gateway service — that would be infra built without a real consumer to validate against.
```

The third major issue is validation strength: the planned scripts mostly prove reachability and JSON parseability, not OpenAPI conformance or realistic analytics behavior.

### Plan 01 Review
**Summary:** Good foundational plan with clear artifact outputs and sensible dependency placement. The main weakness is that the validation strategy is too shallow for a phase whose success criterion explicitly says responses must match spec schemas, and the spec vendoring is not as reproducible as the plan implies.

**Strengths:**
- Clear "wave 1" foundation with reusable artifacts for all downstream plans.
- Good separation between vendored specs, Prism image packaging, and validation scripts.
- Uses pinned filenames and specific source URLs, which is better than ad hoc fetch-at-runtime behavior.
- Correctly avoids premature OpenShift work before basic assets exist.

**Concerns:**
- **HIGH:** `validate-mocks.sh` only checks HTTP `2xx` plus "valid JSON"; that does not prove responses match the OpenAPI schema or contain required fields.
- **MEDIUM:** The TMF source URLs point at mutable branches like `main`, so the vendoring process is not truly pinned or reproducible.
- **MEDIUM:** The plan bakes specs into per-spec images, but `D-06` says specs should be mounted into Prism containers via ConfigMap. That is a plan/decision mismatch.
- **MEDIUM:** Both CAMARA specs are vendored, but only one is clearly intended to be served later. If "retrieve location" matters for fault prediction, this phase may leave one required backend path unavailable.

**Suggestions:**
- Replace "JSON parses" with independent schema validation against specific endpoints and expected status codes.
- Pin vendored downloads to immutable commit SHAs or release tags and record the upstream commit in a manifest.
- Decide explicitly whether Prism should use baked images or mounted specs, then align `CONTEXT.md`, research, and plan text.
- Clarify whether CAMARA retrieval is required in Phase 1; if yes, merge specs or plan a second CAMARA mock now.

**Risk Assessment:** MEDIUM. The artifact generation is straightforward, but the current verification is too weak to confidently claim `BACK-01` completion.

### Plan 02 Review
**Summary:** This is the best-scoped plan in the set: it attacks the highest-risk dependency early, uses a go/no-go gate, and respects the "Podman first, OpenShift later" decision. The main problem is that the fallback outcome is treated like a valid completion path even though the written requirement says otherwise.

**Strengths:**
- Excellent risk-first sequencing.
- Explicit timebox-then-fallback strategy matches the context well.
- Validates `nextgsim` activity, not just HTTP reachability.
- Produces evidence needed for later planning instead of guessing.

**Concerns:**
- **HIGH:** A `NO-GO` outcome currently leads to Prism fallback without any requirement change, even though `BACK-02` requires `NextGCore` on OpenShift.
- **MEDIUM:** Go/no-go criteria are subjective: "non-empty JSON" and "actual analytics data" are not crisp enough for a blocking decision.
- **MEDIUM:** Failures in Podman + `docker-compose` on macOS may reflect local runtime quirks rather than real `NextGCore` infeasibility.
- **MEDIUM:** Testing one-shot analytics queries is appropriate, but it may still fail to prove that `nextgsim` traffic materially affects NWDAF output.

**Suggestions:**
- Define explicit `GO` criteria: required endpoint path, expected HTTP codes, minimum required JSON keys, and evidence that UE/PDU activity changes analytics state.
- Split outcomes into three cases: `GO`, `ENVIRONMENTAL-BLOCKED`, and `NO-GO`.
- If fallback is used, record it as a requirement exception or roadmap change, not silent success.
- Capture `k8s/` directory usability in the summary with enough detail for `Plan 04` to consume directly.

**Risk Assessment:** HIGH. The plan is good, but the decision it drives has phase-level implications that are not yet reconciled with the stated requirements.

### Plan 03 Review
**Summary:** Solid deployment plan for the Prism tier, with good scoping and internal-only exposure. The main risk is incomplete CAMARA coverage plus some fragility in the image build/push path and probe strategy.

**Strengths:**
- Clear separation of cluster setup from deployment work.
- Sensible one-deployment-per-API pattern for TMF mocks.
- ClusterIP-only services are the right default for dev/sandbox backends.
- Reuses prior artifacts instead of re-solving spec packaging.

**Concerns:**
- **HIGH:** `prism-camara` appears to serve only `location-verification`, while the project requirements later call for both CAMARA tools. If both are in phase scope for backend readiness, this is incomplete.
- **MEDIUM:** The plan assumes internal image registry route exposure and uses `--tls-verify=false`; workable for dev, but operationally brittle and not ideal from a security standpoint.
- **MEDIUM:** Readiness/liveness probe selection is under-specified and may fail on specs whose endpoints require query params or POST bodies.
- **LOW:** Validation depends on port-forward/manual local execution paths rather than a clean in-cluster smoke job.

**Suggestions:**
- Make the CAMARA decision explicit now: one merged spec, two Prism instances, or a documented reason retrieval is deferred.
- Prefer one cluster-native image path such as BuildConfig/ImageStream if registry route setup becomes painful.
- Add a local parse/smoke test for every spec before deploying to OpenShift.
- If CAMARA must use `tcpSocket` probes, strengthen the post-deploy functional checks to compensate.

**Risk Assessment:** MEDIUM. Prism deployment itself is low risk, but incomplete CAMARA coverage would undercut the phase goal.

### Plan 04 Review
**Summary:** This plan completes the phase on paper, but it is also where the biggest conceptual gaps appear. The branching logic is pragmatic, yet the fallback path conflicts with `BACK-02`, and the ConfigMap switching proof does not yet demonstrate the eventual "no redeploy" behavior of real MCP consumers.

**Strengths:**
- Good use of the `Plan 02` decision as a hard branch.
- Keeps routing intentionally simple and avoids premature proxy/gateway work.
- Includes end-to-end verification instead of declaring success from manifest creation alone.
- Correctly isolates SCC usage to the `NextGCore` path.

**Concerns:**
- **HIGH:** The Prism NWDAF fallback does not satisfy `BACK-02` as currently written.
- **HIGH:** The routing design does not yet guarantee hot switching for consumers because env-var-based consumption requires pod restart.
- **HIGH:** The `NextGCore` OpenShift porting task is under-specified for the complexity involved. "Run all NFs in a single pod" sounds simple but may still be a substantial integration project.
- **MEDIUM:** `verify-routing.sh` proves ConfigMap mutability and the script's own re-read behavior, not actual consumer switchover semantics.
- **MEDIUM:** `check-nwdaf.sh` only verifies one endpoint returns JSON, not that analytics are realistic, non-default, or driven by `nextgsim`.
- **LOW:** A placeholder SCC file in the fallback path may confuse downstream automation or reviewers.

**Suggestions:**
- Either change the requirement/roadmap now to allow "NWDAF-compatible fallback endpoint," or keep fallback as a documented partial completion rather than calling `BACK-02` done.
- Lock the consumer contract now: use mounted files or direct API reads, not env vars, if "no redeploy" is a real success criterion.
- Narrow the `NextGCore` OpenShift scope to the minimal NF set required for NWDAF validation and name those containers/configs explicitly.
- Add a tiny long-running test consumer in Phase 1 that reads routing config the same way future MCP servers will, then prove it switches backends without restart.
- Make `check-nwdaf.sh` assert expected fields and, ideally, a before/after signal from `nextgsim`.

**Risk Assessment:** HIGH. This is the plan most likely to report success without actually meeting the written phase contract.

### Bottom Line
The plan set is thoughtfully sequenced and grounded in real research, but I would not call it execution-ready until three things are fixed:

1. Reconcile `BACK-02` with the Prism fallback path.
2. Lock the routing-consumer contract so "no redeploy" is actually achievable.
3. Strengthen validation so `BACK-01` and `BACK-02` are proven, not inferred.

---

## Consensus Summary

### Agreed Strengths
- **Risk-first sequencing of NextGCore validation (Plan 02):** Both reviewers single out validating NWDAF locally via Podman *before* investing in OpenShift porting as the standout design decision of the phase.
- **Security-conscious defaults:** Both call out `ClusterIP`-only services and minimal-privilege SCC scoping (`NET_ADMIN` limited to the UPF) as correct, deliberate choices rather than oversights.
- **Clean foundation/dependency structure:** Both note Plan 01's artifact-first approach (vendored specs, validation scripts before deployment) sets up the rest of the phase well.

### Agreed Concerns
- **[HIGH, both reviewers] NextGCore single-pod OpenShift topology (Plan 04) is underspecified and likely infeasible as written.** Gemini: 22 NFs + simulator in one pod risks sequential `initContainers` startup times, port conflicts, and quota violations. Cursor: "run all NFs in a single pod" is a substantial integration project being treated as a simple task. **Action: before executing Plan 04's Path A, split NextGCore into multiple pods (at minimum UPF separate from control-plane NFs) or prune to the minimal NF set needed for NWDAF, per Gemini's specific suggestion.**
- **[MEDIUM–LOW, both reviewers] Readiness/liveness probe paths for Prism (Plan 03) are resolved too late and too loosely.** Both flag "inspect the spec at execution time to find a GET path" as risky — specs with required query params or POST-only operations (CAMARA) could cause crash-looping or false health signals. **Action: hardcode specific probe paths per API now (Gemini proposes exact paths per TMF API and a `tcpSocket` probe for CAMARA) rather than leaving this to execution-time judgment.**

### Divergent Views (worth resolving before execution)
- **Whether the NWDAF fallback satisfies BACK-02 at all.** Gemini treats the timebox-then-fallback strategy as unambiguously good engineering and factors it into a MEDIUM overall risk rating. **Cursor disagrees more fundamentally: REQUIREMENTS.md and ROADMAP.md literally say "Deploy NextGCore on OpenShift" / "NextGCore is running on OpenShift" — a Prism NWDAF mock fallback doesn't satisfy that text as written, regardless of how well-engineered the fallback is.** This is a real tension between the *locked* CONTEXT.md decision (D-10, explicitly approved by the user during discuss-phase) and the original ROADMAP/REQUIREMENTS wording that predates that decision. This was a known, deliberate tradeoff from discuss-phase, not an oversight — but Cursor's point that it should be reconciled explicitly (e.g., a note in ROADMAP.md acknowledging the fallback as an accepted alternate success path) rather than silently asserted as complete is worth acting on.
- **The routing "no redeploy" consumer contract.** Only Cursor caught that CONTEXT.md's D-15 allows future MCP servers to consume the ConfigMap "via env var or mounted file" — but env vars are only read at pod startup, so an env-var-based consumer would need a restart to pick up a routing change, which doesn't actually satisfy "switch backends without redeploying services." Gemini did not flag this. **This is a legitimate design gap worth fixing now:** either mandate mounted-file consumption (which can be live-reloaded) for future MCP servers, or document that only file-mount consumption satisfies the no-redeploy contract.
- **Validation script strength.** Cursor rates this HIGH across multiple plans (validate-mocks.sh doesn't prove schema conformance, check-nwdaf.sh doesn't prove realistic analytics). Gemini doesn't rate this as a top concern, focused instead on operational risks (registry push, probe paths, sleep timers). Both are valid — they're reviewing different failure modes (correctness-of-proof vs. operational-flakiness).
- **OpenShift internal registry brittleness (Plan 03).** Gemini flags this as a MEDIUM operational risk with a concrete suggested fallback (push to quay.io/docker.io instead). Cursor doesn't mention it. Worth a quick look before executing Plan 03, though not blocking.

