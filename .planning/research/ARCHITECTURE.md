# Architecture Patterns

**Domain:** Telecom MCP tool-calling training data generation (SDG pipeline with execution verification)
**Researched:** 2026-09-26

## Recommended Architecture

Four-layer system: MCP tool servers (tool definitions + API proxying), backend tier (live cores + mocks), SDG pipeline (batch generation + verification), and inference tier (teacher model). All deployed on OpenShift.

```
                                  +-------------------+
                                  |   SDG Pipeline    |
                                  |   Orchestrator    |
                                  |   (batch Job)     |
                                  +--------+----------+
                                           |
                          +----------------+----------------+
                          |                                 |
                          v                                 v
                 +--------+--------+              +---------+---------+
                 | Teacher Model   |              | Semantic Judge    |
                 | (vLLM on GPU)   |              | (vLLM or API)     |
                 | OpenAI-compat   |              | quality filtering |
                 +--------+--------+              +---------+---------+
                          |                                 ^
                          | tool-calling traces             | execution results
                          v                                 |
                 +--------+--------+                        |
                 | MCP Gateway     | <-- FastMCP proxy ---->+
                 | (composition    |                        |
                 |  server)        |                        |
                 +---+----+----+--+                         |
                     |    |    |                             |
          +----------+    |    +----------+                 |
          |               |               |                 |
+---------+--+  +---------+--+  +---------+--+              |
| TMF Server |  | NWDAF      |  | MCP-Telecom|              |
| (642/628/  |  | Server     |  | (60+ infra |              |
|  621)      |  | (29.520)   |  |  tools)    |              |
+------+-----+  +------+-----+  +------+-----+             |
       |               |               |                    |
       v               v               v                    |
+------+-----+  +------+-----+  +------+-----+             |
| Prism Mock |  | NextGCore  |  | Containerlab|            |
| Servers    |  | 5G Core    |  | / Device    |            |
| (TMF specs)|  | (NWDAF API)|  | Simulator   |            |
+------------+  +------------+  +-------------+            |
       |               |               |                    |
       +---------------+---------------+--------------------+
                    execution results flow back
```

### Component Boundaries

| Component | Responsibility | Communicates With | Technology |
|-----------|---------------|-------------------|------------|
| **SDG Pipeline Orchestrator** | Generates seed scenarios, dispatches to teacher model, collects traces, runs verification, filters, writes JSONL | Teacher Model, MCP Gateway, Semantic Judge, storage | Python, batch Job on OpenShift |
| **Teacher Model (vLLM)** | Generates multi-turn tool-calling traces given seed scenarios + tool schemas | SDG Orchestrator (via OpenAI-compatible API) | vLLM on GPU pod, OpenShift AI / KServe |
| **MCP Gateway** | Unified entry point composing all MCP servers; routes tool calls to correct domain server | SDG Orchestrator, domain MCP servers | FastMCP proxy/mount, Python |
| **TMF MCP Server** | 11 curated tools for TMF642 (alarm), TMF628 (perf), TMF621 (ticket) | MCP Gateway, Prism mock backends | FastMCP, Python, httpx |
| **NWDAF MCP Server** | 3 tools for TS 29.520 AnalyticsInfo + EventsSubscription | MCP Gateway, NextGCore NWDAF API | FastMCP, Python, httpx |
| **CAMARA MCP Server** | 2 tools for Device Location (+ existing Device Status, SIM Swap) | MCP Gateway, operator sandboxes or Prism | FastMCP, Python, httpx |
| **MCP-Telecom** | 60+ infrastructure/device-layer tools (alarms, metrics, telemetry, routing) | MCP Gateway, Containerlab / device simulators | FastMCP, Python, Netmiko/ncclient |
| **Prism Mock Servers** | Auto-generated HTTP mocks from TMF/CAMARA OpenAPI specs | TMF MCP Server, CAMARA MCP Server | Stoplight Prism containers |
| **NextGCore** | Live 5G SA core with NWDAF analytics endpoint | NWDAF MCP Server | Rust binaries, Docker Compose |
| **Semantic Judge** | Scores execution results for correctness, completeness, safety | SDG Orchestrator | vLLM (same or separate instance) or external API |
| **Storage (PVC / S3)** | Stores generated traces, filtered dataset, pipeline logs | SDG Orchestrator | OpenShift PVC or MinIO/S3 |

### Data Flow

The end-to-end data flow from OpenAPI spec to training JSONL:

```
Phase 1: Tool Definition (build time)
  OpenAPI YAML (TMF642, TMF628, TMF621, TS29.520, CAMARA)
    --> Curated MCP tool definitions (hand-tuned, not raw auto-conversion)
    --> Registered in domain MCP servers
    --> Composed into MCP Gateway via FastMCP mount()

Phase 2: Seed Generation (pipeline run)
  Fault prediction workflow templates
    + Synthetic incident parameters (region, severity, device type, failure mode)
    --> Seed scenario prompts (batch of 500-1000 at a time)

Phase 3: Teacher Model Generation (pipeline run)
  Seed scenario + tool schemas (from MCP Gateway listTools)
    --> Teacher model (vLLM, e.g., Qwen3-32B or Nemotron)
    --> Multi-turn tool-calling trace (ReAct format)
    --> Raw trace with: user query, reasoning, tool_call, tool_result, final answer

Phase 4: Execution Verification (pipeline run)
  Each tool_call in the trace
    --> Dispatched to MCP Gateway
    --> Routed to correct backend (Prism mock / NextGCore / sandbox)
    --> HTTP request executed
    --> Response captured and compared to trace's expected tool_result
    --> Verdict: PASS (response matches), FAIL (error/mismatch), SKIP (backend unavailable)

Phase 5: Quality Filtering (pipeline run)
  Execution-verified traces
    --> Format validation (valid JSON tool calls, correct parameter types)
    --> Execution pass rate filter (drop traces with >30% FAIL steps)
    --> Semantic judge (LLM scores: correctness, completeness, safety, reasoning quality)
    --> Deduplication (semantic similarity)
    --> Difficulty stratification (simple 1-2 step, medium 3-5 step, complex 6+ step)
    --> Final: 5,000-10,000 high-quality training examples

Phase 6: Output
  Filtered traces --> JSONL (OpenAI chat format with tool_calls)
  Pipeline metrics --> JSON (pass rates, filter funnel, token counts)
  Delivered to Farbod's team for OSFT on OTel 2.0
```

## Patterns to Follow

### Pattern 1: Domain-Separated MCP Servers, Composed via Gateway

**What:** Each API family (TMF, NWDAF, CAMARA, infrastructure) gets its own MCP server process. A FastMCP gateway composes them into a single unified interface using `mount()` with namespaces.

**When:** Always. This is the core architectural pattern.

**Why:** Isolation (a bug in TMF642 parsing does not crash the NWDAF server), independent scaling, independent backend routing (each server's httpx client points to its own backend URL), and the tool count per server stays well under 20.

**Example:**
```python
from fastmcp import FastMCP
from fastmcp.server import create_proxy

gateway = FastMCP("Telco-MCP-Gateway")

# Mount domain servers with namespaces to prevent tool name collisions
gateway.mount(tmf_server, namespace="tmf")       # tmf_list_alarms, tmf_get_alarm, ...
gateway.mount(nwdaf_server, namespace="nwdaf")    # nwdaf_get_analytics, ...
gateway.mount(camara_server, namespace="camara")  # camara_verify_location, ...

# MCP-Telecom runs as external process; proxy into gateway
mcp_telecom_proxy = create_proxy("http://mcp-telecom-svc:8000/mcp")
gateway.mount(mcp_telecom_proxy, namespace="infra")

gateway.run(transport="http", port=8080)
```

**Key nuance:** FastMCP's `from_openapi()` auto-converts OpenAPI endpoints into MCP tools, but the FastMCP docs explicitly warn that "LLMs achieve significantly better performance with well-designed and curated MCP servers than with auto-converted OpenAPI servers." Use `from_openapi()` as a starting scaffold, then hand-tune tool names, descriptions, parameter schemas, and response formatting for LLM consumption. The 20 tools in the fault prediction API map already define the curated surface.

### Pattern 2: Batch SDG Pipeline with Producer-Consumer Stages

**What:** The SDG pipeline runs as a batch Job (not streaming). Each stage is a discrete step: seed generation, teacher inference, execution verification, semantic judging, filtering. Stages communicate via files or a work queue.

**When:** For generating the 8,500-14,000 raw examples needed.

**Why:** Batch is simpler, debuggable, and restartable. The target is a fixed dataset, not a real-time stream. APIGen and the NeMo NOC reasoning pipeline both use batch patterns. The pipeline needs to be fully reproducible for the WG deliverable.

**Example architecture:**
```
sdg-pipeline/
  seeds/           # Stage 1 output: seed scenario JSONL
  raw_traces/      # Stage 2 output: teacher-generated traces
  verified_traces/ # Stage 3 output: execution-verified traces
  filtered_traces/ # Stage 4 output: quality-filtered final dataset
  metrics/         # Pipeline run metrics
  
  generate_seeds.py       # Stage 1
  generate_traces.py      # Stage 2 (calls vLLM)
  verify_executions.py    # Stage 3 (calls MCP Gateway)
  filter_quality.py       # Stage 4 (calls semantic judge)
  run_pipeline.py         # Orchestrator (runs stages sequentially)
```

Each stage reads the previous stage's output directory and writes to its own. If a stage fails, rerun from that stage, not from scratch. This follows the NeMo Skills pipeline pattern (prepare -> generate -> verify -> format).

### Pattern 3: Three-Tier Backend Routing via Configuration

**What:** Each MCP server's backend URL is set via environment variable or ConfigMap, not runtime logic. The same MCP tool code works against all three backend tiers.

**When:** Always. This decouples tool definitions from backend implementations.

**Why:** The three backend tiers (NextGCore live, operator sandboxes, Prism mocks) have different availability and fidelity. Routing is a deployment concern, not an application concern.

```
Backend Tier 1: NextGCore (highest fidelity)
  - NWDAF AnalyticsInfo, EventsSubscription
  - Real 3GPP-compliant responses with ONNX-backed analytics
  - Runs in Docker Compose or adapted for OpenShift
  
Backend Tier 2: Operator Sandboxes (medium fidelity)
  - GSMA Open Gateway, Vodafone, BT sandboxes
  - CAMARA Device Status, Device Location
  - Rate-limited, requires API keys
  
Backend Tier 3: Prism Mocks (lowest fidelity, highest availability)
  - TMF642, TMF628, TMF621, CAMARA (fallback)
  - Auto-generated from OpenAPI specs
  - Dynamic responses based on schema definitions
  - Always available, no external dependencies
```

**Configuration:**
```yaml
# OpenShift ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-backend-config
data:
  TMF642_BASE_URL: "http://prism-tmf642:4010"
  TMF628_BASE_URL: "http://prism-tmf628:4011"
  TMF621_BASE_URL: "http://prism-tmf621:4012"
  NWDAF_BASE_URL: "http://nextgcore-nwdaf:8080"
  CAMARA_BASE_URL: "http://prism-camara:4013"  # or operator sandbox URL
```

### Pattern 4: APIGen-Style Three-Stage Verification

**What:** Every generated tool-calling trace goes through format checking, execution verification, and semantic verification before entering the training set. Follows the APIGen pipeline's proven verification pattern.

**When:** During pipeline Stage 4 (quality filtering).

**Why:** APIGen demonstrated that three-stage verification produces training data that lets 7B models outperform GPT-4 on function-calling benchmarks. The NeMo NOC reasoning pipeline uses a similar pattern. Unverified synthetic data degrades model quality.

```
Stage A: Format Check
  - JSON parseable
  - tool_call fields match registered tool schemas
  - Parameter types match OpenAPI spec constraints
  - No hallucinated tool names or parameters
  
Stage B: Execution Verification
  - Each tool_call replayed against MCP backend
  - HTTP status 2xx = PASS
  - Response structure matches expected schema
  - Timeout / connection error = SKIP (retry once)
  - 4xx/5xx = FAIL
  
Stage C: Semantic Verification
  - LLM judge scores the complete trace:
    - Does the reasoning make sense for the incident?
    - Are tool calls in logical order?
    - Does the final answer follow from the evidence?
    - Are there safety violations (destructive operations without checks)?
  - Score 0-5; threshold >= 3 to pass
```

### Pattern 5: Teacher Model via vLLM with OpenAI-Compatible API

**What:** Serve the teacher model (Qwen3-32B, Nemotron, or similar) via vLLM with `--enable-auto-tool-choice`. The SDG pipeline calls it using standard OpenAI Python client. This gives tool-calling support out of the box.

**When:** For all teacher model inference in the SDG pipeline.

**Why:** vLLM on OpenShift AI is the Red Hat-supported path for GPU inference. The OpenAI-compatible API means the pipeline code is model-agnostic -- swap teacher models by changing the vLLM deployment, not the pipeline code. vLLM supports parallel tool calls, structured output, and has Prometheus metrics for monitoring.

```python
from openai import OpenAI

teacher = OpenAI(
    base_url="http://vllm-teacher-svc:8000/v1",
    api_key="not-needed-internal",
)

response = teacher.chat.completions.create(
    model="Qwen/Qwen3-32B",
    messages=seed_messages,
    tools=mcp_tool_schemas,      # from MCP Gateway listTools
    tool_choice="auto",
    temperature=0.7,
    max_tokens=4096,
)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Raw OpenAPI-to-MCP Auto-Conversion for Training Data
**What:** Using `FastMCP.from_openapi()` output directly without curation.
**Why bad:** Auto-converted tool names are verbose (`tmf642AlarmManagement_v5_getAlarm`), descriptions are spec-ese not LLM-friendly, and parameter schemas include fields irrelevant to the fault prediction workflow. The LLM will generate lower-quality tool calls, and the training data will teach bad habits.
**Instead:** Use `from_openapi()` as scaffolding, then hand-write the 20 tool definitions with clear names (`tmf642_list_alarms`), LLM-optimized descriptions, and trimmed parameter sets matching the fault prediction workflow.

### Anti-Pattern 2: Single Monolithic MCP Server for All 80+ Tools
**What:** Putting MCP-Telecom's 60+ tools and the 20 new BSS/OSS tools into one process.
**Why bad:** 80+ tools exceed the ~50-tool threshold where LLM tool selection accuracy degrades. A crash in one tool domain takes down everything. Cannot scale NWDAF calls independently of alarm queries.
**Instead:** Domain-separated servers behind a gateway. The gateway exposes all tools but each server process stays focused. For SDG, the pipeline can also query specific domain servers directly rather than always going through the gateway.

### Anti-Pattern 3: Streaming SDG Pipeline
**What:** Generating, verifying, and filtering examples in a continuous stream.
**Why bad:** The target is a fixed dataset (5,000-10,000 examples), not ongoing generation. Streaming adds complexity (backpressure, exactly-once semantics, partial failure recovery) without benefit. It makes reproducibility harder -- you cannot "rerun from stage 3" if stages are interleaved.
**Instead:** Batch pipeline with stage-separated output directories. Each stage is idempotent and restartable.

### Anti-Pattern 4: Running Teacher Model and Verification in the Same Pod
**What:** Co-locating the GPU-intensive teacher model inference with the CPU-bound execution verification logic.
**Why bad:** GPU pods are expensive and scarce. Execution verification is I/O-bound (HTTP calls to MCP servers, waiting for Prism responses). Mixing them wastes GPU time on I/O waits and makes scaling each concern independently impossible.
**Instead:** Teacher model in its own GPU pod (vLLM). Verification in separate CPU pods. Pipeline orchestrator coordinates between them.

### Anti-Pattern 5: Hardcoded Backend URLs in MCP Tool Code
**What:** Embedding `http://prism-tmf642:4010` directly in tool function implementations.
**Why bad:** Cannot switch between Prism mock, NextGCore, and operator sandboxes without code changes. Breaks the principle that the same tool code works against all backend tiers.
**Instead:** Backend URL from environment variable, injected via OpenShift ConfigMap. The httpx client's `base_url` is set at server startup, not per-tool.

## Deployment Architecture on OpenShift

### Namespace Layout

```
Namespace: otel25-sdg
  |
  +-- MCP Tier (Deployments, 1-2 replicas each)
  |   +-- mcp-gateway          (FastMCP proxy, port 8080)
  |   +-- mcp-tmf              (TMF642/628/621, port 8081)
  |   +-- mcp-nwdaf            (NWDAF, port 8082)
  |   +-- mcp-camara           (CAMARA, port 8083)
  |   +-- mcp-telecom          (MCP-Telecom, port 8084)
  |
  +-- Backend Tier (Deployments/StatefulSets)
  |   +-- prism-tmf642         (Prism mock, port 4010)
  |   +-- prism-tmf628         (Prism mock, port 4011)
  |   +-- prism-tmf621         (Prism mock, port 4012)
  |   +-- prism-camara         (Prism mock, port 4013)
  |   +-- nextgcore            (5G SA core, multiple ports)
  |
  +-- Inference Tier (GPU node, managed by OpenShift AI)
  |   +-- vllm-teacher         (teacher model, port 8000, GPU)
  |   +-- vllm-judge           (semantic judge, port 8001, GPU)
  |                             (or shared on same vLLM instance)
  |
  +-- Pipeline Tier
  |   +-- sdg-pipeline         (Job or CronJob, CPU)
  |
  +-- Storage
      +-- sdg-data-pvc         (ReadWriteMany, pipeline I/O)
      +-- model-cache-pvc      (ReadWriteOnce, vLLM model weights)
```

### Resource Estimates

| Component | CPU Request | Memory Request | GPU | Replicas | Notes |
|-----------|-------------|----------------|-----|----------|-------|
| mcp-gateway | 250m | 256Mi | - | 1 | Lightweight proxy |
| mcp-tmf | 250m | 256Mi | - | 1 | httpx calls to Prism |
| mcp-nwdaf | 250m | 256Mi | - | 1 | httpx calls to NextGCore |
| mcp-camara | 250m | 256Mi | - | 1 | httpx calls to sandbox/Prism |
| mcp-telecom | 500m | 512Mi | - | 1 | SSH/NETCONF connections |
| prism-tmf642 | 100m | 128Mi | - | 1 | Node.js mock server |
| prism-tmf628 | 100m | 128Mi | - | 1 | Node.js mock server |
| prism-tmf621 | 100m | 128Mi | - | 1 | Node.js mock server |
| prism-camara | 100m | 128Mi | - | 1 | Node.js mock server |
| nextgcore | 2000m | 2Gi | - | 1 | Rust 5G core, multiple NFs |
| vllm-teacher | 4000m | 32Gi | 1-4x A100/H100 | 1 | 32B model, tensor parallel |
| vllm-judge | 2000m | 16Gi | 1x A100 | 1 | Can share with teacher |
| sdg-pipeline | 2000m | 4Gi | - | 1 (Job) | Batch orchestrator |

### OpenShift-Specific Considerations

**NextGCore on OpenShift:**
- Needs SCTP support. NextGCore uses userspace SCTP over UDP (pure Rust), so kernel SCTP module is NOT required -- this avoids the biggest OpenShift SCC headache for 5G cores.
- Still needs `NET_RAW` capability for raw socket access (UPF). Use a dedicated SecurityContextConstraint.
- Docker Compose definitions in `docker/rust/` need conversion to OpenShift Deployments. Each NF (AMF, SMF, UPF, NRF, etc.) becomes a separate pod or container in a multi-container pod.

**vLLM on OpenShift AI:**
- Use ServingRuntime + InferenceService (KServe) for managed GPU scheduling.
- RawDeployment mode (not Serverless) for persistent inference -- the SDG pipeline makes sustained, bursty calls, not sporadic ones.
- Set `--gpu-memory-utilization 0.90` and `--max-model-len 8192` to fit 32B model on 4x A100 80GB.
- Enable `--enable-auto-tool-choice --tool-call-parser hermes` (or `llama3_json` depending on teacher model).

**Prism Mock Servers:**
- One Prism container per OpenAPI spec (Prism takes exactly one spec file per instance).
- Mount spec files via ConfigMap. Start command: `prism mock -h 0.0.0.0 /specs/tmf642.yaml`.
- Enable dynamic responses with `prefer: dynamic=true` header from MCP tools to get varied mock data for SDG diversity.

**Storage:**
- `sdg-data-pvc`: ReadWriteMany (RWX) if pipeline stages run as separate pods. ReadWriteOnce (RWO) if stages run sequentially in one pod. RWO is simpler; prefer it unless parallelism demands RWX.
- `model-cache-pvc`: ReadWriteOnce, mounted on vLLM pod. Pre-populate with model weights via an init container or PVC clone to avoid download-on-start.

### Network Topology

```
All components in same namespace, communicate via ClusterIP Services.
No Ingress/Route needed -- everything is internal.

Exception: operator sandboxes (GSMA Open Gateway, Vodafone, BT)
  --> Egress from mcp-camara pod to external HTTPS endpoints
  --> May need NetworkPolicy to allow egress
  --> API keys stored in OpenShift Secrets, mounted as env vars
```

## Scalability Considerations

| Concern | At 1,000 examples | At 10,000 examples | At 50,000 examples |
|---------|-------------------|--------------------|--------------------|
| Teacher model throughput | Single vLLM instance, ~2 traces/min for 32B model, ~8 hours | Same instance, ~80 hours (add tensor parallelism) | Multiple vLLM instances with load balancer, or switch to smaller teacher |
| Execution verification | Sequential, ~5 min total | Parallel verification (10 workers), ~2 hours | Need to rate-limit against operator sandboxes; Prism scales trivially |
| Prism mock servers | Single replica each, no issue | Single replica each, no issue | Still single replica -- Prism is stateless and fast |
| Storage | < 100MB JSONL | ~500MB JSONL | ~2GB JSONL, consider S3/MinIO |
| Pipeline restartability | Not critical | Important -- add checkpointing per stage | Essential -- stage-level checkpointing + dedup on restart |

## Suggested Build Order

Build order follows dependency chains. Components lower in the stack must exist before components higher up can be tested.

```
Phase 1: Foundation (no dependencies)
  [1a] Prism mock servers (TMF642, TMF628, TMF621, CAMARA specs)
  [1b] MCP-Telecom integration (clone, containerize, test on OpenShift)
  [1c] vLLM teacher model deployment on OpenShift AI
  
  These three have zero dependencies on each other and can be built in parallel.

Phase 2: MCP Tool Layer (depends on Phase 1a for backends)
  [2a] TMF MCP Server (11 tools, curated from OpenAPI, pointing at Prism)
  [2b] CAMARA MCP Server (2-4 tools, pointing at Prism or sandbox)
  [2c] NWDAF MCP Server (3 tools -- can start with Prism, switch to NextGCore later)
  [2d] MCP Gateway (compose all servers via FastMCP mount)

  Can build 2a/2b/2c in parallel. 2d depends on at least one of them existing.

Phase 3: Backend Upgrade (depends on Phase 2c for NWDAF tools)
  [3a] NextGCore deployment on OpenShift (replace Prism for NWDAF)
  [3b] Operator sandbox integration (CAMARA endpoints, API keys)

  Optional -- Prism works for initial SDG runs. NextGCore adds fidelity.

Phase 4: SDG Pipeline (depends on Phase 1c + Phase 2d)
  [4a] Seed scenario generator
  [4b] Teacher model trace generator (calls vLLM + MCP tool schemas)
  [4c] Execution verifier (calls MCP Gateway)
  [4d] Semantic judge + quality filter
  [4e] Pipeline orchestrator (chains 4a-4d)

  Must be sequential: 4a -> 4b -> 4c -> 4d. Orchestrator (4e) wraps them.

Phase 5: Evaluation & Delivery
  [5a] Baseline OTel 2.0 on ZTE-AIM/TFCE
  [5b] Dataset packaging (JSONL + metadata + pipeline reproducibility docs)
  [5c] Delivery to Farbod's team
```

**Critical path:** Phase 1c (vLLM) and Phase 2d (MCP Gateway) gate Phase 4 (SDG Pipeline). Get these running first, even with Prism-only backends.

**Parallel opportunities:**
- Phase 1a/1b/1c are fully independent
- Phase 2a/2b/2c are independent of each other
- Phase 3 can happen during Phase 4 (swap backends mid-pipeline without changing tool code)

## Sources

- [FastMCP Documentation - Server Composition](https://gofastmcp.com/servers/composition) (Context7, HIGH confidence)
- [FastMCP Documentation - OpenAPI Integration](https://gofastmcp.com/integrations/openapi) (Context7, HIGH confidence)
- [FastMCP Documentation - Proxy Provider](https://gofastmcp.com/servers/providers/proxy) (Context7, HIGH confidence)
- [MCP Architecture Best Practices 2026](https://markaicode.com/architecture/mcp-architecture-best-practices-2026/) (WebSearch, MEDIUM confidence)
- [MCP Server Monolith Fix - Tool Scoping](https://www.channel.tel/blog/mcp-server-monolith-fix-tool-scoping) (WebSearch, MEDIUM confidence)
- [IBM MCP Architecture Patterns](https://ibm.github.io/mcp-context-forge/1.0.0-RC3/best-practices/mcp-architecture-patterns/) (WebSearch, MEDIUM confidence)
- [APIGen Pipeline](https://apigen-pipeline.github.io/) (WebSearch, HIGH confidence - NeurIPS 2024 paper)
- [ToolACE: Winning the Points of LLM Function Calling](https://arxiv.org/html/2409.00920v1) (WebSearch, HIGH confidence)
- [NVIDIA: Building Telco Reasoning Models with NeMo](https://developer.nvidia.com/blog/building-telco-reasoning-models-for-autonomous-networks-with-nvidia-nemo/) (WebFetch, HIGH confidence)
- [vLLM Tool Calling Documentation](https://docs.vllm.ai/en/latest/features/tool_calling/) (WebSearch, HIGH confidence)
- [vLLM on OpenShift AI with KServe](https://lucaberton.com/blog/openshift-ai-model-serving-vllm/) (WebSearch, MEDIUM confidence)
- [Red Hat Developer - Autoscaling vLLM on OpenShift AI](https://developers.redhat.com/articles/2025/10/02/autoscaling-vllm-openshift-ai) (WebSearch, HIGH confidence)
- [Stoplight Prism - OpenAPI Mock Server](https://github.com/stoplightio/prism) (WebSearch, HIGH confidence)
- [NextGCore GitHub](https://github.com/NextgCoreLab/nextgcore) (WebSearch, MEDIUM confidence)
- [M-Baraa-Mardini/NWDAF - Standalone NWDAF](https://github.com/M-Baraa-Mardini/NWDAF) (WebSearch, MEDIUM confidence)
- [NeMo Evaluator Sandbox Architecture](https://docs.nvidia.com/nemo/evaluator/nightly/architecture/sandbox) (WebSearch, HIGH confidence)
