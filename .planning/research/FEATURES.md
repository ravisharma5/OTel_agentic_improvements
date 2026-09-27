# Feature Landscape

**Domain:** Telecom MCP tool-calling training data generation pipeline
**Researched:** 2026-09-26

## Table Stakes

Features users expect. Missing = pipeline does not produce usable training data.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| MCP tool definitions from OpenAPI specs | The 20 fault prediction tools (TMF642, TMF628, TMF621, NWDAF, CAMARA) must exist as properly typed MCP tools or there is nothing to generate data for | Medium | Use openapi-mcp-generator or FastMCP OpenAPI ingestion to scaffold, then curate descriptions and prune parameters. Auto-generated tools perform worse than curated ones (FastMCP docs explicitly warn about this). |
| JSON Schema input/output validation | Every MCP tool call must validate against the tool's input schema before execution. Without this, the pipeline produces structurally invalid training examples that teach the model wrong parameter names/types | Low | MCP spec 2025-06-18 mandates JSON Schema for inputSchema and optional outputSchema. Use Zod (TypeScript) or Standard Schema bridge for runtime validation. |
| Mock backend responses via Prism | TMF642, TMF628, TMF621 have no public live backends. Without mocks, execution verification is impossible for ~14 of the 20 tools | Low | Prism supports OAS 3.0 and Swagger 2.0 (TMF628 is Swagger-only). Use dynamic mode for varied responses. Static mode returns same example values every time, which produces monotonous training data. |
| Live NWDAF backend via NextGCore | NWDAF analytics (ABNORMAL_BEHAVIOUR, LOAD_LEVEL_INFORMATION) are the prediction engine of the fault workflow. Prism mocks cannot produce realistic analytics output; NextGCore implements TS 29.520 with ONNX-backed models | Medium | Requires Docker Compose deployment, OpenShift adaptation needs SCCs and SCTP support. Has k8s/ directory but not OpenShift-native. |
| Teacher model SDG generation | Core value proposition: a strong teacher model (GPT-4o, Claude, or Nemotron-70B) generates tool-calling examples from MCP tool schemas. Without this, there is no synthetic data | Medium | Follow NeMo NOC pipeline pattern: provide tool schemas + fault scenario descriptions + few-shot examples as context. Teacher generates (user query, tool call sequence, tool response, reasoning). |
| Format-compliant output (OpenAI chat format JSONL) | Farbod's team expects training data in standard SFT format. Non-standard formats create integration friction that blocks the Oct 15 handoff | Low | OpenAI chat completion format with role=tool for tool responses. NeMo Data Designer outputs this natively. Validate every record against the schema before writing. |
| Execution verification of generated tool calls | APIGen's key finding: verifying that generated tool calls actually execute correctly against real/mock backends is what separates usable from unusable training data. Without this, the model learns to hallucinate plausible-looking but invalid API calls | High | Three-stage verification from APIGen: (1) format check, (2) execution against backend, (3) semantic verification. This is the single highest-value quality gate. |
| Exact and fuzzy deduplication | Without dedup, teacher models produce repetitive examples that waste training budget and risk model collapse. Standard practice removes 5-25% of raw generated data | Low | Exact dedup via hash signatures. Fuzzy dedup via MinHash + LSH. Run before semantic dedup (cheaper first). |
| Basic quality filtering (heuristic) | Remove malformed, truncated, or trivially simple examples that would dilute training signal. Every production SDG pipeline includes this | Low | Check: complete tool call structure, valid JSON, reasonable length, all required parameters present, response matches expected schema. |
| Volume target: 8,500-14,000 raw, 5,000-10,000 filtered | PROJECT.md specifies this range. Below 5K examples, tool-calling fine-tuning is unreliable. APIGen achieved SOTA with 60K examples across 3,673 APIs; our 23-tool scope needs proportionally fewer | Medium | Budget ~500 examples per tool minimum, with heavy concentration on multi-tool sequences. Quality beats quantity (Phi-1 on 7B tokens beat models trained on 100x more). |
| Container-based deployment | Must run on OpenShift. Non-containerized components block deployment | Low | MCP server (Node.js/Python): trivial. Prism: trivial. NextGCore: needs OpenShift adaptation. SDG pipeline orchestration: standard container job. |
| Health checks (liveness + readiness probes) | OpenShift best practice; without them, crashed MCP servers or mock backends silently fail, producing gaps in generated data | Low | HTTP /health endpoint on MCP servers and Prism instances. OpenShift probes configured in deployment manifests. |

## Differentiators

Features that set this effort apart from generic tool-calling SDG. Not expected by default, but create significant value for the WG.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Telecom-specific complexity tiers | Map the fault prediction workflow into difficulty levels that mirror real NOC escalation. Tier 1: single API call (list alarms). Tier 2: correlated queries (alarms + performance data). Tier 3: full 6-step fault workflow (alarm triage, perf pull, NWDAF analytics, device check, correlation, ticket creation). NVIDIA NeMo NOC pipeline uses exactly this curriculum approach and improved accuracy from 20% to 60% | Medium | Define 3-4 tiers based on number of tools invoked and reasoning depth. Tier boundaries come directly from the fault prediction workflow steps in fault_prediction_api_map.md. This is not arbitrary -- it follows NOC escalation patterns. |
| Multi-turn conversation generation | Real NOC workflows are not single-turn. An engineer asks follow-up questions, refines filters, drills into specific alarms. APIGen-MT's blueprint-then-simulation approach (NeurIPS 2025) produces verifiable multi-turn data that trains models to maintain context across turns. Their xLAM-2 models beat GPT-4o on multi-turn benchmarks | High | Two-phase approach: (1) generate task blueprint with ground-truth actions (which tools, which params, expected output), (2) simulate NOC-engineer-agent dialogue using the blueprint as guardrails. Reverse task recombination builds complex scenarios from validated simple ones. |
| Curriculum ordering for training delivery | Order the 5K-10K examples from simple to complex for OSFT. Research shows 18-45% faster convergence with easy-to-hard ordering. Depth of Thought (counting reasoning steps) is the cleanest metric for tool-calling curricula | Low | Straightforward metadata annotation: tag each example with tier and step count. Farbod's team uses the ordering during OSFT. Almost no engineering cost, significant training quality benefit. |
| Three-tier backend verification | Layer 1: Prism mocks (all 20 tools, synthetic responses). Layer 2: NextGCore live NWDAF (real analytics predictions). Layer 3: Operator sandboxes (GSMA Open Gateway, Vodafone, BT) for CAMARA endpoints. Each tier adds fidelity. No other telecom SDG effort has this layered verification | High | Prism is always-available baseline. NextGCore adds real NWDAF behavior. Operator sandboxes add real carrier responses but are rate-limited and may have access restrictions. Tag each training example with its verification tier so downstream consumers know the fidelity level. |
| Error case and edge case generation | Distribution mismatch is severe: if synthetic data lacks error cases (alarm not found, performance collection timeout, NWDAF service unavailable, invalid parameter), the model fails silently on those paths in production. Must deliberately generate ~15-20% error scenarios | Medium | Prism supports error simulation via Prefer header (e.g., Prefer: code=404). Generate examples where tools return errors and the model must handle them (retry, fallback, inform user). Include: invalid parameters, missing required fields, rate limiting, partial responses. |
| Semantic judging with telecom domain context | LLM-as-judge scoring of generated examples, using telecom-specific rubrics. Generic judges miss domain errors (e.g., wrong severity mapping, invalid alarm correlation logic, unrealistic NWDAF event combinations). Telecom-aware judging catches these | Medium | Use the teacher model with a telecom rubric to score each example on: (1) correct tool selection, (2) valid parameter values for telecom context, (3) realistic response handling, (4) sound reasoning about fault correlation. Score 0-5, filter below 3.5 per APIGen pattern. |
| Diversity metrics across API coverage | Track coverage: % of tools used, % of parameter combinations exercised, % of error codes covered, distribution across tiers. APIGen found that diversity matters more than volume for generalization -- 100 well-structured tools > 10,000 examples of 5 tools | Low | Dashboard or report showing: tool usage histogram, parameter combination coverage, tier distribution, unique scenario count. Flag under-represented tools for targeted generation. |
| Regression detection against ZTE-AIM/TFCE | Baseline OTel 2.0 on TFCE (917 problems, Chinese questions, English functions). After OSFT with our data, measure delta. This is the primary proof that the training data works. No one has published OTel 2.0 TFCE scores yet -- first-mover advantage on this measurement | Medium | TFCE covers Simple, Multiple, Parallel, Parallel-Multiple scenarios. Also baseline on BFCL V4 (22 tasks, AST + executable eval) and GSMA Open Telco Benchmarks (16,866 samples). Run eval suite before and after OSFT. Track per-category scores, not just overall. |
| Declarative pipeline configuration | NeMo Data Designer pattern: define the entire SDG pipeline in YAML (columns, dependencies, samplers, validators, quality gates). Reproducible, version-controlled, inspectable. No ad-hoc scripts | Medium | YAML config specifies: tool schemas to use, scenario templates, teacher model, verification backend, quality thresholds, output format. The same config can regenerate the entire dataset. Treat as a build artifact alongside the data. |
| MCP-Telecom integration for infrastructure context | Incorporate MCP-Telecom's 60+ device-layer tools (BGP, SNMP, gNMI, alarms) into multi-step scenarios where the model must correlate infrastructure-level faults with BSS/OSS-level alarms. Creates richer, more realistic training examples | Medium | Scenario: gNMI telemetry shows interface flapping (MCP-Telecom) AND TMF642 raises critical alarm AND NWDAF predicts load anomaly. The model must correlate across all three. This is uniquely achievable because we have both toolkits. |

## Anti-Features

Features to explicitly NOT build. These are traps that waste effort or create scope creep.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Custom training/OSFT framework | Farbod's team owns OSFT execution. Building our own duplicates effort and creates integration risk. Our deliverable is data + pipeline, not a trained model | Deliver JSONL in OpenAI chat format with curriculum ordering metadata. Let Farbod's team use their existing NeMo/TRL training setup |
| Production-grade API backends for TMF/NWDAF | Building real TMF642/628/621 backends is a multi-year OSS/BSS project. We need mock responses, not production APIs | Use Prism for TMF mocks (auto-generated from OpenAPI specs), NextGCore for NWDAF (already implements TS 29.520). Operator sandboxes for CAMARA |
| General-purpose SDG platform | Building a platform that generates training data for any domain is massively more scope than what we need. Telecom tool-calling is the constraint | Build a telecom-specific pipeline that handles our 23 tools and fault prediction workflow. If the architecture is clean, it naturally extends to other use cases (churn, energy) later |
| MCP client/agent runtime | We are building tools and training data, not an agent that uses them. Building an agent is a separate product | The SDG pipeline simulates agent behavior for data generation, but the output is training data, not a running agent. OTel 2.5 IS the agent after OSFT |
| Full TMF conformance test suite | PROJECT.md explicitly separates this as a strategic gaps document, not tied to Oct 15. Building it now delays the primary deliverable | Document conformance requirements in the industry gaps doc. Build just enough validation to ensure our MCP tools match the OpenAPI specs (Prism validation proxy handles this) |
| GUI/dashboard for pipeline monitoring | Engineering time is better spent on data quality than on a monitoring UI. The pipeline runs as batch jobs, not a long-lived service | Use OpenShift's built-in monitoring (Prometheus metrics, pod logs). Export pipeline stats as structured JSON for post-run analysis |
| Support for all 9 OTel gaps simultaneously | Gaps 2-9 (operational data, vendor CLI, IETF RFCs, OSS/BSS workflows, etc.) each require different API surfaces, different backends, and different domain knowledge | Build for gap 1 (tool-calling) with fault prediction only. Architecture should be extensible (add new tool schemas, new scenario templates) but do not pre-build for other gaps |
| Real-time streaming SDG | Running the pipeline as a continuously-generating stream adds complexity (state management, checkpointing, error recovery) with no benefit for a batch deliverable | Run as batch jobs: generate N examples, verify, filter, output. Orchestrate with OpenShift Jobs or Tekton pipelines |
| Multilingual training data | ZTE-AIM/TFCE has Chinese questions but English functions. TelAgentBench is Korean. Building multilingual support multiplies complexity without helping the primary English-language OSFT | Generate in English only. The tool schemas, parameter names, and API responses are all in English. Multilingual can be a post-OTel 2.5 extension |

## Feature Dependencies

```
OpenAPI Specs (TMF642/628/621, NWDAF, CAMARA)
  |
  v
MCP Tool Definitions (20 new tools)
  |
  +---> Schema Validation (JSON Schema input/output)
  |
  +---> Mock Backends (Prism for TMF, NextGCore for NWDAF)
  |       |
  |       v
  |     Execution Verification (format + execution + semantic)
  |       |
  |       v
  +---> Teacher Model SDG Generation
  |       |
  |       +---> Complexity Tiers (single → correlated → full workflow)
  |       |
  |       +---> Multi-turn Generation (blueprint → simulation)
  |       |
  |       +---> Error Case Generation (~15-20% of examples)
  |       |
  |       v
  |     Raw Training Examples (8,500-14,000)
  |       |
  |       v
  +---> Quality Pipeline
          |
          +---> Format Validation
          +---> Exact + Fuzzy Deduplication
          +---> Semantic Deduplication
          +---> Telecom Semantic Judging (LLM-as-judge)
          +---> Diversity Metrics
          |
          v
        Filtered Dataset (5,000-10,000)
          |
          +---> Curriculum Ordering (simple → complex)
          +---> Format Compliance (OpenAI chat JSONL)
          |
          v
        Deliverable to Farbod's Team
          |
          v
        Eval / Regression Detection
          +---> Baseline OTel 2.0 on TFCE, BFCL, GSMA
          +---> Post-OSFT delta measurement
```

Key dependency chains:

- MCP tool definitions must exist before any SDG generation can start
- Mock backends must be running before execution verification works
- Execution verification must work before quality filtering is meaningful (garbage in, garbage out)
- Complexity tiers must be defined before curriculum ordering can be applied
- Baseline eval must run before OSFT so there is a before/after comparison

## MVP Recommendation

Prioritize for the Oct 15 deadline:

1. **MCP tool definitions for all 20 fault prediction tools** -- without these, nothing else works. Use OpenAPI-to-MCP generators for scaffolding, then curate descriptions for LLM consumption. Estimate: 1-2 weeks.

2. **Prism mock backends + NextGCore NWDAF deployment** -- execution verification is the highest-value quality gate. Prism is trivial (point at OpenAPI spec). NextGCore needs OpenShift adaptation. Estimate: 1 week.

3. **Teacher model SDG with execution verification** -- the core pipeline. Generate examples, execute them against backends, keep only verified ones. Start with single-tool (Tier 1) examples to prove the pipeline, then scale to multi-tool (Tier 2-3). Estimate: 2-3 weeks.

4. **Quality filtering pipeline (format + dedup + basic semantic judging)** -- filter raw output down to the 5K-10K target. Estimate: 1 week.

5. **Curriculum ordering + format export** -- tag examples with tier/complexity, order for OSFT, export as JSONL. Estimate: 2-3 days.

6. **Baseline eval on ZTE-AIM/TFCE** -- run OTel 2.0 against TFCE before OSFT. This is proof the data will matter. Estimate: 1 week.

Defer to post-Oct 15:
- **Multi-turn generation** (APIGen-MT blueprint approach): High value but high complexity. Start with single-turn verified examples, add multi-turn in a second pass.
- **MCP-Telecom integration**: Valuable for cross-domain scenarios but adds integration complexity. Can retrofit after core pipeline delivers.
- **Operator sandbox verification (Tier 3)**: Requires access coordination with GSMA/Vodafone/BT. Use Prism + NextGCore for Oct 15, add sandbox verification as data quality enrichment later.
- **Declarative YAML pipeline config**: Nice for reproducibility but the pipeline needs to work first. Refactor to declarative config after the batch pipeline proves out.

## Sources

### MCP Specification and Tools
- [MCP Tools Specification 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) -- HIGH confidence
- [MCP TypeScript SDK Tool Registration](https://deepwiki.com/modelcontextprotocol/typescript-sdk/3.2-tool-registration-and-execution) -- HIGH confidence
- [Red Hat MCP Validation Tool](https://github.com/RHEcosystemAppEng/mcp-validation) -- HIGH confidence
- [openapi-mcp-generator](https://github.com/harsha-iiiv/openapi-mcp-generator) -- MEDIUM confidence
- [FastMCP OpenAPI Integration](https://gofastmcp.com/integrations/openapi) -- HIGH confidence
- [Speakeasy: Generate MCP from OpenAPI](https://www.speakeasy.com/mcp/tool-design/generate-mcp-tools-from-openapi) -- MEDIUM confidence
- [Stainless: Lessons from OpenAPI to MCP Conversion](https://www.stainless.com/blog/lessons-from-openapi-to-mcp-server-conversion/) -- MEDIUM confidence

### SDG Pipelines and Methodology
- [NVIDIA NeMo Telco NOC Reasoning Pipeline](https://developer.nvidia.com/blog/building-telco-reasoning-models-for-autonomous-networks-with-nvidia-nemo/) -- HIGH confidence (directly relevant, March 2026)
- [NeMo Data Designer](https://github.com/NVIDIA-NeMo/DataDesigner) -- HIGH confidence
- [NeMo Tool-Calling Fine-Tuning with Synthetic Data](https://docs.nvidia.com/nemo/microservices/latest/example-applications/tool-calling.html) -- HIGH confidence
- [APIGen Pipeline](https://apigen-pipeline.github.io/) -- HIGH confidence (NeurIPS 2024)
- [APIGen-MT: Multi-Turn Data Generation](https://arxiv.org/abs/2504.03601) -- HIGH confidence (NeurIPS 2025)
- [Synthetic Data for Tool-Calling Training](https://theneuralbase.com/function-calling-theory/learn/advanced/synthetic-tool-use-data/) -- MEDIUM confidence

### Data Quality
- [NVIDIA Data Preprocessing Techniques](https://developer.nvidia.com/blog/mastering-llm-techniques-data-preprocessing/) -- HIGH confidence
- [D4: Document De-Duplication and Diversification](https://proceedings.neurips.cc/paper_files/paper/2023/file/a8f8cbd7f7a5fb2c837e578c75e5b615-Paper-Datasets_and_Benchmarks.pdf) -- HIGH confidence (NeurIPS 2023)
- [Confident AI: Definitive Guide to SDG](https://www.confident-ai.com/blog/the-definitive-guide-to-synthetic-data-generation-using-llms) -- MEDIUM confidence

### Evaluation Benchmarks
- [BFCL V4 Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) -- HIGH confidence
- [ZTE-AIM TFCE Dataset](https://huggingface.co/datasets/ZTE-AIM/Telecom-Function-Calling-Evaluation) -- HIGH confidence
- [GSMA Open Telco AI Data](https://www.open-telco.ai/data/) -- HIGH confidence
- [TeleCom-Bench (ZTE)](https://github.com/ZTE-AICloud/TeleCom-Bench) -- HIGH confidence

### Curriculum Learning
- [Strategic Data Ordering for LLM Training](https://arxiv.org/html/2405.07490v1) -- HIGH confidence
- [Curriculum Learning for LLM Pretraining](https://arxiv.org/html/2601.21698v1) -- HIGH confidence

### Deployment
- [OpenShift MCP Server](https://github.com/redhat-performance/openshift-mcp-server) -- HIGH confidence
- [obs-mcp for OpenShift Observability](https://developers.redhat.com/articles/2026/07/16/how-obs-mcp-boosts-ai-native-openshift-observability) -- HIGH confidence
- [ContextForge OpenShift Deployment](https://ibm.github.io/mcp-context-forge/deployment/openshift/) -- MEDIUM confidence
- [Prism Mock Server](https://github.com/stoplightio/prism) -- HIGH confidence

### Telecom API Specifications
- [TMF642 Alarm Management](https://github.com/tmforum-apis/TMF642_AlarmManagement) -- HIGH confidence
- [TMF628 Performance Management](https://github.com/tmforum-apis/TMF628_Performance) -- HIGH confidence
- [TMF621 Trouble Ticket](https://github.com/tmforum-apis/TMF621_TroubleTicket) -- HIGH confidence
- [NWDAF TS 29.520 APIs](https://github.com/jdegre/5GC_APIs/blob/Rel-18/TS29520_Nnwdaf_AnalyticsInfo.yaml) -- HIGH confidence
- [Red Hat Open Telco AI Blog](https://www.redhat.com/en/blog/open-telco-ai-training-model-industry) -- HIGH confidence
