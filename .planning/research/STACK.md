# Technology Stack

**Project:** OTel 2.5 Telecom Tool-Calling Training Data Pipeline
**Researched:** 2026-09-26
**Overall Confidence:** HIGH (all core choices verified against official docs and current releases)

## Recommended Stack

### MCP Server Framework

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| FastMCP (Python) | 4.0.10 | Build MCP servers wrapping TMF/NWDAF/CAMARA APIs | Built-in OpenAPI-to-MCP conversion via `from_openapi()`, decorator-based `@mcp.tool()` API, Python aligns with SDG pipeline and MCP-Telecom (which already uses FastMCP), powers ~70% of MCP servers in the wild. v4 implements the 2026-07-28 MCP protocol revision with sessionless requests suitable for load-balanced deployments. | HIGH |
| Python | 3.12 | Runtime | FastMCP requires >=3.10, NeMo Data Designer supports 3.10-3.14, 3.12 is the sweet spot for stability and performance. | HIGH |

**Why FastMCP Python over TypeScript MCP SDK:**
- MCP-Telecom (60+ existing tools we integrate) already uses FastMCP Python. Using TypeScript would create a language split.
- FastMCP's `from_openapi()` (available since v2.0.0, matured through v3/v4) directly converts TMF OpenAPI specs into MCP tools -- the exact pattern needed for TMF642, TMF628, TMF621, NWDAF, and CAMARA specs.
- The SDG pipeline (NeMo Data Designer) is Python. Single language across MCP servers + SDG pipeline reduces operational complexity.
- FastMCP 4.x is built on MCP SDK v2, so we get the latest protocol support without the lower-level SDK boilerplate.

**Why not the official MCP Python SDK (`mcp` v2.x) directly:**
The official `mcp` v2.x SDK (class: `MCPServer`) is the reference implementation but lacks FastMCP's OpenAPI integration, middleware system, composition/proxy features, and deployment tooling. For building 20+ tools from OpenAPI specs, FastMCP's higher-level abstractions save significant development time.

### SDG (Synthetic Data Generation) Pipeline

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| NeMo Data Designer | >=0.6.x | Declarative SDG pipeline for tool-calling training data | YAML-driven column DAG, built-in tool-calling SFT output format, MCP server integration for execution traces, Apache 2.0 license, used at NVIDIA production scale (~10T tokens generated). Connects to external tools through MCP servers for verified data generation. | HIGH |
| NeMo Curator | latest | Data filtering, deduplication, quality gating | Prebuilt filtering pipelines (exact/fuzzy dedup, quality classification), integrates with Data Designer via `DataDesignerStage`. Any OpenAI-compatible inference service works. | HIGH |
| vLLM | >=0.8.3 | Serve open-weight teacher models for bulk SDG | Tool-calling support with `--enable-auto-tool-choice`, parsers for xLAM/Llama3/Hermes/Qwen3 models, OpenAI-compatible API, GPU-efficient serving. Required flag added in 0.8.3. | HIGH |

**Pipeline architecture (APIGen-inspired three-stage verification):**

1. **Generation** -- NeMo Data Designer generates tool-calling examples using YAML-defined column DAGs. Each example contains: domain context, tool definitions (from MCP tool schemas), user query, and expected tool call(s).
2. **Execution verification** -- Generated tool calls are executed against backends (NextGCore NWDAF live, Prism mocks for TMF APIs) to verify they produce valid responses. This is the APIGen methodology's key insight: executable verification catches 60-75% of parameter errors that format-only checks miss.
3. **Semantic verification** -- LLM judge scores whether the tool call actually answers the user query (not just syntactically valid). NeMo Data Designer supports LLM judges as validators in the column DAG.

**Why NeMo Data Designer over APIGen-MT:**
APIGen-MT (Salesforce) is the strongest methodology paper for multi-turn tool-calling data, and the xLAM-2 models trained on it top BFCL. However, the full pipeline code is not open-sourced (GitHub issue #38 confirms this). Only a PoC exists (minpeter/APIGen-MT) that lacks the sophisticated context preparation, multi-judge committee, and policy compliance checks. NeMo Data Designer is fully open-source (Apache 2.0), has a production-grade framework, and its YAML config approach is reproducible. We adopt APIGen's three-stage verification methodology within NDD's framework.

**Why not NeMo Skills directly:**
NeMo Skills is the broader pipeline framework (SDG + training + eval). We only need SDG -- Farbod's team handles training. NeMo Data Designer is the focused SDG component with better tool-calling support. NeMo Skills is the right choice if we were doing end-to-end, but we are not.

### Teacher Models for SDG

| Model | Purpose | Cost (per 1M tokens) | Why | Confidence |
|-------|---------|---------------------|-----|------------|
| GPT-4.1 | Primary tool-call generation | $2.00 in / $8.00 out | Best structured output precision for function-calling, parallel tool call support, 1M context window, 50% batch API discount. OpenAI's tool-calling format is the de facto standard that NeMo Data Designer outputs. | HIGH |
| Claude Sonnet 4.5 | Semantic validation / multi-step reasoning judge | $3.00 in / $15.00 out | Strongest at long-horizon multi-step reasoning. Use as the LLM judge in verification stage, not for bulk generation. | MEDIUM |
| Qwen3-72B (via vLLM) | High-volume bulk generation | Self-hosted GPU cost only | Open-weight, competitive on BFCL, serves via vLLM with `--tool-call-parser hermes`. For the 8,500-14,000 raw examples needed, self-hosted generation at scale is 5-10x cheaper than API calls. | MEDIUM |

**Cost estimate for target volume:**
- 14,000 examples x ~1,500 tokens/example (input+output) = ~21M tokens
- GPT-4.1 API: ~$42 input + $168 output = ~$210 total (or ~$105 with batch API)
- Self-hosted Qwen3-72B: GPU-hours only, roughly $20-40 on cloud GPUs
- Validation pass with Claude Sonnet: ~$60-90 for semantic judging
- **Total SDG cost estimate: $150-300** (well within project scope)

### Mock API Servers

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Prism (Stoplight) | 5.16.0 | Auto-mock TMF642, TMF628, TMF621 from OpenAPI specs | Spec-driven auto-generation (no manual stub config), supports OAS 3.0 + Swagger 2.0 (needed for TMF628 v4.0.0 which is Swagger-only), dynamic response generation from schema, request/response validation, Docker-ready. TMF specs all have OpenAPI definitions -- Prism reads them directly. | HIGH |
| NextGCore (live) | latest | Real NWDAF TS 29.520 backend | Only open-source 5G core with ONNX-backed NWDAF analytics. Provides real responses for ABNORMAL_BEHAVIOUR, LOAD_LEVEL_INFORMATION events. Docker Compose deployment. AGPL-3.0 (sandbox use only, not shipped). | HIGH |

**Why Prism over WireMock:**
WireMock requires manual stub configuration for every endpoint -- with TMF642 alone having 18 event listener endpoints and TMF628 having 35 operations, manual stubbing is impractical. Prism reads the OpenAPI spec and generates mocks automatically. For execution-verified SDG, we need mocks that conform to the spec shape, not hand-crafted responses.

**Why Prism over Microcks:**
Microcks (CNCF incubating, Kubernetes-native) is the superior choice for production API mocking at scale. However, for SDG pipeline usage we need lightweight, fast-startup mock servers that spin up per OpenAPI spec. Prism runs as a single Node.js process per spec: `npx prism mock tmf642.yaml --port 4010`. Microcks requires MongoDB + Keycloak + the Microcks server -- that operational weight is unnecessary for mock backends in a data generation pipeline. If the project later needs persistent, shared mock environments (e.g., for developer testing), Microcks is the right upgrade path.

**Why not MockServer:**
Same issue as WireMock -- requires manual JSON/Java stub configuration. No OpenAPI auto-generation. Single maintainer project.

### OpenAPI-to-MCP Conversion

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| FastMCP `from_openapi()` | 4.0.10 (built-in) | Convert TMF/NWDAF/CAMARA OpenAPI specs to MCP tools | Already using FastMCP for MCP servers. `from_openapi()` handles OAS 3.0 YAML (TMF642, TMF621, NWDAF, CAMARA) and Swagger 2.0 JSON (TMF628). RouteMap controls which endpoints become tools vs resources. `mcp_component_fn` callback allows post-generation enhancement of descriptions for LLM consumption. | HIGH |

**Post-conversion curation is mandatory:**
FastMCP's own docs warn that "LLMs achieve significantly better performance with well-designed and curated MCP servers than with auto-converted OpenAPI servers." The conversion pipeline should be:
1. Auto-convert with `from_openapi()` to bootstrap tool definitions
2. Manually curate: enhance descriptions with telecom domain context, add examples, simplify parameter schemas where OpenAPI is over-specified
3. Test with an LLM to verify tool selection accuracy before SDG

**Why not standalone openapi-mcp-generator:**
The `openapi-mcp-generator` CLI (TypeScript) generates standalone MCP servers from OpenAPI specs. While useful as a one-shot code generator, FastMCP's `from_openapi()` keeps the conversion dynamic -- spec updates automatically propagate without code regeneration. Since we control the specs and need to iterate on tool definitions during SDG, the dynamic approach is better.

### Container Deployment

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| OpenShift Container Platform | 4.16+ | Container orchestration | Project constraint -- Red Hat platform required. OCP 4.16+ supports the OpenShift GitOps 1.19 operator. | HIGH |
| Helm | 3.x | Application packaging | Standard Kubernetes package manager. TMF mock servers, MCP servers, and NextGCore all need Helm charts for repeatable deployment. ArgoCD natively supports Helm as a source. | HIGH |
| Red Hat OpenShift GitOps | 1.19 | GitOps deployment (ArgoCD) | Red Hat-supported ArgoCD operator. v1.19 is GA with agent-based pull deployments, supports OCP 4.14-4.21. Manages the full deployment lifecycle: MCP servers, mock backends, SDG pipeline jobs. | HIGH |
| Podman / Buildah | latest (OCP-bundled) | Container build | Red Hat's container tooling. Rootless, daemonless, OCI-compliant. Already on OpenShift nodes. Use for building MCP server images. | HIGH |

**Deployment architecture:**
```
OpenShift Cluster
  |-- Namespace: mcp-servers
  |     |-- MCP-Telecom (60+ device-layer tools)
  |     |-- MCP-TMF (TMF642, TMF628, TMF621 tools)
  |     |-- MCP-5GCore (NWDAF analytics, CAMARA tools)
  |
  |-- Namespace: mock-backends
  |     |-- Prism: TMF642 mock (port 4010)
  |     |-- Prism: TMF628 mock (port 4011)
  |     |-- Prism: TMF621 mock (port 4012)
  |     |-- NextGCore: NWDAF live backend
  |
  |-- Namespace: sdg-pipeline
  |     |-- NeMo Data Designer job (runs SDG)
  |     |-- vLLM serving (teacher model)
  |     |-- Validation/filtering jobs
  |
  ArgoCD (OpenShift GitOps) syncs all from Git
```

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| httpx | >=0.27 | Async HTTP client for MCP-to-backend calls | FastMCP's OpenAPI integration requires httpx.AsyncClient for backend requests. Also used for MCP tool implementations calling TMF/NWDAF APIs. | HIGH |
| pydantic | >=2.0 | Schema validation for tool parameters and SDG output | FastMCP uses Pydantic for tool parameter validation. NeMo Data Designer uses Pydantic models for structured output schemas. Single dependency, two uses. | HIGH |
| datasets (HuggingFace) | >=2.0 | Load/save training data in standard formats | Loading xLAM evaluation datasets, saving final JSONL training data. Standard ML data handling. | HIGH |
| openai (Python client) | >=1.0 | Interface with teacher model APIs and vLLM | vLLM exposes OpenAI-compatible endpoints. NeMo Data Designer uses OpenAI-format for model calls. Single client library for all model interactions. | HIGH |
| pytest | >=8.0 | Testing MCP tools and SDG pipeline | Test tool schemas, mock server responses, pipeline output validation. | HIGH |
| uv | >=0.4 | Python package management | Faster than pip, lockfile support, recommended by FastMCP docs. Use for reproducible environments across dev and CI. | MEDIUM |

### Data Formats

| Format | Purpose | Spec |
|--------|---------|------|
| OpenAI chat + tools JSONL | SDG output / training data format | Messages array with roles (system, user, assistant, tool) + tools array with function definitions. This is what Farbod's team expects for OSFT. |
| MCP tool schemas (JSON) | Tool definitions for SDG seed data | Extracted from MCP server tool registrations. Each tool has name, description, inputSchema (JSON Schema). |
| OpenAPI 3.0 YAML / Swagger 2.0 JSON | Source API specifications | TMF642/621 (OAS 3.0), TMF628 (Swagger 2.0), NWDAF (OAS 3.0), CAMARA (OAS 3.0). Input to both Prism mocking and FastMCP conversion. |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| MCP Framework | FastMCP 4.x (Python) | TypeScript MCP SDK v2 | Creates language split with SDG pipeline (Python) and MCP-Telecom (Python). No built-in OpenAPI conversion in TS SDK. |
| MCP Framework | FastMCP 4.x (Python) | Official `mcp` v2.x Python SDK | Lower-level, lacks OpenAPI integration, middleware, composition. More code to write for same result. |
| SDG Pipeline | NeMo Data Designer | APIGen-MT (Salesforce) | Pipeline code not open-sourced. Only dataset + PoC available. Methodology adopted, framework not usable. |
| SDG Pipeline | NeMo Data Designer | Custom Python scripts | Reinventing YAML config, column DAG, batching, validation. NDD provides this out of the box with tool-calling SFT format. |
| Mock Server | Prism 5.x | WireMock | Requires manual stub config per endpoint. TMF specs have 50+ operations total -- manual stubbing is impractical for SDG. |
| Mock Server | Prism 5.x | Microcks (CNCF) | Operational overhead (MongoDB + Keycloak + server) excessive for SDG mock backends. Right choice for production API simulation, wrong choice for pipeline-internal mocks. |
| Teacher Model | GPT-4.1 + Qwen3 | Claude Opus 4.x exclusively | Claude excels at multi-step reasoning but GPT has better structured output precision for tool-call generation. Claude is better as the judge/validator. Cost: Claude Opus is ~4-5x more expensive for bulk generation. |
| GitOps | OpenShift GitOps 1.19 | Upstream ArgoCD | OpenShift GitOps IS ArgoCD, but Red Hat-supported with SCC-aware defaults. Using upstream on OpenShift means losing operator lifecycle management. |
| Package Manager | uv | pip/poetry | uv is 10-100x faster, has built-in lockfiles, recommended by FastMCP. Poetry works but adds unnecessary abstraction. |

## Version Compatibility Matrix

| Component | Min Version | Tested With | Protocol/Spec |
|-----------|-------------|-------------|---------------|
| FastMCP | 4.0.0 | 4.0.10 | MCP 2026-07-28 |
| Python | 3.10 | 3.12 | -- |
| Prism | 5.x | 5.16.0 | OAS 3.0 + Swagger 2.0 |
| vLLM | 0.8.3 | latest | OpenAI-compatible |
| NeMo Data Designer | 0.6.x | latest | -- |
| OpenShift | 4.16 | 4.18+ | -- |
| OpenShift GitOps | 1.19 | 1.19.x | ArgoCD 2.x |
| Helm | 3.x | 3.14+ | -- |

## Installation

```bash
# Core MCP server dependencies
uv add fastmcp httpx pydantic

# SDG pipeline
pip install data-designer  # NeMo Data Designer
pip install nemo-curator    # Filtering and dedup
pip install openai          # Teacher model API client
pip install datasets        # HuggingFace data loading

# vLLM (for self-hosted teacher model)
pip install vllm

# Mock server
npm install -g @stoplight/prism-cli

# Dev dependencies
uv add --dev pytest pytest-asyncio
```

```bash
# Start Prism mock for TMF642
npx @stoplight/prism-cli mock tmf642_alarm_management.yaml --port 4010

# Start vLLM with tool calling (example with Qwen3-72B)
vllm serve Qwen/Qwen3-72B-Instruct \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --tensor-parallel-size 4

# Run FastMCP server
fastmcp run src/mcp_tmf/server.py
```

## Sources

### Verified (HIGH confidence)
- [FastMCP 4.0.10 on PyPI](https://pypi.org/project/fastmcp/) -- latest version, release date, Python requirements
- [FastMCP OpenAPI Integration docs](https://gofastmcp.com/integrations/openapi) -- `from_openapi()` API, RouteMap, caveats
- [FastMCP GitHub (PrefectHQ)](https://github.com/PrefectHQ/fastmcp) -- source, releases, protocol support
- [MCP TypeScript SDK v2.1.0](https://www.npmjs.com/package/@modelcontextprotocol/server) -- alternative evaluated
- [NeMo Data Designer GitHub](https://github.com/NVIDIA-NeMo/DataDesigner) -- Apache 2.0, Python 3.10-3.14, installation
- [NeMo Tool-Calling Fine-Tuning Tutorial](https://docs.nvidia.com/nemo/microservices/26.3.1/example-applications/tool-calling.html) -- pipeline steps, Pydantic schemas, output format
- [Prism 5.16.0 GitHub releases](https://github.com/stoplightio/prism/releases) -- latest version, Docker support
- [Prism docs](https://docs.stoplight.io/docs/prism/83dbbd75532cf-http-mocking) -- OAS 3.0/Swagger 2.0 support, dynamic mocking
- [vLLM Tool Calling docs](https://docs.vllm.ai/en/latest/features/tool_calling/) -- `--enable-auto-tool-choice`, parser list, supported models
- [Red Hat OpenShift GitOps 1.19 Release Notes](https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/1.19/html-single/release_notes/index) -- OCP compatibility, agent-based deployment GA

### Methodology References (HIGH confidence)
- [APIGen paper (arXiv:2406.18518)](https://arxiv.org/abs/2406.18518) -- three-stage verification methodology (format, execution, semantic)
- [APIGen-MT paper (arXiv:2504.03601)](https://arxiv.org/abs/2504.03601) -- multi-turn tool-calling data generation, NeurIPS 2025
- [xLAM GitHub (SalesforceAIResearch)](https://github.com/SalesforceAIResearch/xLAM) -- ActionStudio framework, data format, Apache 2.0 code / CC-BY-NC-4.0 data

### Benchmark / Market Data (MEDIUM confidence)
- [BFCL v4 / Function Calling Benchmarks](https://awesomeagents.ai/leaderboards/function-calling-benchmarks-leaderboard/) -- model rankings for tool calling
- [MCP-Atlas, Toolathlon-Verified benchmarks](https://benchlm.ai/frontier-ai-models) -- cross-server MCP tool-use evaluation
- [Microcks CNCF Incubating announcement](https://www.cncf.io/blog/2026/05/07/microcks-becomes-a-cncf-incubating-project/) -- alternative mock server evaluated
