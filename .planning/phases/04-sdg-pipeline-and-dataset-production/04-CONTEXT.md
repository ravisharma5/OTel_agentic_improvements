# Phase 4: SDG Pipeline and Dataset Production - Context

**Gathered:** 2026-10-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Run the `sdg_hub` MCP distillation pipeline against the Phase 3 MCP Gateway to generate, execution-verify, and quality-filter 5,000-10,000 tool-calling training examples, then deliver the dataset plus a runnable recipe (notebooks + production scripts) to Farbod's team in Training Hub's OSFT-compatible JSONL format. Before generation can run against "live backends" as the roadmap requires, this phase must also close three backend-readiness gaps inherited from Phases 1-3: wire a real (simulated) device backend for MCP-Telecom, fix NWDAF's live-verification blocker, and fix Prism's unrealistic mock data. This phase does NOT run the actual OSFT training (Farbod's team owns that), does NOT build the industry gaps document (Phase 5), and does NOT expand to other WG use cases (v2 scope).

</domain>

<decisions>
## Implementation Decisions

### SDG Framework: sdg_hub
- **D-01:** "sdg_hub" in ROADMAP.md/REQUIREMENTS.md (SDG-01) refers to the **Red Hat AI Innovation Team's `sdg_hub`** project (`github.com/Red-Hat-AI-Innovation-Team/sdg_hub`) — NOT NeMo Data Designer, which is what Phase 1's original stack research (`.planning/research/STACK.md`, `SUMMARY.md`) recommended before this roadmap decision was locked in. This is a correction analogous to Phase 3's RHCL-vs-FastMCP gateway correction (`03-CONTEXT.md` D-01): treat NeMo Data Designer references in prior research as **superseded** for the SDG framework choice specifically.
- **D-02:** Phase 4 uses **both** of sdg_hub's agentic example flows: `examples/agentic/mcp_distillation_training` generates raw tool-calling traces, and `examples/agentic/mcp_distillation_evaluation` performs the three-stage verification (format, execution, semantic) named in the roadmap's success criterion #1.
- **D-03:** sdg_hub is **installed as a pinned pip dependency** in the recipe/notebook environment, not vendored into this repo. No patching of sdg_hub's source is expected — the two example flows are used as-provided, configured to point at this project's MCP Gateway and teacher model.
- **D-04:** The automated OSFT-schema validation step (see D-14) is implemented **inside sdg_hub's `mcp_distillation_evaluation` flow** — extend/configure its quality-filtering stage to also check OSFT schema compliance, rather than building a separate standalone validator script.

### Delivery Shape: Recipes, Not Just a Dataset
- **D-05:** The Phase 4 deliverable to Farbod's team is **not just the filtered JSONL dataset** — it is a runnable recipe: **Jupyter notebooks** for exploration/dry-run plus a **scripted, repeatable production pipeline** for the real 8,500-14,000 example generation run.
- **D-06:** The dry-run and production pipeline run on a **separate OpenShift AI (RHOAI) cluster** — not the existing cluster running Phases 1-3's backends (`otel25-backends`, `otel25-mcp`, the RHCL gateway namespace). This separate cluster is where Gemma 4 (D-11) is served via vLLM and where the notebooks execute.
- **D-07:** The separate cluster's pipeline authenticates to the existing JWT/Keycloak-protected MCP Gateway by **reusing the existing Keycloak client-credentials flow** that Phase 3 built — no new auth infrastructure. The gateway's Route must be reachable from the separate cluster (confirm/expose externally during research if not already).

### Teacher Model
- **D-08:** The teacher model is **Gemma 4 31B dense** (Apache 2.0), not Qwen3-series as originally researched. Chosen over Qwen3.8-27B specifically because Gemma 4 has no "thinking"/extended-reasoning overhead, and its July 2026 mid-cycle refresh showed its **largest agentic benchmark gain on Tau2 Telecom (+10.10%)** for the 31B size — directly in this project's domain. It also matches OTel 2.0's own base model family (31B Gemma 4, per PROJECT.md), giving the project pre-existing familiarity with this model family.
- **D-09:** vLLM serves Gemma 4 with `--enable-auto-tool-choice --tool-call-parser gemma4` (vLLM's native Gemma 4 tool-call parser — note Gemma 4 uses a custom non-JSON serialization for tool calls, requiring this specific parser, not a generic one).
- **D-10:** GPU access for the separate OpenShift AI cluster is **already available** — Phase 4's work is deploying vLLM + Gemma 4 there, not acquiring GPU hardware/quota from scratch.
- **D-11 (Claude's discretion, flagged):** Whether the semantic judge (quality-filtering stage) reuses the same Gemma 4 instance or a separate model/instance is left to the planner, informed by what `mcp_distillation_evaluation`'s default configuration expects.

### Backend Readiness Prerequisites (block "live backend" verification per success criterion #1)
- **D-12:** **MCP-Telecom device backend:** Stand up a **Containerlab** simulated network device topology (not a lightweight mock SSH/CLI target) so MCP-Telecom's 58 device-layer tools get real responses instead of connection errors. **Major finding during discussion: this is not new work from scratch** — Phase 2 already built `mcp/mcp-telecom/src/mcp_telecom/containerlab.py` (a full Containerlab topology generator with vendor→kind mappings for Nokia/Cisco/Juniper/Arista) and `tests/test_containerlab.py`, anticipating exactly this. Phase 4's job is to actually deploy a Containerlab topology using this existing generator, not build the generator itself.
- **D-13:** **Security gaps CR-01/02/03** (dormant since Phase 2's code review, `02-REVIEW.md`) must be **fixed as a Phase 4 prerequisite**, before the Containerlab device backend goes live — since fixing them is what makes the device backend safe to wire at all:
  - CR-01: enforce `command_allowlist.yaml`'s deny-by-default guarantee for real in `run_command`'s validation path (currently only `safety.py`'s independent regex check gates execution; the allowlist file is not consulted). See `mcp/mcp-telecom/src/mcp_telecom/safety.py:64` (`validate_command`) and `mcp/mcp-telecom/command_allowlist.yaml`.
  - CR-02: sanitize `show_interface_detail`'s `interface` argument before it's formatted into a vendor CLI template and sent over SSH (command-injection path). See `mcp/mcp-telecom/src/mcp_telecom/tools/interfaces.py`.
  - CR-03: contain `compare_configs`' `backup_file` argument to the `backups/` directory before calling `Path(...).read_text()` (arbitrary local file read). See `mcp/mcp-telecom/src/mcp_telecom/server.py:462`.
- **D-14:** **Device inventory & command allowlist:** Populate `mcp/mcp-telecom/devices.yaml.example` → `devices.yaml` with real Containerlab-provisioned device targets (per the scaffold's own "replace with real device details in Phase 4" comment), and populate `command_allowlist.yaml`'s `allowed_commands` list with real permitted commands (fixing CR-01's enforcement gap at the same time, since the scaffold's comment already anticipates this exact Phase 4 task).
- **D-15:** **NWDAF live verification:** Fix the **HTTP/2 h2c incompatibility** blocking semantic verification of NWDAF's 3 tools against live NextGCore (`STATE.md` Blockers — NextGCore's NWDAF API serves h2c, httpx2 client sends HTTP/1.1, fails with "illegal request line"). Add an h2c-capable client/transport rather than building a new Prism NWDAF mock — this gets NWDAF tools true live-backend semantic verification, matching the rigor of the other tools.
- **D-16:** **Prism mock realism:** Enrich the vendored OpenAPI specs (TMF642, TMF628, TMF621, CAMARA verify/retrieve) with realistic `example` values pulled from TM Forum user guides, **before** any SDG generation run — per `01-CONTEXT.md` D-08's original (until-now-deferred) mitigation for Prism's Lorem-Ipsum-style dynamic mock data. This is a Phase 4 prerequisite, not a "generate and tag by tier" workaround.
- **D-17:** **Backend-routing ConfigMap consolidation:** Fix the two-unsynced-copies problem (`otel25-backends/backend-routing` and `otel25-mcp/backend-routing`, flagged in Phase 3's `03-CONTEXT.md`/STATE.md) by consolidating to a **single source of truth**, since Phase 4 is already touching NWDAF's routing config (D-15) and adding new device-backend config (D-12/D-14) — fix the sync problem now rather than continuing to patch two copies by hand.

### OSFT Delivery Format
- **D-18:** The OSFT JSONL schema source is **Training Hub** (same Red Hat AI Innovation Team GitHub org as sdg_hub) — not a sample file requested from Farbod's team. Research should read Training Hub's docs/repo for the `messages`/`tool_calls`/`tool_call_id` structure OSFT (via mini-trainer) expects.
- **D-19:** Despite trusting Training Hub's documented format, still do the **early dry-run validation** from `PITFALLS.md` Pitfall #5's mitigation: generate ~10 examples early and have Farbod's team confirm before committing to the full 8,500-14,000 example run.
- **D-20:** Both trajectory formats from success criterion #2 (single-turn and multi-turn) are **delivered to Farbod's team** — package both JSONL variants in the final handoff; the training team decides what to train on, rather than Phase 4 picking one as "the real deliverable."

### Claude's Discretion
- Exact field-level schema of the OSFT-compliance check added inside `mcp_distillation_evaluation` (D-04), as long as it validates `tool_call_id` threading per Training Hub's documented format.
- Whether the semantic judge reuses the Gemma 4 instance or runs separately (D-11).
- Exact Containerlab topology shape (device count, vendor mix) — informed by what `containerlab.py`'s existing vendor support (Nokia/Cisco/Juniper/Arista) and MCP-Telecom's tool set actually need.
- Curriculum/seed taxonomy specifics for success criterion #2's ordering (single-tool → parallel → sequential → multi-turn → closed-loop) — research question, not locked by this discussion.
- Exact mechanics of exposing the MCP Gateway Route externally for the separate-cluster pipeline (D-07), if not already externally reachable from Phase 3.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### SDG framework (MANDATORY — supersedes STACK.md/SUMMARY.md's NeMo Data Designer recommendation for the framework choice itself)
- `https://github.com/Red-Hat-AI-Innovation-Team/sdg_hub` — the SDG framework itself (D-01).
- `https://github.com/Red-Hat-AI-Innovation-Team/sdg_hub/tree/main/examples/agentic/mcp_distillation_training` — generation flow (D-02).
- `https://github.com/Red-Hat-AI-Innovation-Team/sdg_hub/tree/main/examples/agentic/mcp_distillation_evaluation` — three-stage verification flow (D-02, D-04).
- `https://github.com/Red-Hat-AI-Innovation-Team` — org root; also hosts Training Hub (D-18).

### OSFT / Training Hub (MANDATORY — resolves PITFALLS.md Pitfall #5)
- Training Hub repo/docs under `https://github.com/Red-Hat-AI-Innovation-Team` — researcher must locate and read the exact `messages`/`tool_calls` JSONL schema OSFT (mini-trainer backend) expects (D-18).
- `.planning/research/PITFALLS.md` Pitfall #5 — "Training data format incompatible with OSFT expectations" — background risk and original mitigation plan, now superseded by D-18/D-19's Training-Hub-first approach.

### Teacher model (vLLM + Gemma 4)
- vLLM's Gemma 4 announcement/docs — `--enable-auto-tool-choice --tool-call-parser gemma4` serving configuration (D-09). Researcher should fetch current vLLM docs for exact flags/version requirements.
- Gemma 4 model card (Google AI for Developers) — 31B dense specs, July 2026 refresh Tau2 Telecom benchmark gains (D-08).

### Backend-readiness prerequisites (MANDATORY — these gate success criterion #1's "live backends" requirement)
- `mcp/mcp-telecom/src/mcp_telecom/containerlab.py` — existing Containerlab topology generator (vendor→kind mappings); Phase 4 deploys a topology using this, does not build it from scratch (D-12).
- `mcp/mcp-telecom/tests/test_containerlab.py` — existing tests for the generator above.
- `mcp/mcp-telecom/devices.yaml.example` — device-inventory scaffold with explicit "replace with real device details in Phase 4" comment (D-14).
- `mcp/mcp-telecom/command_allowlist.yaml` — command-allowlist scaffold with explicit "Phase 4 populates this... when wiring real network devices" comment (D-14).
- `mcp/mcp-telecom/src/mcp_telecom/safety.py:64` (`validate_command`) — CR-01's enforcement gap (D-13).
- `mcp/mcp-telecom/src/mcp_telecom/tools/interfaces.py` — `show_interface_detail`, CR-02's injection path (D-13).
- `mcp/mcp-telecom/src/mcp_telecom/server.py:462` (`compare_configs`) — CR-03's arbitrary file read (D-13).
- `.planning/phases/02-mcp-tooling-foundation/02-REVIEW.md` — full CR-01/02/03 findings and original recommendations.
- `backends/openshift/configmap-backend-routing.yaml` and the `otel25-mcp` copy referenced in `03-CONTEXT.md` — the two-copies ConfigMap problem (D-17).
- `.planning/research/PITFALLS.md` Pitfall #3 (Prism unrealistic responses) and Pitfall #6 (NextGCore NWDAF risk) — ground D-15/D-16.
- `.planning/STATE.md` "Blockers/Concerns" section — NWDAF h2c failure detail, MCP-Telecom no-device-backend flag, ConfigMap two-copies flag, CR-01/02/03 flag-forward — all directly actioned by this phase's decisions.

### Phase 1-3 contracts this phase must honor
- `.planning/phases/03-mcp-domain-servers-and-gateway/03-CONTEXT.md` — RHCL gateway identity, per-domain Virtual MCP Servers, JWT/Keycloak auth setup (D-07 reuses this), MCPVirtualServer re-reconciliation risk (note if any `MCPServerRegistration` changes are made for D-12/D-14, re-merge `virtualServers` into `otel25-gateway/mcp-gateway-config` per Phase 3's documented workaround).
- `.planning/phases/02-mcp-tooling-foundation/02-CONTEXT.md` — D-07/D-09/D-10/D-10a (MCP-Telecom's deferred device backend and scaffolds, now being actioned by D-12/D-14).
- `.planning/phases/01-backend-infrastructure/01-CONTEXT.md` — D-08 (Prism realism caveat, actioned by D-16).
- `gateway/openshift/` — existing RHCL gateway manifests (AuthPolicy, Keycloak, MCPServerRegistration/MCPVirtualServer CRs) the separate cluster's pipeline must authenticate against (D-07).

### Project-level constraints
- `.planning/PROJECT.md` — "Constraints": Oct 15, 2026 deadline, Red Hat tools preferred (sdg_hub/Training Hub/Gemma 4/OpenShift AI all satisfy this), Apache 2.0 for deliverables we author.
- `.planning/REQUIREMENTS.md` — SDG-01 through SDG-05 (this phase's requirements).
- `.planning/ROADMAP.md` — Phase 4 success criteria (sdg_hub distillation with three-stage verification, curriculum ordering + dual trajectory format, 5K-10K filtered from 8.5K-14K raw, OSFT delivery).

No SPEC.md exists for this phase.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mcp/mcp-telecom/src/mcp_telecom/containerlab.py` — Containerlab topology generator already built in Phase 2, anticipating this exact Phase 4 need (vendor→kind mapping for Nokia SR OS/SR Linux, Cisco IOS-XR/IOS/NX-OS, Juniper Junos, Arista EOS).
- `mcp/mcp-telecom/devices.yaml.example` and `command_allowlist.yaml` — scaffolds explicitly written in Phase 2 to be filled in during Phase 4.
- The Phase 3 RHCL MCP Gateway (`gateway/openshift/`) — the single endpoint sdg_hub's pipeline calls against instead of hitting individual domain servers, already JWT-authenticated via Keycloak.
- `scripts/verify-gateway.sh`, `scripts/verify-domain-tools.sh`, `scripts/verify-mcp-telecom.sh` — existing verification-script patterns this phase's own verification work (e.g. confirming the h2c fix, confirming Containerlab devices respond) should follow stylistically.

### Established Patterns
- Vendoring over installing-as-dependency has been this project's default for things needing patches (Prism specs, MCP-Telecom itself) — explicitly broken here (D-03) because sdg_hub doesn't need patching, just configuration.
- Namespace-per-layer (`otel25-backends`, `otel25-mcp`, RHCL gateway namespace) — Phase 4 introduces a genuinely new deployment target (separate OpenShift AI cluster) rather than extending this pattern, a first for this project.
- Flag-forward-to-Phase-4 pattern — Phases 1-3 consistently deferred known gaps (Prism realism, MCP-Telecom device backend, NWDAF h2c, security gaps, ConfigMap sync) to "whichever phase needs it." Phase 4 is that phase for all five, and this discussion converted every one of them into an explicit, locked decision rather than leaving them implicit.

### Integration Points
- sdg_hub's `mcp_distillation_training`/`mcp_distillation_evaluation` flows call the MCP Gateway's single endpoint (not individual domain servers), authenticating via the reused Keycloak client-credentials flow (D-07).
- The Containerlab-backed MCP-Telecom deployment must have its device-routing config added to whatever single-source-of-truth ConfigMap replaces the two unsynced copies (D-17).
- The separate OpenShift AI cluster's vLLM/Gemma 4 endpoint is called by sdg_hub's training flow as the teacher model (OpenAI-compatible API, per the original architecture pattern still valid from `ARCHITECTURE.md` Pattern 5).

</code_context>

<specifics>
## Specific Ideas

- sdg_hub is specifically the Red Hat AI Innovation Team's project — user supplied the exact org and example-flow paths.
- Gemma 4 31B dense as teacher model, chosen partly because its July 2026 refresh showed outsized Tau2 Telecom gains and partly to avoid Qwen3.8's thinking-mode latency.
- "Recipes" (notebooks + production scripts) for Farbod's team to run themselves — not just a static dataset handoff.
- Containerlab for the device simulator — validated by discovering Phase 2 already built the topology-generator code for exactly this.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Extending to other WG use cases (churn, revenue recovery, energy optimization, closed-loop), the industry gaps document (Phase 5), and the actual OSFT training run were all reaffirmed as out of this phase's scope, not pulled forward.

</deferred>

---

*Phase: 4-SDG Pipeline and Dataset Production*
*Context gathered: 2026-10-05*
