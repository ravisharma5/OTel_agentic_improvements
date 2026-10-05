# Phase 4: SDG Pipeline and Dataset Production - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-05
**Phase:** 4-SDG Pipeline and Dataset Production
**Areas discussed:** SDG framework (sdg_hub), Backend readiness & tool scope, OSFT delivery format status, Teacher model hosting

---

## SDG framework: sdg_hub specifics

| Option | Description | Selected |
|--------|-------------|----------|
| IBM/Red Hat SDG Hub (instructlab-sdg successor) | The open-source `sdg_hub` package | |
| Something else — let me specify | — | ✓ |
| Not sure — research it | — | |

**User's choice:** Confirmed via freeform follow-up: Red Hat AI Innovation Team's `sdg_hub` (github.com/Red-Hat-AI-Innovation-Team/sdg_hub), with `examples/agentic/mcp_distillation_training` and `examples/agentic/mcp_distillation_evaluation` as the relevant flows. The org also hosts Training Hub.
**Notes:** Corrects Phase 1 research (STACK.md/SUMMARY.md), which recommended NeMo Data Designer — that recommendation predates this roadmap decision, same pattern as Phase 3's RHCL correction.

| Option | Description | Selected |
|--------|-------------|----------|
| Both — training flow generates, evaluation flow verifies | — | ✓ |
| Training flow only | — | |
| Not sure — researcher determines split | — | |

**User's choice:** Both.

**Vendoring/install sub-thread:**
- Initial question (vendor vs. pip dependency) surfaced a bigger scope item via freeform answer: deliverable is "recipes" for Farbod's team — dry run on a separate OpenShift AI cluster using Jupyter notebooks.
- Follow-up: cluster is **separate** from Phases 1-3's backend cluster.
- Follow-up: recipes are **both** notebooks (dry-run) and scripted production pipeline.
- Follow-up: sdg_hub installed as **pinned pip dependency** (not vendored).
- Follow-up: pipeline on the separate cluster authenticates to the MCP Gateway by **reusing the existing Keycloak client-credentials flow**.

**Additional follow-up:** OSFT schema-validation step lives **inside sdg_hub's `mcp_distillation_evaluation` flow**, not as a separate custom validator.

---

## Backend readiness & tool scope

| Option | Description | Selected |
|--------|-------------|----------|
| Exclude — scope to 20 BSS/OSS tools only | — | |
| Include, but stand up a device simulator first | — | ✓ |
| Include with intentional error-scenario examples only | — | |

**User's choice:** Include MCP-Telecom's 58 device-layer tools, but stand up a device simulator first.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — fix CR-01/02/03 as a Phase 4 prerequisite | — | ✓ |
| No — defer to dedicated gap-closure phase | — | |
| Claude's discretion | — | |

**User's choice:** Fix CR-01/02/03 as a Phase 4 prerequisite.

| Option | Description | Selected |
|--------|-------------|----------|
| Fix the h2c client issue first | — | ✓ |
| Build a Prism mock for NWDAF | — | |
| Claude's discretion | — | |

**User's choice:** Fix the h2c client issue first.

| Option | Description | Selected |
|--------|-------------|----------|
| Enrich OpenAPI specs with realistic example values first | — | ✓ |
| Generate anyway, tag by backend tier | — | |
| Claude's discretion | — | |

**User's choice:** Enrich specs first.

| Option | Description | Selected |
|--------|-------------|----------|
| Containerlab | — | ✓ |
| Lightweight mock SSH/CLI target | — | |
| Claude's discretion | — | |

**User's choice:** Containerlab.
**Notes:** Discovered during this discussion that Phase 2 already built `mcp/mcp-telecom/src/mcp_telecom/containerlab.py` (topology generator) and `tests/test_containerlab.py` — the Containerlab choice validates/completes existing scaffolding rather than introducing new tooling.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — consolidate to a single source of truth | — | ✓ |
| No — keep patching both manually | — | |
| Claude's discretion | — | |

**User's choice:** Consolidate the two unsynced backend-routing ConfigMap copies.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — populate device-inventory and allowlist with real Containerlab targets | — | ✓ |
| Claude's discretion | — | |

**User's choice:** Populate for real, fixing CR-01's enforcement gap in the process.

---

## OSFT delivery format status

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, I have it / can get it from Farbod's team now | — | |
| No, but Training Hub's docs likely define it | — | ✓ |
| No — still outstanding, treat as blocking | — | |

**User's choice:** Training Hub's docs likely define the format (same GitHub org as sdg_hub).

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — generate 10 examples early and validate with Farbod's team | — | ✓ |
| No — trust Training Hub's docs, skip the check-in | — | |
| Claude's discretion | — | |

**User's choice:** Still do the 10-example dry-run validation (belt-and-suspenders with D-18).

| Option | Description | Selected |
|--------|-------------|----------|
| Inside sdg_hub's evaluation flow | — | ✓ |
| Separate custom validator script | — | |
| Claude's discretion | — | |

**User's choice:** Inside sdg_hub's evaluation flow.

| Option | Description | Selected |
|--------|-------------|----------|
| Both delivered — Farbod's team decides what to train on | — | ✓ |
| Multi-turn is the real deliverable; single-turn is intermediate | — | |
| Claude's discretion / confirm with Training Hub docs | — | |

**User's choice:** Both trajectory formats delivered.

---

## Teacher model hosting

| Option | Description | Selected |
|--------|-------------|----------|
| API-based teacher (GPT-4.1 / Claude Sonnet) | — | |
| Self-hosted vLLM on OpenShift GPU | — | ✓ |
| Claude's discretion / research question | — | |

**User's choice:** Self-hosted vLLM on OpenShift GPU.

| Option | Description | Selected |
|--------|-------------|----------|
| Same OpenShift AI cluster as the notebooks | — | ✓ |
| Existing Phases 1-3 cluster | — | |
| Claude's discretion | — | |

**User's choice:** Same OpenShift AI cluster as the notebooks.

| Option | Description | Selected |
|--------|-------------|----------|
| I have GPU access already — just need it deployed | — | ✓ |
| Not provisioned yet | — | |
| Not sure — flag as research question | — | |

**User's choice:** GPU access already available.

**Model selection sub-thread (freeform, research-assisted):**
- User expressed uncertainty about deploying Qwen3-72B and asked for alternatives in the "32B range," noting the originally-discussed models were outdated.
- Claude researched current (Oct 2026) 32B-class options via web search: Qwen3.8-27B (current Qwen successor), Qwen3-Next-80B-A3B (efficient MoE).
- User asked specifically about Gemma 4, noting Qwen3.8 has long "thinking" overhead.
- Claude researched Gemma 4 (released April 2026, July 2026 mid-cycle refresh): native function-calling via vLLM's `gemma4` tool-call parser, no thinking-mode overhead, July 2026 refresh showed +10.10% Tau2 Telecom gain for the 31B size — directly relevant to this project's domain. Also noted OTel 2.0 itself is a 31B Gemma 4 base model.

| Option | Description | Selected |
|--------|-------------|----------|
| Gemma 4 31B dense (recommended) | — | ✓ |
| Gemma 4 26B MoE (A4B) | — | |
| Claude's discretion / confirm at research time | — | |

**User's choice:** Gemma 4 31B dense.

---

## Claude's Discretion

- Exact field-level schema of the OSFT-compliance check inside `mcp_distillation_evaluation`.
- Whether the semantic judge reuses the Gemma 4 instance or runs separately.
- Exact Containerlab topology shape (device count, vendor mix).
- Curriculum/seed taxonomy specifics for the single-tool → parallel → sequential → multi-turn → closed-loop ordering.
- Exact mechanics of exposing the MCP Gateway Route externally for the separate-cluster pipeline, if not already externally reachable.

## Deferred Ideas

None — discussion stayed within phase scope.
