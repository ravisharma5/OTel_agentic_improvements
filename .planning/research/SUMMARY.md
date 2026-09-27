# Project Research Summary

**Project:** OTel 2.5 Telecom Tool-Calling Training Data Pipeline
**Domain:** Synthetic data generation for telecom-domain LLM tool-calling fine-tuning
**Researched:** 2026-09-26
**Confidence:** HIGH

## Executive Summary

This project builds a pipeline that generates high-quality synthetic training data for telecom tool-calling, enabling OTel 2.0 to be fine-tuned (via OSFT) into OTel 2.5 with fault-prediction capabilities across TMF, NWDAF, and CAMARA APIs. The established approach -- validated by NVIDIA's NeMo NOC reasoning pipeline and Salesforce's APIGen methodology -- is a batch SDG pipeline where a teacher model generates tool-calling traces from curated MCP tool definitions, each trace is execution-verified against real or mock backends, and a quality pipeline filters down to 5,000-10,000 production-grade training examples. The recommended stack is Python-native throughout: FastMCP 4.x for MCP servers (with OpenAPI-to-MCP conversion), NeMo Data Designer for the SDG pipeline framework, vLLM for self-hosted teacher model inference, and Prism for auto-mocking TMF APIs from their OpenAPI specs. Total SDG cost is estimated at $150-300.

The architecture is a four-layer system on OpenShift: domain-separated MCP servers composed behind a FastMCP gateway, a backend tier mixing Prism mocks with NextGCore's live NWDAF, a GPU inference tier running vLLM, and a batch pipeline orchestrator that chains seed generation through verification and filtering. The most critical architectural decision is domain separation of MCP servers -- keeping each API family (TMF, NWDAF, CAMARA, infrastructure) in its own process behind a composition gateway, which prevents the tool-count bloat that degrades LLM tool selection accuracy above 50 tools.

The top risks are: (1) teacher models hallucinating telecom-specific enumeration values (TMF's `g_5mn` vs ISO 8601's `PT5M`), mitigated by execution verification against validating backends; (2) mode collapse producing repetitive training examples, mitigated by diverse prompt taxonomies and coverage tracking; (3) NextGCore's NWDAF being "configured but not exercised" in practice, mitigated by early validation and enriched mock fallbacks; and (4) the Oct 15 deadline leaving zero slack for format mismatches with the training team's OSFT expectations, mitigated by getting a sample format in week 1 and doing a dry-run handoff by week 3. The project has a tight but achievable timeline if the critical path (vLLM deployment + MCP gateway) is prioritized and operator sandbox access is treated as bonus rather than dependency.

## Key Findings

### Recommended Stack

The stack is Python-native to match both the existing MCP-Telecom codebase and the SDG pipeline ecosystem. FastMCP 4.x provides the MCP server framework with built-in `from_openapi()` conversion for TMF/NWDAF/CAMARA specs, NeMo Data Designer provides the SDG pipeline framework with YAML-driven column DAGs and native tool-calling SFT output, and vLLM serves open-weight teacher models (Qwen3-72B) with tool-calling support via `--enable-auto-tool-choice`. See [STACK.md](STACK.md) for full details.

**Core technologies:**
- **FastMCP 4.x (Python 3.12):** MCP server framework -- built-in OpenAPI-to-MCP conversion, composition/proxy for gateway pattern, same language as MCP-Telecom and SDG pipeline
- **NeMo Data Designer >=0.6.x:** SDG pipeline framework -- YAML-driven, built-in tool-calling SFT output format, MCP server integration for execution traces, Apache 2.0
- **vLLM >=0.8.3:** Teacher model serving -- tool-calling support with `--enable-auto-tool-choice`, OpenAI-compatible API, GPU-efficient serving for Qwen3-72B
- **Prism 5.x:** Mock TMF APIs -- auto-generates HTTP mocks from OpenAPI specs (OAS 3.0 + Swagger 2.0), dynamic response mode for SDG diversity
- **NextGCore:** Live NWDAF backend -- only open-source 5G core with ONNX-backed NWDAF analytics, provides real TS 29.520 responses
- **GPT-4.1 + Claude Sonnet 4.5:** API teacher models -- GPT-4.1 for structured tool-call generation, Claude Sonnet as semantic judge/validator
- **OpenShift 4.16+ with GitOps 1.19:** Deployment platform -- Red Hat constraint, ArgoCD-based GitOps for all components

**Critical version requirements:**
- FastMCP >=4.0.0 (MCP protocol 2026-07-28)
- vLLM >=0.8.3 (`--enable-auto-tool-choice` flag added in this version)
- Python 3.12 (sweet spot for FastMCP + NeMo Data Designer compatibility)

### Expected Features

See [FEATURES.md](FEATURES.md) for the complete feature landscape with dependency graph.

**Must have (table stakes):**
- MCP tool definitions for all 20 fault-prediction tools (TMF642, TMF628, TMF621, NWDAF, CAMARA) from OpenAPI specs
- Mock backends via Prism (TMF) + live NWDAF via NextGCore for execution verification
- Teacher model SDG generation with APIGen three-stage verification (format, execution, semantic)
- Format-compliant JSONL output in OpenAI chat format with tool_calls structure for OSFT
- Exact and fuzzy deduplication + basic quality filtering
- Volume target: 8,500-14,000 raw examples filtering to 5,000-10,000 high-quality examples

**Should have (differentiators):**
- Telecom-specific complexity tiers (single-tool, correlated, full 6-step workflow) matching NOC escalation patterns
- Error and edge case generation (20-30% of examples) to prevent happy-path-only training
- Curriculum ordering (simple to complex) for OSFT -- 18-45% faster convergence per research
- Telecom-aware semantic judging with domain-specific rubrics
- Diversity metrics tracking tool coverage, parameter combinations, and scenario distribution

**Defer (post-Oct 15):**
- Multi-turn conversation generation (APIGen-MT blueprint approach) -- high value but high complexity
- MCP-Telecom integration for cross-domain scenarios -- adds integration complexity
- Operator sandbox verification (GSMA, Vodafone, BT) -- external dependency, treat as enrichment
- Declarative YAML pipeline configuration -- refactor after batch pipeline proves out

### Architecture Approach

The system follows a four-layer architecture with strict separation of concerns: MCP tool servers handle API definition and proxying, a backend tier provides mock and live API responses, a batch SDG pipeline orchestrates generation through verification and filtering stages, and an inference tier serves teacher models via vLLM. Domain-separated MCP servers are composed behind a FastMCP gateway using `mount()` with namespaces, keeping each server under 20 tools while presenting a unified interface. The SDG pipeline runs as a batch Job with stage-separated output directories (seeds, raw traces, verified traces, filtered dataset), making each stage idempotent and restartable. Backend routing is configuration-driven via ConfigMap environment variables. See [ARCHITECTURE.md](ARCHITECTURE.md) for deployment diagrams and resource estimates.

**Major components:**
1. **MCP Gateway + Domain Servers** -- FastMCP composition layer routing tool calls to TMF, NWDAF, CAMARA, and MCP-Telecom servers
2. **Backend Tier** -- Prism mock servers (TMF642/628/621/CAMARA) + NextGCore (live NWDAF) + optional operator sandboxes
3. **SDG Pipeline Orchestrator** -- Batch Job chaining seed generation, teacher inference (vLLM), execution verification (MCP Gateway), semantic judging, quality filtering
4. **Inference Tier** -- vLLM on GPU pods serving teacher model and semantic judge via OpenAI-compatible API

### Critical Pitfalls

See [PITFALLS.md](PITFALLS.md) for all 14 pitfalls with detailed evidence and prevention strategies.

1. **Teacher model hallucinating telecom schemas** -- TMF uses non-obvious enums (`g_5mn` not `PT5M`), NWDAF event IDs are rare in pretraining data. Prevention: execute every generated tool call against validating backends (three-stage verification), inject full OpenAPI specs with enum constraints into teacher prompts, build a telecom enum registry.

2. **Mode collapse in generated examples** -- Teacher models converge on 2-3 dominant patterns (always start with list_alarms). Prevention: define 8-10 distinct fault-prediction entry points, use 15-20 prompt templates per workflow, track tool-call n-gram distribution, flag any sequence appearing in >5% of examples.

3. **Prism mocks producing unrealistic responses** -- TMF's characteristic pattern (name-value pair bags) generates meaningless mock data. Prevention: enrich OpenAPI specs with realistic `example` values from TMF user guides, use NextGCore for NWDAF (not mocks), tag training examples with backend tier for downstream weighting.

4. **TMF spec version ambiguity** -- TMF642 has v4 (Swagger 2.0) and v5 (OAS 3.0) with breaking differences. Prevention: pin one spec version per API in week 1, validate MCP tools against pinned specs with a linter, build mocks from same pinned specs.

5. **Training data format incompatible with OSFT** -- OSFT requires specific JSONL structure with `tool_call_id` threading. Prevention: get a sample OSFT file from Farbod's team in week 1, build output serializer to that format from day 1, dry-run 10 examples with training team by week 3.

## Implications for Roadmap

Based on dependency analysis across all four research files, the project decomposes into 5 phases. The critical path runs through Phase 1 (vLLM) and Phase 2 (MCP Gateway), which gate Phase 4 (SDG Pipeline). Phases 1a/1b/1c are fully parallelizable.

### Phase 1: Foundation and Platform Setup
**Rationale:** Three independent workstreams with zero inter-dependencies. Front-loads the OpenShift platform work (SCTP, SCCs) that Pitfall #8 warns can consume 2-3 weeks if deferred. Gets vLLM running on GPU, which gates the entire SDG pipeline.
**Delivers:** Running Prism mock servers for TMF642/628/621, vLLM teacher model endpoint, OpenShift platform ready for 5G core components.
**Addresses:** Mock backend responses (table stakes), container deployment (table stakes), health checks (table stakes).
**Avoids:** Pitfall #8 (OpenShift SCTP/SCC blocks), Pitfall #10 (operator sandbox delays -- apply for access in parallel).
**Parallel workstreams:**
- [1a] Prism mock servers from TMF OpenAPI specs
- [1b] MCP-Telecom clone, containerize, test on OpenShift
- [1c] vLLM teacher model deployment on OpenShift AI

### Phase 2: MCP Tool Layer
**Rationale:** Depends on Phase 1a (Prism backends must exist to test tools against). This is where Pitfall #4 (spec version ambiguity) and Pitfall #13 (NWDAF release mismatch) must be resolved -- pin versions before writing any tool definitions. Also resolve Pitfall #5 (OSFT format) by getting a sample from Farbod's team.
**Delivers:** 20 curated MCP tools for fault prediction, MCP Gateway composing all servers, validated against Prism backends.
**Uses:** FastMCP 4.x with `from_openapi()` as scaffolding, then hand-curated tool definitions.
**Implements:** Pattern 1 (domain-separated servers composed via gateway), Pattern 3 (three-tier backend routing via ConfigMap).
**Avoids:** Pitfall #4 (pin spec versions), Pitfall #11 (schema consistency), Pitfall #12 (tool catalog subsetting), Pitfall #13 (audit NextGCore before writing NWDAF tools).

### Phase 3: Backend Upgrade (NextGCore)
**Rationale:** Can proceed in parallel with Phase 4 -- the pipeline can start with Prism-only backends and swap to NextGCore mid-run via ConfigMap changes. However, Pitfall #6 warns that NextGCore NWDAF may be non-functional, so early validation is critical. This phase runs alongside Phase 4, not blocking it.
**Delivers:** Live NWDAF backend replacing Prism mocks for NWDAF tools, enriched Prism mocks with realistic TMF examples.
**Addresses:** Three-tier backend verification (differentiator), live NWDAF backend (table stakes).
**Avoids:** Pitfall #6 (validate NWDAF with curl before depending on it), Pitfall #3 (enrich Prism mocks to prevent unrealistic responses).

### Phase 4: SDG Pipeline
**Rationale:** Depends on Phase 1c (vLLM) and Phase 2 (MCP Gateway with tool definitions). This is the core value delivery. Start with single-tool Tier 1 examples to prove the pipeline end-to-end, then scale to multi-tool Tier 2-3 examples. Must build error scenario generation (Pitfall #9) and diversity tracking (Pitfall #2) into the pipeline from day 1, not as afterthoughts.
**Delivers:** 5,000-10,000 execution-verified, quality-filtered training examples in OSFT-compatible JSONL format with curriculum ordering metadata.
**Uses:** NeMo Data Designer (YAML pipeline), vLLM (teacher inference), MCP Gateway (execution verification), teacher model APIs (semantic judging).
**Implements:** Pattern 2 (batch pipeline with producer-consumer stages), Pattern 4 (APIGen three-stage verification), Pattern 5 (teacher via vLLM OpenAI-compatible API).
**Avoids:** Pitfall #1 (hallucinated schemas -- execution verification), Pitfall #2 (mode collapse -- diverse prompts + tracking), Pitfall #5 (format mismatch -- dry-run by week 3), Pitfall #9 (happy-path only -- 20-30% error scenarios), Pitfall #14 (multi-turn threading -- turn-level validator).
**Sub-stages:**
- [4a] Seed scenario generator (fault-prediction taxonomy, 8-10 entry points)
- [4b] Teacher model trace generator (calls vLLM + MCP tool schemas)
- [4c] Execution verifier (replays tool calls against MCP Gateway)
- [4d] Semantic judge + quality filter + dedup
- [4e] Pipeline orchestrator (chains 4a-4d, writes JSONL + metrics)

### Phase 5: Evaluation and Delivery
**Rationale:** Must baseline OTel 2.0 before OSFT so there is a before/after comparison. The custom fault-prediction eval suite (Pitfall #7) should weight procedural execution tasks 3x higher than linguistic tasks to avoid the "Execution Wall" problem found by TeleCom-Bench.
**Delivers:** Baseline eval scores, packaged JSONL dataset with metadata, delivery to Farbod's team for OSFT.
**Addresses:** Regression detection against ZTE-AIM/TFCE (differentiator), format compliance (table stakes).
**Avoids:** Pitfall #7 (eval not measuring tool-calling -- custom eval suite + execution-weighted scoring).

### Phase Ordering Rationale

- **Phase 1 first** because Prism, vLLM, and OpenShift setup are zero-dependency and every subsequent phase needs at least one of them. Front-loading OpenShift platform work avoids Pitfall #8.
- **Phase 2 before Phase 4** because MCP tool definitions are the input to the SDG pipeline -- without curated tools, there is nothing to generate data for. This is the single hardest dependency in the project.
- **Phase 3 alongside Phase 4** because backend routing is config-driven (Pattern 3). The pipeline can start generating with Prism mocks while NextGCore stabilizes. Swapping backends requires only a ConfigMap change.
- **Phase 4 is the critical delivery phase** and gets the most calendar time. Start with Tier 1 (single-tool) examples to prove the end-to-end pipeline, then scale to Tier 2-3 (multi-tool) examples.
- **Phase 5 last** because eval requires both a trained model (from Farbod's team after receiving the data) and baseline scores (which can be collected in parallel with Phase 4).

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (MCP Tool Layer):** Needs research into exact TMF OpenAPI spec versions available, FastMCP `from_openapi()` behavior with Swagger 2.0 (TMF628), and NextGCore's actual NWDAF analytics events supported (Rel-16 vs Rel-18 gap).
- **Phase 3 (Backend Upgrade):** Needs research into NextGCore deployment on OpenShift -- Docker Compose to k8s conversion, SCC requirements, SCTP configuration. Pitfall #6 and #8 intersect here.
- **Phase 4 (SDG Pipeline):** Needs research into NeMo Data Designer's tool-calling pipeline configuration (YAML schema, validator integration, MCP server hooks). Also needs early coordination with Farbod's team on OSFT format.

Phases with standard patterns (skip deep research):
- **Phase 1 (Foundation):** Prism mock setup, vLLM deployment, and OpenShift basics are well-documented with official guides.
- **Phase 5 (Eval and Delivery):** BFCL v4, ZTE-AIM/TFCE, and GSMA benchmarks have published evaluation frameworks. Standard eval patterns apply.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All core technologies verified against official docs, PyPI releases, and GitHub repos. FastMCP 4.x, NeMo Data Designer, vLLM, and Prism are all production-grade with active maintenance. |
| Features | HIGH | Feature landscape grounded in published methodologies (APIGen, NeMo NOC pipeline, curriculum learning research). Table stakes vs differentiators clearly delineated. |
| Architecture | HIGH | Gateway composition, batch pipeline, and three-tier backend patterns all supported by FastMCP docs, APIGen paper, and NVIDIA NeMo examples. Resource estimates provided. |
| Pitfalls | HIGH | 14 pitfalls identified with evidence from published papers (EdgeGen, TeleCom-Bench, Model Collapse), GitHub issues (NextGCore #192), and practitioner reports (Amartus TMF analysis, TMF628 enum failures). |

**Overall confidence:** HIGH

The research draws from verified primary sources (official documentation, peer-reviewed papers, GitHub repositories) for nearly all recommendations. The few MEDIUM-confidence areas are teacher model selection (benchmark rankings shift frequently) and NextGCore NWDAF maturity (requires hands-on validation).

### Gaps to Address

- **OSFT data format specification:** No authoritative schema found in research. Must obtain a sample file from Farbod's team in week 1 to avoid Pitfall #5.
- **NextGCore NWDAF actual capabilities:** Research indicates NWDAF is "configured but not exercised" in Docker E2E overlays (Pitfall #6). Hands-on validation required in weeks 1-2 before committing to live NWDAF as a backend tier.
- **NeMo Data Designer MCP integration specifics:** Documentation confirms MCP server integration exists, but the exact YAML configuration for tool-calling pipelines with external MCP backends needs hands-on exploration.
- **Operator sandbox onboarding timeline:** GSMA Open Gateway sandbox availability is confirmed, but actual provisioning timeline is unknown. Apply in week 1, plan for mock-only fallback.
- **TMF628 Swagger 2.0 handling:** FastMCP `from_openapi()` supports OAS 3.0. TMF628 v4.0.0 is Swagger 2.0 only. Need to validate the Swagger 2.0 conversion path (via @samchon/openapi or manual conversion to OAS 3.0).

## Sources

### Primary (HIGH confidence)
- [FastMCP 4.0.10 Documentation](https://gofastmcp.com/) -- OpenAPI integration, server composition, proxy pattern
- [NeMo Data Designer](https://github.com/NVIDIA-NeMo/DataDesigner) -- SDG pipeline framework, tool-calling SFT output
- [NVIDIA NeMo Telco NOC Reasoning Pipeline](https://developer.nvidia.com/blog/building-telco-reasoning-models-for-autonomous-networks-with-nvidia-nemo/) -- Directly relevant pipeline pattern
- [APIGen (NeurIPS 2024)](https://apigen-pipeline.github.io/) -- Three-stage verification methodology
- [APIGen-MT (NeurIPS 2025)](https://arxiv.org/abs/2504.03601) -- Multi-turn tool-calling data generation
- [vLLM Tool Calling Documentation](https://docs.vllm.ai/en/latest/features/tool_calling/) -- `--enable-auto-tool-choice`, parser support
- [Stoplight Prism](https://github.com/stoplightio/prism) -- OpenAPI mock server, OAS 3.0 + Swagger 2.0
- [Red Hat OpenShift GitOps 1.19](https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/1.19/) -- ArgoCD operator for OCP
- [TMF642/628/621 GitHub Repos](https://github.com/tmforum-apis) -- OpenAPI specs, reference implementations
- [EdgeGen](https://arxiv.org/html/2609.24115) -- Edge case and error scenario gaps in synthetic data
- [TeleCom-Bench](https://arxiv.org/html/2605.18025v1) -- Execution Wall: 66-point gap between linguistic and procedural tasks
- [ZTE-AIM TFCE Dataset](https://huggingface.co/datasets/ZTE-AIM/Telecom-Function-Calling-Evaluation) -- 917-problem telecom eval benchmark

### Secondary (MEDIUM confidence)
- [MCP Architecture Best Practices 2026](https://markaicode.com/architecture/mcp-architecture-best-practices-2026/) -- Gateway composition patterns
- [Amartus TMF Integration Guide](https://amartus.com/how-to-effectively-design-integration-interfaces-that-are-based-on-tmf-open-api-specifications/) -- TMF spec ambiguity, conformance gaps
- [GSMA Open Gateway](https://www.gsma.com/solutions-and-impact/gsma-open-gateway/) -- Sandbox availability
- [NextGCore GitHub](https://github.com/NextgCoreLab/nextgcore) -- NWDAF implementation status, issue #192

### Tertiary (LOW confidence)
- [API Evangelist Open Gateway Analysis](https://github.com/api-evangelist/open-gateway) -- GSMA sandbox access limitations (single analyst source, needs validation)

---
*Research completed: 2026-09-26*
*Ready for roadmap: yes*
