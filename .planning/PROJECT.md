# OTel 2.5 Telecom Tool-Calling Training

## What This Is

MCP tool infrastructure and SDG (synthetic data generation) pipeline to produce telecom-specific tool-calling training data for fine-tuning OTel 2.0 into OTel 2.5. Starting with the fault prediction use case, then expanding to churn, revenue recovery, energy optimization, and closed-loop automation. The training data and pipeline are the deliverable — Farbod's team at OpenTelco runs the actual OSFT training.

Part of the LFN Applied Observability for AIOps Working Group. Ravi Sharma (Red Hat) is Technical Lead; Fatih Nar (Red Hat) is Vice Chair.

## Core Value

OTel 2.5 can correctly call telecom tools (TMF, CAMARA, NWDAF) to complete fault prediction workflows — measured by improvement on ZTE-AIM/TFCE benchmark over OTel 2.0.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Build ~20 new MCP tools for fault prediction (TMF642 alarm mgmt, TMF628 performance, TMF621 trouble ticket, NWDAF TS 29.520 analytics, CAMARA Device Location)
- [ ] Integrate MCP-Telecom (60+ tools, MIT) for infrastructure/device layer fault data
- [ ] Deploy MCP servers and sandbox backends on OpenShift
- [ ] Build SDG pipeline: teacher model generates tool-calling examples from MCP tool schemas
- [ ] Execute SDG with three-tier backend verification (NextGCore live, operator sandboxes, Prism mocks)
- [ ] Produce 8,500-14,000 training examples, filter to 5,000-10,000 high quality
- [ ] Baseline OTel 2.0 on ZTE-AIM/TFCE and GSMA benchmarks (no published scores exist)
- [ ] Deliver training dataset + pipeline to Farbod's team for OSFT
- [ ] Create industry gaps document (MCP conformance testing, standard telco API simulators, agent deployment reference architecture on OpenShift)

### Out of Scope

- Running the actual OSFT training on OTel 2.0 — Farbod's team owns this
- Gaps 2-9 (operational data, vendor CLI, IETF RFCs, OSS/BSS workflows, autonomous task completion, MOP validation, network security ops, vision tower) — planned for later phases, not this project cycle
- Production deployment of OTel 2.5 at any operator — WG produces the model, operators deploy
- Building a new 5G core — we use existing open-source cores (NextGCore, Open5GS, Free5GC) as sandboxes

## Context

- **OTel 2.0**: 31B param model (Gemma 4 base, OSFT with ~440B telecom tokens). Knows standards deeply but has zero tool-calling training data for telecom APIs. No published benchmark scores.
- **9 gaps identified** in the model card — tool calling is gap 1, the narrowest and most achievable. Full gap analysis in `OTel_2.5_MCP_and_Data_Landscape.md`.
- **Existing MCP landscape**: MCP-Telecom (60+ device-layer tools, MIT), mcp-camara-demo (3 tools, demo only), Telco-AIX AutoNet (Fatih Nar, in development). No BSS/OSS MCP tools exist — TMF642, TMF628, NWDAF need to be built.
- **SDG methodology**: NVIDIA NeMo NOC reasoning pipeline (fully reproducible, Apache 2.0) for multi-step data. 6GAgentGym (methodology reference, no public code). ToolBench/APIGen for general patterns.
- **Eval benchmarks**: ZTE-AIM/TFCE (917 problems, English, held out), GSMA Open Telco Benchmarks (16,866 samples), TelAgentBench (Korean, structural reference), BFCL V4 Agentic.
- **Sandbox environments**: fenar/cnvopen5gcore (OpenShift-native), NextGCore (Docker Compose, NWDAF), Free5GC (Helm), operator sandboxes (GSMA Open Gateway, Vodafone, BT).
- **Research already done**: `gaps/gap-1-tool-calling/mcp_toolkit_audit.md` and `gaps/gap-1-tool-calling/fault_prediction_api_map.md` contain detailed API mapping and toolkit analysis.

## Constraints

- **Platform**: Must deploy on OpenShift. Red Hat tools and platforms preferred.
- **License**: AGPL-3.0 components (NextGCore, Open5GS) used as sandbox tools only, not shipped as WG deliverables. Apache 2.0 for any code in deliverables.
- **Timeline**: Fault prediction dataset ready by October 15, 2026.
- **Model scope**: Training data and pipeline only. OSFT training owned by Farbod/OpenTelco team.
- **Use case sequencing**: Fault prediction first (narrowest API surface), then expand to other 4 WG use cases.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Start with fault prediction use case | Narrowest API surface (TMF642 + TMF628 + NWDAF), proven SDG pipeline (NeMo), clear eval (ZTE-AIM/TFCE) | — Pending |
| Two-track MCP approach: MCP-Telecom (device layer) + build new BSS/OSS tools | MCP-Telecom already covers infrastructure; BSS/OSS layer (TMF, NWDAF, CAMARA) has no existing MCP servers | — Pending |
| Training data + pipeline as deliverable, not trained model | WG produces data, Farbod's team runs OSFT. Separation of concerns. | — Pending |
| Conformance test suite over formal MCP certification | Test suite gets 80% of value at 10% of overhead. Certification can come later. | — Pending |
| Separate industry gaps doc from training project | Gaps (MCP conformance, telco API simulators, agent deployment ref arch) are strategic, not tied to Oct 15 deadline | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-26 after initialization*
