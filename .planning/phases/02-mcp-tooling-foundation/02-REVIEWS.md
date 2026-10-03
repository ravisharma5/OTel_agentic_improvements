---
phase: 2
reviewers: [gemini, cursor, ollama]
reviewed_at: 2026-10-03T14:39:52.000Z
plans_reviewed: [02-01-PLAN.md, 02-02-PLAN.md, 02-03-PLAN.md]
---

# Cross-AI Plan Review — Phase 2

> Claude (this session) was excluded as a reviewer since it authored/revised these plans — reviewing itself would not be independent. Codex, CodeRabbit, OpenCode, Qwen, LM Studio, and llama.cpp were not available in this environment.

## Gemini Review

# Phase 2: MCP Tooling Foundation - Plan Review

## 1. Summary
The implementation plans for Phase 2 are exceptionally well-researched, meticulously structured, and strictly adhere to the phase boundaries and project constraints. The plans demonstrate a deep understanding of both the FastMCP ecosystem and Kubernetes native behaviors, correctly identifying critical pitfalls like the `mcp` vs. `fastmcp` package divergence and the `inotify` symlink swap issue with ConfigMaps. The strategy to use string templating to bypass FastMCP's lack of codegen and the integration of the mtime-polling ConfigMap watcher are pragmatic and effective. While conceptually very strong, there are a few execution-level risks regarding Python string formatting and OpenShift container permissions that should be addressed before implementation.

## 2. Strengths
* **Deep Kubernetes Awareness:** Accurately identifying that Kubernetes ConfigMap volume updates use atomic symlink swaps (which break standard `inotify` watchers) and proactively designing an `mtime`-based polling fallback.
* **Precise Dependency Management:** Catching the divergence between MCP-Telecom's use of the `mcp` SDK built-in FastMCP and the project's standard standalone `fastmcp` package, preventing a major version conflict.
* **Security & Supply Chain Rigor:** Including a `checkpoint:human-verify` task for PyPI packages (since `slopcheck` was unavailable) and aggressively scaffolding deny-by-default security configurations (command allowlists) before they are even wired to real devices.
* **Robust Verification Automation:** The `verify-mcp-telecom.sh` script dynamically extracts a tool name from `tools/list` rather than hardcoding it, making the test resilient to upstream tool additions/removals.
* **Excellent Scope Discipline:** Rigorously adhering to Phase 2 boundaries by scaffolding configurations for devices but intentionally leaving the "wiring" to Phase 4, documenting the expected connection errors as a passing condition.

## 3. Concerns
* **Code Generation Syntax Conflicts (HIGH):** Plan 02-03 proposes using `str.format()` for the inline Python string template. Because Python code relies heavily on curly braces `{}` for dictionaries, sets, and f-strings, using `str.format()` requires doubling every literal curly brace (`{{`, `}}`). This will result in an unreadable template and is highly prone to syntax errors during generation.
* **OpenShift Arbitrary UID Compatibility (MEDIUM):** Plan 02-02's Dockerfile creates a non-root user (`USER mcpuser`), but does not configure directory permissions for the root group (`0`). OpenShift runs containers with a randomly assigned UID that belongs to the root group. If the application needs to write *anything* to the filesystem (e.g., Python `__pycache__`, temp files), it will fail with `Permission denied`.
* **httpx Client Mutation Safety (MEDIUM):** Plan 02-03 mutates the `client.base_url` directly on the module-level `httpx.AsyncClient` object. While the plan correctly notes that testing this behavior in FastMCP's internal dispatch is deferred to Phase 3, direct mutation of a shared HTTP client's base URL is fragile and not strictly thread-safe in all asynchronous contexts.

## 4. Suggestions
* **Switch Template Engine:** In `openapi_to_mcp.py` (Plan 02-03), use Python's built-in `string.Template` (which uses `$var` substitution) or simple string `.replace()` instead of `str.format()`. This completely avoids the curly brace escaping issue while still preventing the need for a heavy Jinja2 dependency.
* **Fix Dockerfile Permissions:** In the `mcp/mcp-telecom/Dockerfile` (Plan 02-02), add a step to grant group ownership and write permissions to the application directory before switching to the user:
  ```dockerfile
  RUN chgrp -R 0 /app && chmod -R g=u /app
  USER 1001
  ```
* **Alternative Client Routing (Optional):** Instead of mutating `client.base_url` in the file-watcher (Plan 02-03), consider generating a custom `httpx.AsyncTransport` or overriding `httpx.AsyncClient.send()` in the scaffold to dynamically inject the backend URL per request. If this is too complex for the scaffold, keep the current approach but add a highly visible TODO comment in the generated code warning Phase 3 engineers about the potential `from_openapi()` client caching issue.
* **ASGI Server Startup Validation:** In Plan 02-01, ensure that when replacing `mcp.run(...)` with `app = mcp.http_app()` and `uvicorn`, the script execution logic accurately imports and runs the ASGI application, as CLI entrypoints behave differently than programmatic server execution.

## 5. Risk Assessment
**Overall Risk Level: MEDIUM**

**Justification:** The architectural choices are fundamentally sound and well-researched. The "Medium" rating is strictly due to the `str.format()` code generation approach, which has a very high likelihood of causing syntax errors in the generated `server.py` scaffolds during the CAMARA smoke test. Implementing the suggestion to use `string.Template` and fixing the OpenShift group permissions in the Dockerfile will immediately reduce the execution risk to **LOW**.

---

## Cursor Review

## Overall
These plans are well-researched, phase-scoped, and much stronger than a typical first pass. They align well with the existing Phase 1 patterns in `backends/scripts/verify-routing.sh` and the live-switching contract in `backends/openshift/configmap-backend-routing.yaml`. The main risks are not architectural drift, but execution traps: lockfile/runtime assumptions around vendored `MCP-Telecom`, an overly brittle verification strategy in `02-02-PLAN.md`, and a smoke test in `02-03-PLAN.md` that does not actually prove the two hardest claims: operation filtering and backend hot-reload propagation.

## `02-01-PLAN.md`
### Summary
Strong plan overall. It keeps scope tight, respects the vendoring/licensing decisions, and sets up the right scaffolding for later phases. The weak spots are mostly around reproducibility and whether the new safety/config artifacts are actually wired into runtime behavior versus just existing on disk.

### Strengths
- Clear boundary: vendor + patch transport + add scaffolds, without drifting into deployment or gateway work.
- Good alignment with the project-wide FastMCP direction in `.planning/research/STACK.md`.
- Good security posture for Phase 2: Secret references for device credentials and deny-by-default command allowlisting.
- Sensible requirement to run MCP-Telecom's upstream tests after the dependency swap instead of trusting a shallow import change.
- Good forward compatibility with Plan 02 by adding `/healthz` now.

### Concerns
- `HIGH`: The plan never says how `uv.lock` will be created or refreshed after swapping `mcp[cli]` for `fastmcp`, but `02-02-PLAN.md` later assumes `mcp/mcp-telecom/uv.lock` exists and is compatible with `uv sync --frozen`. That is a dependency-ordering gap between plans.
- `MEDIUM`: The health endpoint implementation switches to `mcp.http_app()` + `uvicorn`, but the plan does not explicitly add or validate `uvicorn` as a runtime dependency. If it is not already pulled transitively, the patched entrypoint can fail even if the import swap works.
- `MEDIUM`: `test_allowlist.py` may become a false-confidence test if it validates only a helper function rather than the actual safe-exec path in MCP-Telecom. The plan says "or test against the existing safety module," but this should be nailed down, not left optional.
- `MEDIUM`: Vendoring from GitHub without pinning the upstream commit SHA reduces reproducibility and supply-chain traceability. For this project, "vendored" should really mean "vendored from commit X".
- `LOW`: Listing `mcp/mcp-telecom/LICENSE` under `files_modified` is harmless, but operationally this is probably "copied from upstream" rather than "modified," so the acceptance framing is slightly misleading.

### Suggestions
- Add an explicit output artifact recording the upstream repo URL and commit SHA used for vendoring.
- Make lockfile handling part of Plan 02-01, not implicit in Plan 02-02. Either generate a fresh `uv.lock` here or remove `--frozen` later.
- Require the allowlist test to exercise the real enforcement path used by the safe CLI tool, not just a helper.
- Add an explicit startup smoke test for the patched server over HTTP before relying on the full upstream test suite.
- Confirm whether `uvicorn` is guaranteed by `fastmcp`; if not, declare it directly.

### Risk Assessment
**MEDIUM**. The plan is conceptually solid, but there are two realistic execution failures: lockfile drift and runtime entrypoint/dependency mismatch.

## `02-02-PLAN.md`
### Summary
This plan is phase-aligned and operationally detailed in the right places. The biggest problem is the verification design: dynamically invoking the first discovered tool is too fragile to be a reliable gate. The container runtime assumptions for OpenShift are the other main risk.

### Strengths
- Good separation of deployment artifacts from Plan 02-01's vendoring/patching work.
- Good reuse of established Phase 1 patterns from `backends/scripts/verify-routing.sh` and the OpenShift manifest style in `backends/openshift/`.
- Good choice to keep the service `ClusterIP` only and avoid external exposure in this phase.
- Good requirement to update `.planning/STATE.md` with the no-device-backend gap instead of leaving it implicit.
- Sensible use of `tools/list` plus an invocation check; that is the right shape of proof for D-08.

### Concerns
- `HIGH`: The "discover first tool from `tools/list` and synthesize minimal args from `inputSchema`" strategy is brittle. Many tools will have nested required objects, enums, unions, or target-specific requirements. That means the script can fail for schema-construction reasons even when MCP transport and tool registration are fine.
- `HIGH`: `USER mcpuser` does not, by itself, make the image OpenShift-arbitrary-UID-safe. If the container runs under a random UID or if `uv run` needs writable cache/home paths, this can fail despite looking "non-root".
- `MEDIUM`: The probe story is slightly inconsistent. The plan text says readiness should reflect "MCP endpoint response," but the actual probe is `GET /healthz`, which only proves the app is up, not that `POST /mcp` works.
- `MEDIUM`: This plan still depends on the unresolved `uv.lock` issue created upstream in `02-01-PLAN.md`.
- `MEDIUM`: Port-forward verification is fine for pod behavior, but it does not prove an in-cluster client can resolve and use `mcp-telecom.otel25-mcp.svc.cluster.local`. For a deployment plan, that is a small but real blind spot.
- `LOW`: The registry-route enablement and authfile fallback are useful notes, but they are fairly environment-specific and may make the plan look more deterministic than it really is.

### Suggestions
- Replace "first discovered tool" with a deterministic verification strategy:
  - pick from a curated shortlist of simple tools discovered in the live catalog, or
  - probe for a tool with zero required inputs, or
  - add a server-level self-test endpoint/tool if that is acceptable later.
- Either keep `/healthz` for readiness and treat MCP protocol proof as a separate verification script concern, or use an exec probe that posts a real `tools/list`.
- Make the Dockerfile explicitly OpenShift-safe:
  - avoid runtime writes where possible,
  - ensure group permissions support arbitrary UID execution,
  - avoid `uv run` if it requires writable runtime state.
- Add an in-cluster verification mode, such as a disposable pod or `oc exec`-based check against the service DNS name.
- Resolve the lockfile contract before this plan begins.

### Risk Assessment
**MEDIUM-HIGH**. The deployment mechanics are reasonable, but the current verification method is likely to generate false failures, and the container may hit OpenShift runtime issues.

## `02-03-PLAN.md`
### Summary
This is the most ambitious and also the riskiest plan. The CLI concept is sound, but the current validation strategy overstates what it proves. The chosen CAMARA smoke test is too weak for operation filtering, and the generated server pathing looks likely to break when output is written outside the repo tree.

### Strengths
- Good reuse of the FastMCP `from_openapi()` + `RouteMap` approach from the research.
- Strong intent to bake the Phase 1 backend-routing contract into generated scaffolds instead of leaving each Phase 3 server to reinvent it.
- Good decision to keep this local-only and avoid premature OpenShift deployment.
- Inline string templating is a reasonable simplification for a single-template generator.
- Good acknowledgement in `.planning/STATE.md` that `client.base_url` mutation may not actually propagate through FastMCP request handling.

### Concerns
- `HIGH`: The smoke test writes the generated server to `/tmp/camara_server.py`, but the plan also says the scaffold should bake a spec path resolved relative to the generated file. That will break unless the CLI rewrites the spec path to an absolute path or copies the spec alongside the output.
- `HIGH`: The allowlist smoke test does not really test filtering. `backends/specs/camara_location_verification.yaml` exposes a single operation, `/verify`, so a broken allowlist implementation could still pass.
- `HIGH`: The plan treats `client.base_url` mutation as the mechanism for BACK-03 compliance while simultaneously acknowledging that FastMCP may freeze request dispatch against the original client state. That is not a validated behavior yet and should not be framed as solved.
- `MEDIUM`: There are two sources of truth for the spec path: `--spec` and `allowlist.spec_path`. If they differ, the generated scaffold can silently encode something other than what the CLI validated.
- `MEDIUM`: The plan invests heavily in watcher mechanics tests but does not add equally valuable negative tests for invalid allowlist config, invalid `mcp_type`, or malformed operation entries.
- `MEDIUM`: The known `TMF628` Swagger 2.0 concern in `.planning/STATE.md` remains completely unexercised here. That may be acceptable for this phase, but it should be explicitly deferred, not implied solved.

### Suggestions
- Make the generated scaffold self-contained with respect to the spec:
  - either bake an absolute spec path for local smoke tests,
  - or copy the spec into a sibling `specs/` directory next to the generated file,
  - or embed the spec text directly.
- Strengthen the filtering proof with a multi-operation fixture. Since the real CAMARA file only has one operation, add a tiny synthetic 2-operation OpenAPI fixture specifically to prove allowlist exclusion.
- Downgrade the backend hot-reload claim from "compliant" to "candidate implementation present, propagation still unverified" unless Phase 2 actually proves end-to-end request rerouting.
- Enforce that `--spec` and `allowlist.spec_path` either match semantically or collapse to one source of truth.
- Add schema-validation tests for invalid allowlists; those are likely to catch more real CLI bugs than extra watcher tests.
- Call out `TMF628` Swagger 2.0 handling as an explicit deferred validation item if it is not going to be exercised here.

### Risk Assessment
**HIGH**. The plan is directionally right, but its current success criteria can pass without proving the two most important behaviors: selective operation exposure and usable runtime packaging of generated scaffolds.

## Cross-Plan Notes
- Scope discipline is good overall, but keep `MCP-08` clearly out of Phase 2. The planning context mentions it in the phase-adjacent requirements table while the actual phase boundary correctly defers gateway composition to Phase 3.
- The best existing repo pattern to preserve is the explicit contract style in `backends/openshift/configmap-backend-routing.yaml`: if a behavior is required later, either prove it now or describe it as unresolved. `02-03-PLAN.md` should be especially strict about that.
- If you fix only three things before execution, make them these:
  1. define lockfile/runtime expectations between `02-01-PLAN.md` and `02-02-PLAN.md`,
  2. replace the "first discovered tool" invocation heuristic in `02-02-PLAN.md`,
  3. fix the generated-spec path and filtering-proof gap in `02-03-PLAN.md`.

---

## Ollama Review

# Review of Phase 02 Plans: MCP Tooling Foundation

## Summary

The Phase 02 plans are well-structured and logically progress from foundational schema validation to production-ready code generation. The conversion CLI enables one-time codegen of FastMCP server skeletons based on OpenAPI specs and YAML allowlists, while baking in critical compliance patterns (ConfigMap file-watching and URL validation) that address BACK-03 gaps. The plans are practical and testable, with isolated unit tests for the file-watcher component and end-to-end smoke tests against the CAMARA spec. However, there are notable risks around the propagation of `client.base_url` changes through `from_openapi()`, unclear handling of malformed ConfigMap symlinks, and an unvalidated assumption that `from_openapi()` does not freeze the HTTP client state. The plans are technically sound but require careful validation in Phase 3 to avoid runtime failures.

## Strengths

- **Clear Separation of Concerns**: The CLI is modular, with `allowlist_schema.py` handling validation and `openapi_to_mcp.py` generating the scaffold. This makes maintenance and testing easier.
- **Comprehensive Test Suite**: The `test_configmap_watcher.py` covers valid, invalid, missing-file, and URL-propagation scenarios with robust isolation.
- **Practical Implementation of BACK-03 Compliance**: The file-watcher implementation with `client.base_url` mutation is a pragmatic choice to close the compliance gap, even if propagation through `from_openapi()` is not fully tested.
- **Good Dev Practices**: Use of `uv run` for dependency management, `textwrap.dedent` for template generation, and dependency version constraints in `pyproject.toml`.
- **Realistic Deployment Path**: The plans acknowledge that the CLI is for Phase 3 curation (not production use), with testing against local servers and explicit local-only smoke tests.
- **Threat Modeling**: Explicit consideration of tampering risks for ConfigMap URLs and OpenAPI specs with mitigation strategies.

## Concerns

### High Severity

- **BACK-03 Compliance Gap**: The critical assumption that `client.base_url` mutations propagate correctly through `FastMCP.from_openapi()` is **not validated**. The plan states this is "deferred to Phase 3," but no fallback strategy exists if the client base URL is not updated at runtime (as in `from_openapi()` freezing the HTTP client). Without explicit validation or a workaround (e.g., recreating the app on backend change), this could cause catastrophic failure in production.

- **Unvalidated ConfigMap Symlink Handling**: The plan avoids inotify because Kubernetes ConfigMap volumes perform atomic symlink swaps that break inotify watches (per RESEARCH.md Pitfall 4). However, **this is not validated or tested** in the plans. The mtime-based approach may work for symlink swaps that preserve file modification times — but in practice, if symlinks are swapped atomically, mtime might not change. This is a **HIGH RISK** unvalidated assumption.

### Medium Severity

- **OpenAPI Spec Validation**: Although the plans state to "verify spec file exists," there is **no validation of the OpenAPI spec's validity or schema compatibility**. A malformed spec could cause runtime crashes or produce unexpected tool behavior. This should be mitigated by adding `fastmcp` schema validation or a validator like `openapi-spec-validator`.

- **No Error Handling for Client base_url Mutation**: The file-watcher implementation does not include a retry mechanism or error handling if the URL is invalid or if `client.base_url` is not set (due to `from_openapi()` internals freezing the value). This should be addressed with a fallback URL or a graceful degradation.

- **No Version Pinning for FastMCP**: While `pyproject.toml` uses `>=4.0.0`, this is vulnerable to breaking changes. **FastMCP** should be version-pinned to the exact version used in Phase 01 to ensure compatibility. For example, `fastmcp == 4.0.0` instead of `>=4.0.0`.

### Low Severity

- **Unvalidated `customize_components` Hook**: The hook is stubbed and commented, but no guidance is given for developers or for Phase 3 on how to implement it. This is not critical but may cause confusion.

- **Lack of Documentation for CLI**: While the CLI is runnable, there is **no user-facing documentation** that explains the purpose of each field, expected inputs, or error conditions. This is a minor issue for Phase 02 (testability-focused), but will be needed for Phase 3.

## Suggestions

- **Add Explicit Validation for `client.base_url` Mutation**: Add a unit test that mocks `from_openapi()` to verify that `client.base_url` is not frozen at tool creation time. If it is frozen, propose a workaround for Phase 3 — e.g., a `reconfigure_backend_url()` function that re-instantiates the app on URL change.

- **Add OpenAPI Spec Validation**: Use `fastmcp`'s built-in `validate_spec()` or a third-party validator like `openapi-spec-validator` to validate input specs before processing. This prevents crashes due to malformed specs.

- **Version Pin FastMCP**: Use an exact version pin for FastMCP (e.g., `fastmcp == 4.0.0`) to avoid breaking changes. Update the `pyproject.toml` dependency.

- **Add Retry Logic for File-Watcher**: Add a retry mechanism that attempts to read the file 3 times on failure, or logs the failure with error context. This improves resilience.

- **Add User Documentation for CLI**: Generate an automatically generated `--help` output and write a short README.md for the CLI explaining usage, constraints, and expected behavior. This is useful for Phase 3 curation teams.

- **Add Validation for `BACKEND_ROUTING_PATH`**: In `test_configmap_watcher.py`, ensure the `BACKEND_ROUTING_PATH` env var value is validated to be non-empty and a proper path before passing it to the watcher.

- **Add Test for URL Redirection**: Add a test that reads a URL from the ConfigMap, then updates it with an invalid URL and asserts the watcher keeps the previous valid URL (already covered in `test_rejects_invalid_url`, but this test could be extended to test redirect behavior via HTTP status codes).

## Risk Assessment

**Risk Level: MEDIUM**

**Justification**: The implementation is technically sound and achieves the core goals of Phase 02 — generating code with filtered operations and ConfigMap file-watching. However, the **unvalidated propagation of `client.base_url` changes** and the **unvalidated ConfigMap symlink handling** represent significant risks that could break Phase 3 deployment. These are **HIGH SEVERITY** risks, but they are mitigated by Phase 3 validation. The lack of OpenAPI spec validation and version pinning represents **MEDIUM SEVERITY** risks that can be addressed with minimal effort. Since Phase 3 will validate and deploy the generated code, the MEDIUM risk level is appropriate — the code is production-ready, but requires phased validation to ensure it handles edge cases.

The success of Phase 02 is contingent on Phase 3 validating the `client.base_url` propagation assumption. Without this validation, Phase 1's MCPToolingFoundation will be a failure — a risk that should be formally tracked and mitigated during Phase 3 planning.

---

## Consensus Summary

All three reviewers independently converge on the same top-line verdict: the plans are well-researched and scope-disciplined, but Plan 02-03's core "BACK-03 compliance" claim is the single biggest shared risk, and Plan 02-02's OpenShift container/verification mechanics have real execution gaps the internal plan-checker (3 passes) did not catch.

### Agreed Strengths
- Strong Phase 1 pattern reuse (`verify-routing.sh` style, OpenShift manifest conventions, ConfigMap contract) — Gemini, Cursor.
- Correct, non-obvious identification of the `mcp` SDK vs. standalone `fastmcp` package divergence — Gemini, Ollama.
- Good scope discipline: scaffolding-only for device config/allowlists, explicit deferral of real device wiring — Gemini, Cursor.
- Sound use of mtime-polling over inotify for ConfigMap watching, given Kubernetes' atomic symlink-swap behavior — Gemini, Ollama.

### Agreed Concerns (raised by 2+ reviewers — highest priority)
1. **`client.base_url` mutation propagating through `FastMCP.from_openapi()` is unvalidated (HIGH — Gemini, Cursor, Ollama — unanimous).** All three reviewers independently flagged exactly the gap this phase's plan-checker already identified and explicitly deferred to Phase 3 via a STATE.md entry (see 02-03-PLAN.md must_haves and `.planning/STATE.md`). This is now corroborated by three independent reviews plus the internal plan-checker — treat the existing STATE.md flag-forward as confirmed-important, not speculative, and make it a first-priority item when Phase 3 is planned.
2. **OpenShift arbitrary-UID / container write-permission risk in the Dockerfile (HIGH/MEDIUM — Gemini, Cursor).** `USER mcpuser` alone does not satisfy OpenShift's random-UID-in-root-group execution model; if the patched server (or `uv run`, or Python's `__pycache__`) needs to write anywhere, it will hit `Permission denied` at deploy time. Gemini's concrete fix (`chgrp -R 0 /app && chmod -R g=u /app`) is actionable and should be applied to 02-02-PLAN.md's Dockerfile task before execution — this is a correctness gap the internal review passes missed entirely.

### Divergent / Single-Reviewer Findings (worth triaging, not unanimous)
- **CAMARA smoke test cannot prove operation filtering works (Cursor, HIGH).** `camara_location_verification.yaml` exposes exactly one operation, so a broken allowlist filter would still "pass" the smoke test. This directly undercuts D-12/D-14's intent (prove the CLI does selective operation exposure, not just "doesn't crash"). Worth a lightweight fix: add a tiny synthetic 2-operation OpenAPI fixture to the test suite alongside the real CAMARA smoke test.
- **`str.format()` in the inline codegen template will break on literal `{`/`}` in generated Python (Gemini, HIGH).** If the generated `server.py` scaffold needs to emit any dict/set/f-string syntax, `str.format()` requires doubling every brace — a real and easily-triggered bug. Gemini's suggested fix (`string.Template` with `$var` substitution) avoids the problem without adding a Jinja2 dependency, consistent with 02-03-PLAN.md's own stated rationale for not using a `.j2` file.
- **`uv.lock` / dependency-ordering gap between 02-01 and 02-02 (Cursor, HIGH).** 02-01 swaps `mcp[cli]` for `fastmcp` but doesn't say how `uv.lock` gets regenerated; 02-02 assumes `uv sync --frozen` works against that lockfile. A legitimate plan-to-plan contract gap.
- **"First discovered tool" verification heuristic in `verify-mcp-telecom.sh` is brittle (Cursor, HIGH).** The already-revised dynamic-tool-discovery fix (addressing the internal checker's blocker about hardcoded tool names) may still fail for tools with complex required/nested schema fields that can't be synthesized generically from `inputSchema` alone.
- **Generated scaffold's spec-path resolution may break when run from `/tmp` (Cursor, HIGH).** If the smoke test writes the generated server to `/tmp/camara_server.py` while the scaffold resolves the spec path relative to its own location, the two can diverge unless the CLI rewrites to an absolute path.
- Minor/lower-confidence suggestions not acted on here: exact FastMCP version pinning (Ollama), OpenAPI spec pre-validation via `openapi-spec-validator` (Ollama), vendoring commit-SHA pinning for MCP-Telecom (Cursor), readiness-probe semantic mismatch between `/healthz` and "MCP endpoint response" framing (Cursor).

