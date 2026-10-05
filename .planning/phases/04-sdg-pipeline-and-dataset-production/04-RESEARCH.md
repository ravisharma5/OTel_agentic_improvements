# Phase 4: SDG Pipeline and Dataset Production - Research

**Researched:** 2026-10-05
**Domain:** Synthetic data generation for telecom tool-calling training (sdg_hub, vLLM/Gemma 4, OSFT, backend readiness)
**Confidence:** MEDIUM-HIGH

## Summary

Phase 4 is the convergence phase -- it brings together everything Phases 1-3 built (backends, MCP tools, gateway) and runs the SDG pipeline to produce the actual training dataset. The research covers nine distinct workstreams that CONTEXT.md locked in: (1) sdg_hub pipeline configuration, (2) OSFT data format, (3) vLLM + Gemma 4 serving, (4) Containerlab device simulator deployment, (5) security fixes CR-01/02/03, (6) NWDAF h2c fix, (7) Prism spec enrichment, (8) ConfigMap consolidation, and (9) cross-cluster gateway exposure.

The most significant finding is around the OSFT data format (D-18). Training Hub's OSFT algorithm accepts JSONL with a `messages` array using standard roles (system/user/assistant), but its documentation does not explicitly document `tool_calls` or `tool` role support. The OpenAI-compatible tool-calling conversation format (assistant `tool_calls` array + `tool` role responses with matching `tool_call_id`) is the expected structure based on PITFALLS.md's analysis, HuggingFace TRL conventions, and sdg_hub's own trace normalization code -- but this MUST be validated via D-19's early dry-run with Farbod's team before committing to the full generation run. This is the single highest-risk assumption in this phase.

The sdg_hub pipeline (v0.9.4) requires an intermediate agent framework (Langflow or LangGraph) between itself and the MCP Gateway -- it does not call MCP servers directly. This means the OpenShift AI cluster deployment needs three components: vLLM serving Gemma 4 (teacher LLM), a Langflow/LangGraph agent wrapping the MCP Gateway tools, and the sdg_hub pipeline notebooks/scripts.

**Primary recommendation:** Stand up vLLM + Gemma 4 and the agent framework first, run a 10-example dry-run through sdg_hub immediately, validate the output format with Farbod's team, then fix backend readiness gaps in parallel before the full production run.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** sdg_hub (Red Hat AI Innovation Team) is the SDG framework -- supersedes NeMo Data Designer
- **D-02:** Both `mcp_distillation_training` and `mcp_distillation_evaluation` flows used
- **D-03:** sdg_hub installed as pinned pip dependency, not vendored
- **D-04:** OSFT-schema validation inside `mcp_distillation_evaluation` flow
- **D-05:** Deliverable is runnable recipes (notebooks + scripts), not just a dataset
- **D-06:** Pipeline runs on separate OpenShift AI (RHOAI) cluster
- **D-07:** Reuse existing Keycloak client-credentials flow for cross-cluster auth
- **D-08:** Teacher model is Gemma 4 31B dense (Apache 2.0)
- **D-09:** vLLM with `--enable-auto-tool-choice --tool-call-parser gemma4`
- **D-10:** GPU access already available on separate cluster
- **D-11:** Semantic judge model choice is Claude's discretion
- **D-12:** Containerlab device simulator using existing `containerlab.py` generator
- **D-13:** Security fixes CR-01/02/03 as prerequisites before device backend
- **D-14:** Populate `devices.yaml` and `command_allowlist.yaml` with Containerlab targets
- **D-15:** Fix NWDAF h2c incompatibility with h2c-capable client
- **D-16:** Enrich vendored specs with realistic TM Forum example values
- **D-17:** Consolidate two-copy ConfigMap to single source of truth
- **D-18:** OSFT JSONL schema from Training Hub (same GitHub org)
- **D-19:** Early dry-run validation with Farbod's team (~10 examples)
- **D-20:** Deliver both single-turn and multi-turn trajectory JSONL variants

### Claude's Discretion
- Exact OSFT-compliance check schema inside `mcp_distillation_evaluation` (D-04)
- Whether semantic judge reuses Gemma 4 or runs separately (D-11)
- Containerlab topology shape (device count, vendor mix)
- Curriculum/seed taxonomy specifics for ordering
- Mechanics of exposing MCP Gateway Route externally (D-07)

### Deferred Ideas (OUT OF SCOPE)
- None explicitly deferred. Other WG use cases, Phase 5 gaps doc, and OSFT training execution remain out of scope as before.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SDG-01 | Configure and run sdg_hub MCP distillation flow against MCP servers | sdg_hub v0.9.4 flow architecture, Langflow agent connector, vLLM/Gemma 4 teacher model setup |
| SDG-02 | Implement curriculum ordering (single-tool to closed-loop) | sdg_hub RowMultiplierBlock + SamplerBlock configuration, seed scenario taxonomy |
| SDG-03 | Output in both single-turn and multi-turn trajectory formats | sdg_hub trace normalization code, OSFT messages schema |
| SDG-04 | Produce 8,500-14,000 raw, filter to 5,000-10,000 verified | sdg_hub quality filtering (ColumnValueFilterBlock), three-stage verification |
| SDG-05 | Deliver filtered dataset to Farbod's team for OSFT | Training Hub JSONL schema, dry-run validation pattern |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SDG pipeline orchestration | OpenShift AI cluster (notebooks/scripts) | -- | sdg_hub runs as Python pipeline on RHOAI |
| Teacher model inference | OpenShift AI cluster (vLLM) | -- | Gemma 4 31B needs GPU; vLLM serves OpenAI-compatible API |
| Agent tool execution | OpenShift AI cluster (Langflow/LangGraph) | Existing cluster (MCP Gateway) | Agent wraps MCP Gateway tools; executes against remote gateway |
| MCP tool serving | Existing cluster (otel25-mcp) | -- | All 78 tools already deployed behind RHCL Gateway |
| Backend mock/live responses | Existing cluster (otel25-backends) | -- | Prism mocks + NextGCore + Containerlab devices |
| Device simulation | Existing cluster (Containerlab) | Separate VM if OpenShift Clabernetes incompatible | Containerlab needs privileged pods |
| Auth/Identity | Existing cluster (Keycloak) | -- | JWT client-credentials flow already built |
| Dataset validation | OpenShift AI cluster | -- | OSFT schema check in evaluation flow |
| Dataset delivery | Git/artifact store | -- | JSONL files + notebooks + scripts |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sdg-hub | 0.9.4 | SDG pipeline framework | [VERIFIED: PyPI registry -- `pip index versions sdg-hub` confirmed 0.9.4 latest] Red Hat AI Innovation Team's purpose-built tool for MCP distillation. D-01 locked. |
| training-hub | 0.10.0 | OSFT algorithm interface | [VERIFIED: PyPI registry -- confirmed 0.10.0 latest] Provides the `osft()` function with mini_trainer backend. D-18 locked. |
| vllm | 0.31.0 | Gemma 4 serving | [VERIFIED: PyPI registry -- confirmed 0.31.0 latest] Native Gemma 4 tool-call-parser support. D-09 locked. |
| httpx2 | 2.13.1 | HTTP client (existing in codebase) | [VERIFIED: PyPI registry -- 2.13.1 already installed] Pydantic-maintained fork of httpx; used by all MCP servers. |
| h2 | 4.4.1 | HTTP/2 protocol library | [VERIFIED: PyPI registry -- confirmed 4.4.1 latest] Required for h2c prior-knowledge mode to fix NWDAF. D-15. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpcore2 | (dep of httpx2[http2]) | HTTP/2 transport layer | Configuring h2c prior-knowledge for NWDAF client |
| pyyaml | (dep of sdg-hub) | YAML parsing | Containerlab topology, flow configs |
| clabernetes | latest Helm chart | Containerlab on Kubernetes | Deploying device topology on OpenShift (D-12) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Langflow agent | LangGraph agent | sdg_hub supports both; LangGraph has better MCP integration but needs `langgraph<2` pin per eval README |
| Clabernetes on OpenShift | Containerlab on bare VM | Avoids OpenShift privileged-SCC complexity; requires network reachability from otel25-mcp pods |
| h2c via httpcore2 | grpclib or raw h2 sockets | httpcore2 approach integrates cleanly with existing httpx2 client; lower-level alternatives require more code |

**Installation:**
```bash
# On OpenShift AI cluster (pipeline environment)
pip install "sdg-hub==0.9.4" "sdg-hub[vllm]" "sdg-hub[examples]"
pip install vllm  # served separately, not in same env

# On existing cluster (NWDAF fix)
pip install "httpx2[http2]"  # adds h2 + httpcore2[http2]

# Training Hub (for format reference/validation only -- Farbod's team runs actual training)
pip install "training-hub==0.10.0"
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| sdg-hub | PyPI | ~6 months (35 releases) | N/A | github.com/Red-Hat-AI-Innovation-Team/sdg_hub | [OK] | Approved |
| training-hub | PyPI | ~11 months (19 releases) | N/A | github.com/Red-Hat-AI-Innovation-Team/training_hub | [OK] | Approved |
| vllm | PyPI | ~3 years (70+ releases) | Very high | github.com/vllm-project/vllm | N/A (not checked) | Approved -- well-known project |
| httpx2 | PyPI | ~8 months | Moderate | github.com/pydantic/httpx2 | [SUS] | Approved -- false positive, validated in 02-REVIEW.md. Pydantic-maintained httpx fork already used in codebase. |
| h2 | PyPI | ~10 years (40+ releases) | High | github.com/python-hyper/h2 | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** httpx2 -- slopcheck flags it as "suspiciously close to httpx, could be a typosquat." This is a known false positive (documented in 02-REVIEW.md verification note). httpx2 is the legitimate Pydantic-stewarded continuation of httpx, already a dependency of FastMCP in this project.

## Architecture Patterns

### System Architecture Diagram

```
                    OpenShift AI Cluster (D-06)
    ┌──────────────────────────────────────────────────┐
    │                                                  │
    │   ┌──────────┐     ┌───────────────────────┐     │
    │   │ Jupyter   │     │ vLLM                  │     │
    │   │ Notebook  │     │ Gemma 4 31B           │     │
    │   │ (sdg_hub) │     │ --tool-call-parser    │     │
    │   │           │     │   gemma4              │     │
    │   └──┬──┬─────┘     └──────────┬────────────┘     │
    │      │  │                      │                  │
    │      │  │  LLM API calls       │                  │
    │      │  └──────────────────────┘                  │
    │      │                                            │
    │      │ Agent API calls                            │
    │      ▼                                            │
    │   ┌──────────────────────┐                        │
    │   │ Langflow / LangGraph │                        │
    │   │ Agent                │                        │
    │   │ (MCP Gateway client) │                        │
    │   └──────────┬───────────┘                        │
    │              │                                    │
    └──────────────┼────────────────────────────────────┘
                   │ HTTPS + JWT (D-07)
                   ▼
    ┌──────────────────────────────────────────────────┐
    │       Existing OpenShift Cluster                  │
    │                                                   │
    │   otel25-gateway                                  │
    │   ┌────────────────────────────────────────┐      │
    │   │ RHCL MCP Gateway                       │      │
    │   │ mcp.apps.cluster-wfhjs...opentlc.com   │      │
    │   │ Keycloak JWT auth (AuthPolicy)          │      │
    │   │ 4 Virtual MCP Servers (TMF/NWDAF/       │      │
    │   │   CAMARA/Infra)                         │      │
    │   └───────────┬────────────────────────────┘      │
    │               │                                   │
    │   otel25-mcp  ▼                                   │
    │   ┌─────────────────────────────────────┐         │
    │   │ TMF642 │ TMF628 │ TMF621 │ NWDAF │  │         │
    │   │ CAMARA │ MCP-Telecom (78 tools)     │         │
    │   └────────┬──────────┬─────────────────┘         │
    │            │          │                            │
    │   otel25-backends     │                            │
    │   ┌────────▼──────────▼─────────────────┐         │
    │   │ Prism mocks (TMF642/628/621/CAMARA) │         │
    │   │ NextGCore NWDAF (h2c fix applied)    │         │
    │   │ ConfigMap (single source of truth)   │         │
    │   └──────────────────────────────────────┘         │
    │                                                   │
    │   Containerlab (c9s or separate VM)                │
    │   ┌──────────────────────────────────┐            │
    │   │ Nokia SRL │ Cisco XRd │ ...      │            │
    │   │ SSH-reachable device endpoints   │            │
    │   └──────────────────────────────────┘            │
    └───────────────────────────────────────────────────┘

    Output: OSFT-format JSONL ──────► Farbod's team
            (single-turn + multi-turn)
```

### sdg_hub Pipeline Flow (18 blocks)

```
Input DataFrame (tool_list, mcp_server_name, mcp_server_description)
    │
    ▼
[1] build_exploration_prompt ──► [2] explore_server (AgentBlock → Langflow)
    │
    ▼
[3-4] extract_exploration ──► parse_exploration (<server_understanding>)
    │
    ▼
[5] multiply_tool_rows (×10, shuffled) ──► [6] sample_tools (2 random)
    │
    ▼
[7] build_question_gen_prompt ──► [8] generate_questions (LLMChatBlock → Gemma 4)
    │
    ▼
[9-10] extract_question ──► parse_question_fields
    │
    ▼
[11-12] build_quality_check_prompt ──► score_question_quality (LLMChatBlock)
    │
    ▼
[13-14] extract+parse quality ──► filter_low_quality_questions (keep "good"/"excellent")
    │
    ▼
[15] run_expert_trajectory (AgentBlock → Langflow, calls MCP tools)
    │
    ▼
[16] extract_agent_text (text + tool trace)
    │
    ▼
[17] build+score+extract+parse response_quality
    │
    ▼
[18] filter_incomplete_responses (keep "mostly/fully complete")
    │
    ▼
Output DataFrame (filtered tool-calling trajectories)
```

### Recommended Project Structure

```
sdg/
├── notebooks/
│   ├── 01-dry-run.ipynb            # 10-example dry-run for format validation (D-19)
│   ├── 02-exploration.ipynb         # Interactive MCP server exploration
│   └── 03-production-run.ipynb      # Full 8.5K-14K generation run
├── scripts/
│   ├── serve-gemma4.sh              # vLLM launch script for Gemma 4
│   ├── start-agent.sh               # Langflow/LangGraph agent startup
│   ├── run-generation.py            # Production pipeline runner
│   ├── run-evaluation.py            # Three-stage verification runner
│   ├── serialize-osft.py            # Trajectory → OSFT JSONL serializer
│   └── validate-osft-schema.py      # OSFT format validation checker
├── config/
│   ├── flow-training.yaml           # sdg_hub training flow overrides
│   ├── flow-evaluation.yaml         # sdg_hub evaluation flow overrides
│   ├── seed-scenarios.yaml          # Curriculum seed taxonomy
│   └── model-config.yaml            # vLLM + Gemma 4 serving config
├── data/
│   ├── seeds/                       # Input seed DataFrames per curriculum stage
│   ├── raw/                         # Raw generation output
│   ├── filtered/                    # Post-verification filtered output
│   └── delivery/                    # Final OSFT JSONL (single-turn + multi-turn)
└── README.md                        # Recipe documentation for Farbod's team
```

### Pattern 1: sdg_hub Flow Configuration

**What:** Configure the MCP distillation training flow to use our MCP Gateway and Gemma 4 teacher model.
**When to use:** Setting up the pipeline for the first time and for production runs.

```python
# Source: sdg_hub README + flow.yaml analysis [CITED: github.com/Red-Hat-AI-Innovation-Team/sdg_hub]
from sdg_hub import FlowRegistry, Flow

FlowRegistry.discover_flows()
flow = Flow.from_yaml(FlowRegistry.get_flow_path("MCP Server Distillation"))

# Teacher model: Gemma 4 31B via vLLM's OpenAI-compatible API
flow.set_model_config(
    model="hosted_vllm/google/gemma-4-31B-it",  # LiteLLM provider prefix
    api_key="<VLLM_API_KEY>",
    api_base="http://vllm-gemma4.rhoai-sdg.svc:8000/v1",
)

# Agent: Langflow wrapping MCP Gateway tools
flow.set_agent_config(
    agent_framework="langflow",
    agent_url="http://langflow.rhoai-sdg.svc:7860/api/v1/run/<flow-id>",
    agent_api_key="<LANGFLOW_API_KEY>",
)

# Runtime overrides for volume/diversity
result = flow.generate(
    seed_dataset,
    runtime_params={
        "multiply_tool_rows": {"num_samples": 20},  # More diversity
        "sample_tools": {"num_samples": 3},          # 3-tool subsets
    },
)
```

### Pattern 2: OSFT JSONL Format (Tool-Calling Conversations)

**What:** The expected output format for Training Hub's OSFT algorithm.
**When to use:** Serializing sdg_hub traces into the delivery JSONL.

```jsonl
{"messages": [{"role": "system", "content": "You are a telecom NOC fault prediction assistant with access to the following tools:\n\n<tools>\n[{\"type\": \"function\", \"function\": {\"name\": \"tmf642_list_alarms\", \"description\": \"List or find Alarm objects\", \"parameters\": {\"type\": \"object\", \"properties\": {\"severity\": {\"type\": \"string\", \"enum\": [\"critical\", \"major\", \"minor\", \"warning\", \"indeterminate\"]}}}}}, ...]\n</tools>"}, {"role": "user", "content": "Check if there are any critical alarms on our network equipment."}, {"role": "assistant", "content": null, "tool_calls": [{"id": "call_abc123", "type": "function", "function": {"name": "tmf642_list_alarms", "arguments": "{\"severity\": \"critical\"}"}}]}, {"role": "tool", "tool_call_id": "call_abc123", "content": "{\"id\": \"8675309\", \"alarmType\": \"environmentalAlarm\", \"perceivedSeverity\": \"critical\", \"probableCause\": \"rectifierLowVoltage\"}"}, {"role": "assistant", "content": "I found a critical environmental alarm (ID: 8675309) indicating a rectifier low voltage condition..."}]}
```

**Critical caveat:** Training Hub's OSFT documentation only explicitly shows `system/user/assistant` roles with `content` fields. The `tool_calls` array in assistant messages and `tool` role with `tool_call_id` follow the OpenAI/HuggingFace TRL convention and are referenced in PITFALLS.md Pitfall #5, but are NOT explicitly documented in Training Hub's README or examples. **This format MUST be validated via D-19's dry-run with Farbod's team.** [ASSUMED]

### Pattern 3: h2c Prior-Knowledge Client for NWDAF

**What:** Fix the httpx2 client to speak HTTP/2 cleartext (h2c) to NextGCore's NWDAF API.
**When to use:** Replacing the current `httpx2.AsyncClient` in `mcp/nwdaf/server.py`.

```python
# Source: httpcore2 HTTP/2 docs [CITED: pydantic.dev/docs/httpx2/httpcore2/http2/]
import httpcore2
import httpx2

# Prior-knowledge mode: disable HTTP/1.1, force HTTP/2
# This sends the HTTP/2 connection preface directly on cleartext connections
h2_transport = httpcore2.AsyncConnectionPool(http1=False, http2=True)

client = httpx2.AsyncClient(
    base_url=get_backend_url(),
    transport=h2_transport,
)
```

**Caveat:** httpcore2's documentation says "you should still expect to see HTTP/1.1 connections for any http:// URLs" in default mode, but the prior-knowledge mode (`http1=False, http2=True`) forces HTTP/2 regardless. This approach bypasses both ALPN negotiation and h2c Upgrade -- the client sends the HTTP/2 connection preface directly. Verified that `httpx2[http2]` installs `h2` as a dependency. The approach needs runtime testing against the actual NextGCore endpoint. [ASSUMED -- prior-knowledge h2c behavior inferred from httpcore2 docs, not tested against NextGCore]

### Anti-Patterns to Avoid

- **Calling MCP servers directly from sdg_hub:** sdg_hub's `AgentBlock` requires an agent framework (Langflow/LangGraph) as an intermediary. Do not attempt to wire sdg_hub to the MCP Gateway directly -- the agent framework handles tool selection, parameter filling, and trace capture.
- **Using generic tool-call parser for Gemma 4:** Gemma 4 uses a custom non-JSON serialization (`<|tool_call>call:func{key:<|"|>val<|"|>}<tool_call|>`). Using `--tool-call-parser hermes` or any other parser will fail silently. Must use `--tool-call-parser gemma4` specifically. [CITED: docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html]
- **Assuming tool_calls format works with OSFT without validation:** The single highest-risk assumption. Generate 10 examples and validate with Farbod's team before committing to 8.5K-14K generation.
- **Patching the two-copy ConfigMap separately:** The whole point of D-17 is to stop doing this. Fix the sync problem first, then add new device backend entries.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SDG pipeline orchestration | Custom generation scripts | sdg_hub flows | 18-block pipeline with quality gating, async LLM calls, built-in diversity controls |
| Tool-call trace normalization | Custom parser | sdg_hub's `normalize_tool_trace()` in eval_utils.py | Handles three input formats, matches call/result pairs by tool_call_id |
| Gemma 4 tool-call parsing | Custom parser | vLLM's `gemma4_tool_parser` | Handles Gemma 4's custom `<|tool_call>` serialization format, streaming, and edge cases |
| Containerlab topology generation | New topology code | Existing `containerlab.py` in this repo | Phase 2 already built this with vendor-to-kind mappings for Nokia/Cisco/Juniper/Arista |
| Containerlab on Kubernetes | Manual docker-in-docker pods | Clabernetes Helm chart | Handles DinD, VXLAN tunnel stitching, topology splitting into per-node deployments |

**Key insight:** This phase is about CONFIGURING and RUNNING existing tools (sdg_hub, vLLM, Clabernetes, Training Hub), not building new ones. The custom code is limited to: the OSFT serializer, security fixes, the h2c transport fix, and spec enrichment. Everything else is configuration.

## Common Pitfalls

### Pitfall 1: OSFT Data Format Mismatch (HIGHEST RISK)

**What goes wrong:** 10,000 tool-calling examples generated but Training Hub's OSFT cannot parse the `tool_calls`/`tool` role structure because it was never tested with this format.
**Why it happens:** Training Hub's OSFT docs show only `system/user/assistant` with `content` fields. The `tool_calls` extension is convention, not documented.
**How to avoid:** D-19 dry-run: generate 10 examples in the first week, have Farbod's team run `osft(data_path="dry-run.jsonl")` and confirm it tokenizes correctly. If it fails, determine whether Training Hub needs a patch or if the data needs to be pre-tokenized differently.
**Warning signs:** `osft()` silently succeeds but loss values are abnormally high (masking wrong tokens). Or it fails with a parsing error on the `tool_calls` field.

### Pitfall 2: Langflow/LangGraph Agent Not Connecting to MCP Gateway

**What goes wrong:** sdg_hub's `AgentBlock` calls Langflow, but Langflow cannot reach the MCP Gateway or fails to authenticate.
**Why it happens:** Cross-cluster networking (OpenShift AI to existing cluster), JWT token acquisition, MCP protocol handshake through the RHCL gateway.
**How to avoid:** Test the agent -> gateway connection manually (curl the gateway from the OpenShift AI cluster, verify JWT flow) before configuring sdg_hub. Build and test the Langflow/LangGraph agent in isolation first.
**Warning signs:** `explore_server` block times out (300s default). Agent returns empty tool traces.

### Pitfall 3: Gemma 4 Tool-Call Parsing Failures Under Load

**What goes wrong:** At scale (8.5K-14K requests), vLLM's Gemma 4 tool-call parser produces `<pad>` tokens or drops tool calls missing the `call:` marker (~0.4% rate in production).
**Why it happens:** Known vLLM bugs: concurrent request `<pad>` token issue (#39392), missing `call:` marker issue (PR #54778).
**How to avoid:** Pin vLLM to latest (0.31.0 should have the PR #54778 fix). Limit concurrent requests (`--max-num-seqs` flag). Add post-generation validation that checks every trace has at least one tool call.
**Warning signs:** Empty `tool_calls` arrays in traces. `<pad>` tokens in model output.

### Pitfall 4: Clabernetes Fails on OpenShift Due to CRI-O Incompatibility

**What goes wrong:** Clabernetes pods fail to start because OpenShift's CRI-O runtime does not support the nested Docker daemon that Clabernetes expects.
**Why it happens:** Clabernetes uses docker-in-docker; OpenShift uses CRI-O, not Docker. The privileged SCC may not be sufficient for DinD on CRI-O.
**How to avoid:** Test Clabernetes on the existing OpenShift cluster early. If it fails, fall back to running Containerlab on a separate VM with SSH/management network reachable from the otel25-mcp pods. This fallback does not require Clabernetes.
**Warning signs:** Pod CrashLoopBackOff with Docker daemon startup errors.

### Pitfall 5: h2c Fix Breaks Prism Compatibility

**What goes wrong:** The h2c transport fix for NWDAF (D-15) makes the client HTTP/2-only, but if the ConfigMap is switched back to a Prism backend (HTTP/1.1), the client cannot connect.
**Why it happens:** Prior-knowledge mode (`http1=False`) disables HTTP/1.1 entirely.
**How to avoid:** Make the transport configurable: use h2c transport when NWDAF_BASE_URL points to NextGCore (port 7777), use default httpx2 transport when it points to Prism (port 4010). Detect based on URL or add a ConfigMap key `NWDAF_PROTOCOL=h2c|http1.1`.
**Warning signs:** Connection errors when switching NWDAF backend in ConfigMap.

## Code Examples

### CR-01 Fix: Wire command_allowlist.yaml into safety.validate_command()

```python
# Source: 02-REVIEW.md CR-01 recommendation [CITED: .planning/phases/02-mcp-tooling-foundation/02-REVIEW.md]
# In mcp/mcp-telecom/src/mcp_telecom/safety.py

import os
from pathlib import Path
import yaml

_ALLOWLIST_PATH = os.getenv(
    "MCP_TELECOM_ALLOWLIST_FILE",
    str(Path(__file__).parent.parent.parent / "command_allowlist.yaml"),
)

_allowlist_cache: list[str] | None = None

def _load_allowlist() -> list[str]:
    global _allowlist_cache
    if _allowlist_cache is not None:
        return _allowlist_cache
    p = Path(_ALLOWLIST_PATH)
    if not p.exists():
        _allowlist_cache = []
        return _allowlist_cache
    data = yaml.safe_load(p.read_text()) or {}
    _allowlist_cache = data.get("allowed_commands") or []
    return _allowlist_cache

def validate_command(command: str) -> str | None:
    cmd = command.strip()
    if not cmd:
        return "Empty command"

    # Existing safety check (blocked patterns + allowed prefixes)
    if not is_safe_command(cmd):
        return (
            f"Command blocked for safety: '{cmd}'. "
            f"Only read-only commands are allowed."
        )

    # NEW: Allowlist enforcement (D-13 CR-01)
    allowlist = _load_allowlist()
    if not allowlist:
        return (
            "Command blocked: command_allowlist.yaml has no allowed commands. "
            "Populate the allowlist before executing commands on devices."
        )
    if not any(cmd.lower().startswith(prefix.lower()) for prefix in allowlist):
        return f"Command blocked: not in command_allowlist.yaml allowed list."

    return None
```

### CR-02 Fix: Sanitize interface argument

```python
# In mcp/mcp-telecom/src/mcp_telecom/tools/interfaces.py
import re

_INTERFACE_RE = re.compile(r"^[A-Za-z0-9_./:-]+$")

def show_interface_detail(
    device_manager: DeviceManager,
    audit: AuditLogger,
    device: str,
    interface: str,
) -> str:
    """Show detailed statistics for a specific interface."""
    if not _INTERFACE_RE.fullmatch(interface):
        return f"Error: invalid interface name: {interface!r}"
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "interface_detail", interface=interface)
    # Also route through validate_command for defense-in-depth
    from mcp_telecom.safety import validate_command
    err = validate_command(cmd)
    if err:
        return f"Error: {err}"
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_interface_detail", True, len(output))
    return output
```

### CR-03 Fix: Contain backup_file to backups directory

```python
# In mcp/mcp-telecom/src/mcp_telecom/server.py, compare_configs function
from pathlib import Path

BACKUPS_DIR = Path("backups").resolve()

@mcp.tool()
def compare_configs(device: str, backup_file: str) -> str:
    try:
        import difflib
        # CR-03 fix: resolve against BACKUPS_DIR, reject path traversal
        candidate = (BACKUPS_DIR / Path(backup_file).name).resolve()
        if not candidate.is_relative_to(BACKUPS_DIR):
            return f"Error: backup_file must be within the backups/ directory"
        if not candidate.exists():
            return f"Error: Backup file not found: {backup_file}"
        previous = candidate.read_text()
        # ... rest of diff logic unchanged
```

### vLLM Gemma 4 Serving Script

```bash
# Source: vLLM Gemma 4 docs [CITED: docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html]
vllm serve google/gemma-4-31B-it \
    --dtype bfloat16 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --enable-auto-tool-choice \
    --tool-call-parser gemma4 \
    --reasoning-parser gemma4 \
    --chat-template examples/tool_chat_template_gemma4.jinja \
    --port 8000 \
    --host 0.0.0.0
```

**Hardware:** 1x H100 80GB (BF16) or 1x A100 80GB (with FP8 quantization: `--quantization fp8`). For 2x A100 40GB: add `--tensor-parallel-size 2`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| NeMo Data Designer for SDG | sdg_hub MCP distillation | Phase 4 CONTEXT.md (D-01) | sdg_hub is purpose-built for MCP tool-calling distillation |
| Qwen3.8-27B teacher model | Gemma 4 31B dense | Phase 4 CONTEXT.md (D-08) | No thinking overhead, +10% Tau2 Telecom benchmark gain |
| httpx2 default HTTP/1.1 | httpcore2 h2c prior-knowledge | Phase 4 (D-15) | Fixes NWDAF live backend verification blocker |
| Two unsynced ConfigMap copies | Single source of truth | Phase 4 (D-17) | Eliminates silent backend routing drift |
| Mock-only MCP-Telecom | Containerlab device backend | Phase 4 (D-12) | Enables execution-verified device-layer training examples |

**Deprecated/outdated:**
- NeMo Data Designer references in STACK.md/SUMMARY.md: superseded by D-01 for the SDG framework choice
- ARCHITECTURE.md Pattern 5 teacher model setup: still valid pattern, but model choice changed to Gemma 4

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Training Hub OSFT accepts `tool_calls` array and `tool` role in messages JSONL | Pattern 2, Pitfall 1 | HIGH -- entire dataset may need reformatting or mini_trainer may need a patch. Mitigated by D-19 dry-run. |
| A2 | httpcore2 `http1=False, http2=True` sends HTTP/2 preface on cleartext http:// URLs (h2c prior-knowledge) | Pattern 3, Pitfall 5 | MEDIUM -- if this does not work, fallback is raw `h2` library socket-level code, which is more complex but proven. |
| A3 | Clabernetes docker-in-docker works on OpenShift with CRI-O and privileged SCC | Pitfall 4 | MEDIUM -- fallback is running Containerlab on a separate VM, which is simpler but requires network routing. |
| A4 | sdg_hub's `AgentBlock` can reach an MCP Gateway through Langflow/LangGraph with JWT auth | Pitfall 2, Architecture | MEDIUM -- the agent framework is the bridge; if Langflow's MCP integration does not support JWT, a custom adapter is needed. |
| A5 | Gemma 4 31B dense is sufficient as both teacher model and semantic judge (D-11) | Claude's Discretion | LOW -- if quality is insufficient, the judge can be a separate model instance or a different model entirely. |
| A6 | sdg_hub 0.9.4 flow YAML structure matches the documented 18-block pipeline | Standard Stack | LOW -- the flow was fetched from the GitHub repo and matched the version on PyPI at the time of the GitHub fetch; minor version differences possible if the PyPI latest (0.9.4) differs from main branch. |

## Open Questions (RESOLVED)

1. **Does Training Hub's OSFT tokenizer handle `tool_calls` and `tool` role correctly?**
   - What we know: OSFT accepts `messages` JSONL with system/user/assistant roles. HuggingFace TRL 0.19.0+ supports tool-calling in SFT. PITFALLS.md Pitfall #5 describes the expected format.
   - What is unclear: Whether Training Hub's mini_trainer backend passes these fields through to the tokenizer and correctly masks non-assistant tokens including tool responses.
   - Recommendation: D-19 dry-run in the first week. If it fails, determine whether the issue is in mini_trainer (needs a patch) or in the chat template (needs tool-calling support configured).
   - **RESOLVED:** D-19 dry-run gate implemented in 04-07 Task 3 (checkpoint:human-verify). Farbod's team validates 10-example dry-run before production run proceeds.

2. **Can the Langflow/LangGraph agent on OpenShift AI reach the RHCL MCP Gateway on the existing cluster?**
   - What we know: The gateway Route is at `mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com` with TLS edge termination. Keycloak client-credentials flow is built.
   - What is unclear: Whether the OpenShift AI cluster can reach this hostname (DNS resolution, firewall rules between clusters).
   - Recommendation: Simple curl test from the OpenShift AI cluster in the first task. If blocked, need to configure network policy or use a different exposure mechanism.
   - **RESOLVED:** Gateway reachability test implemented as Test 1 in 04-05 Task 2 (verify-langflow-mcp.sh). Script acquires JWT and curls the gateway endpoint from the RHOAI cluster.

3. **Does Langflow/LangGraph have native MCP protocol support, or do we need to build a bridge?**
   - What we know: sdg_hub's `AgentBlock` supports `langflow` and `langgraph` agent frameworks. The MCP Gateway serves MCP protocol (Streamable HTTP + SSE).
   - What is unclear: Whether Langflow/LangGraph can consume MCP protocol endpoints directly as tool providers, or if we need to build an adapter that converts MCP tool schemas to Langflow/LangGraph's tool format.
   - Recommendation: Research Langflow's MCP support during the first implementation task. If not supported, build a lightweight adapter that calls the gateway's `tools/list` and `tools/call` endpoints.
   - **RESOLVED:** Implemented as 04-05 Task 2 (verify-langflow-mcp.sh). Script tests native MCP support (MCP_NATIVE=true/false) and provides contingency adapter instructions if absent.

4. **What is the exact Containerlab topology shape needed?**
   - What we know: `containerlab.py` supports Nokia SRL, Cisco XRd, Cisco IOSxe, Cisco NX-OS, Juniper cRPD, Arista cEOS. MCP-Telecom has 58 device-layer tools covering routing, interfaces, MPLS, VPN, QoS, SNMP, config management.
   - What is unclear: How many devices, which vendors, and what topology (basic ring, MPLS core, datacenter spine-leaf, ISP edge) gives the best coverage for SDG.
   - Recommendation: Start with the `basic` scenario (3x Nokia SRL ring) for initial testing. Expand to `mpls_core` (Nokia + Cisco multi-vendor) for the production run to cover more vendor-specific tool variations.
   - **RESOLVED:** 04-06 Task 1 uses the "basic" Nokia SRL ring topology (3 devices) as the initial deployment shape, per Claude's discretion on exact topology shape noted in CONTEXT.md.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| OpenShift AI cluster | D-06, D-10 | Assumed YES (D-10 says GPU access available) | N/A | -- |
| vLLM GPU runtime | D-08, D-09 | Assumed YES (D-10) | 0.31.0 target | -- |
| H100 80GB (or equivalent) | Gemma 4 31B serving | Assumed YES (D-10) | -- | 2x A100 40GB with tensor parallelism, or A100 80GB with FP8 |
| Containerlab images | D-12 | Unknown -- requires container image access | -- | Use only Nokia SRL (open-source ghcr.io/nokia/srlinux:latest) |
| Existing OpenShift cluster | All backend/gateway ops | YES (Phases 1-3 deployed) | -- | -- |
| RHCL MCP Gateway | D-07, SDG-01 | YES (Phase 3 deployed) | 1.4.x | -- |
| Keycloak | D-07 | YES (Phase 3 deployed) | -- | -- |
| NextGCore NWDAF | D-15 | YES (Phase 1 deployed, h2c bug blocking) | -- | Fall back to Prism NWDAF mock (would need to build one first) |
| Langflow or LangGraph | sdg_hub agent | NOT DEPLOYED | -- | Must deploy on OpenShift AI cluster as Phase 4 setup |
| Helm | Clabernetes install | Check on cluster | -- | `oc` apply raw manifests |

**Missing dependencies with no fallback:**
- Langflow or LangGraph agent framework -- must be deployed on the OpenShift AI cluster
- Network connectivity between OpenShift AI cluster and existing cluster gateway Route

**Missing dependencies with fallback:**
- Containerlab vendor images (Cisco, Juniper) may require licensing -- fall back to Nokia SRL (fully open-source)
- If Clabernetes fails on OpenShift, fall back to Containerlab on a separate VM

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing in mcp/mcp-telecom) + manual notebook validation |
| Config file | mcp/mcp-telecom/pyproject.toml (existing) |
| Quick run command | `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout 30` |
| Full suite command | `cd mcp/mcp-telecom && uv run pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SDG-01 | sdg_hub flow connects to MCP Gateway and generates traces | integration/manual | Manual: run `01-dry-run.ipynb` | No -- Wave 0 |
| SDG-02 | Curriculum ordering produces examples in correct progression | manual | Manual: inspect output distribution | No -- Wave 0 |
| SDG-03 | Both single-turn and multi-turn JSONL formats valid | unit | `pytest sdg/scripts/test_serialize_osft.py -x` | No -- Wave 0 |
| SDG-04 | Quality filtering reduces raw count to target range | integration/manual | Manual: count rows post-filter | No -- Wave 0 |
| SDG-05 | JSONL validates against OSFT schema | unit | `pytest sdg/scripts/test_validate_osft.py -x` | No -- Wave 0 |
| CR-01 | command_allowlist.yaml enforced in validate_command() | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_allowlist.py -x` | Yes (needs rewrite) |
| CR-02 | Interface argument sanitized | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_interfaces.py -x` | No -- Wave 0 |
| CR-03 | backup_file contained to backups/ dir | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_compare_configs.py -x` | No -- Wave 0 |
| D-15 | NWDAF client speaks h2c to NextGCore | integration | Manual: curl test from pod | No -- manual only |

### Sampling Rate
- **Per task commit:** Quick run for any MCP-Telecom changes: `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout 30`
- **Per wave merge:** Full MCP-Telecom suite + manual notebook validation
- **Phase gate:** All unit tests green + Farbod's team confirms OSFT dry-run success

### Wave 0 Gaps
- [ ] `mcp/mcp-telecom/tests/test_allowlist.py` -- rewrite to test production `validate_command()` instead of local copy (CR-01)
- [ ] `mcp/mcp-telecom/tests/test_interfaces.py` -- new test for interface argument sanitization (CR-02)
- [ ] `mcp/mcp-telecom/tests/test_compare_configs.py` -- new test for backup_file containment (CR-03)
- [ ] `sdg/scripts/test_serialize_osft.py` -- validates OSFT JSONL serializer output (SDG-03, SDG-05)
- [ ] `sdg/scripts/test_validate_osft.py` -- validates OSFT schema compliance (D-04)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Keycloak JWT client-credentials (existing, D-07 reuses) |
| V3 Session Management | no | Stateless JWT, no sessions |
| V4 Access Control | yes | Command allowlist enforcement (CR-01), path containment (CR-03) |
| V5 Input Validation | yes | Interface argument regex (CR-02), command safety validation |
| V6 Cryptography | no | No crypto operations in this phase |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command injection via interface argument (CR-02) | Tampering | Regex allowlist `^[A-Za-z0-9_./:-]+$` |
| Arbitrary file read via backup_file (CR-03) | Information Disclosure | Path containment to BACKUPS_DIR |
| Unenforced command allowlist (CR-01) | Elevation of Privilege | Wire allowlist into `validate_command()` at startup |
| Cross-cluster JWT token theft | Spoofing | TLS edge termination on gateway Route; short-lived tokens |
| Prompt injection causing agent to call destructive device commands | Tampering | Command allowlist + safety.py blocked patterns (defense in depth) |

## Detailed Research Findings

### 1. sdg_hub Pipeline Mechanics (D-01 through D-04)

**Version:** 0.9.4 on PyPI (latest). GitHub main branch may be ahead. [VERIFIED: PyPI registry]

**Architecture:** sdg_hub is a YAML-defined pipeline framework. Pipelines ("flows") consist of ordered "blocks" (PromptBuilderBlock, LLMChatBlock, AgentBlock, TagParserBlock, ColumnValueFilterBlock, etc.). The MCP Server Distillation flow has 18 blocks in two major phases:
1. **Generation** (blocks 1-18 in `mcp_distillation_training`): exploration, question synthesis, quality filtering, expert trajectory generation, response quality filtering
2. **Evaluation** (separate flow in `mcp_distillation_evaluation`): programmatic metrics (tool recall, precision, order match, parameter match) + LLM-as-judge (6 dimensions on 1-10 scale) [CITED: github.com/Red-Hat-AI-Innovation-Team/sdg_hub/tree/main/examples/agentic/mcp_distillation_evaluation]

**Key finding -- agent framework required:** The `AgentBlock` does not call MCP servers directly. It calls an agent framework endpoint (Langflow or LangGraph). The flow YAML hardcodes `agent_framework: "langflow"` and `agent_url: "http://localhost:7860/api/v1/run/default"`. For our setup, we need a Langflow or LangGraph agent deployed on the OpenShift AI cluster that wraps the remote MCP Gateway's tools. [CITED: sdg_hub flow.yaml]

**Input format:** Requires a DataFrame/dataset with columns: `tool_list` (JSON array of tool schemas), `mcp_server_name`, `mcp_server_description`. These describe the MCP server(s) the pipeline will generate training data for. For our case, this would describe the MCP Gateway's exposed tools. [CITED: sdg_hub flow.yaml metadata]

**Quality gating:** Two filter stages:
- `filter_low_quality_questions`: keeps rows rated "good" or "excellent" by the LLM judge
- `filter_incomplete_responses`: keeps responses rated "mostly complete" or "fully complete"

Expected yield: if generation produces 14,000 raw, and each filter retains ~60-70% (typical for quality-gated LLM pipelines), the final count would be ~6,000-7,000. This aligns with the 5K-10K target from 8.5K-14K raw. [ASSUMED]

**Three-stage verification (D-02, D-04):** The `mcp_distillation_evaluation` flow provides:
1. **Format check:** programmatic metrics (tool recall, precision) -- essentially schema validation
2. **Execution check:** the expert trajectory is generated by actually calling tools through the agent (AgentBlock), so execution verification is inherent in the generation flow
3. **Semantic check:** LLM-as-judge scoring on task fulfillment, grounding, tool appropriateness, parameter accuracy, dependency awareness, parallelism/efficiency

The evaluation flow's `eval_utils.py` `normalize_tool_trace()` function handles three formats of tool traces and normalizes them to `[{name, input, output}]` for comparison. `compute_tool_metrics()` provides programmatic scoring. [CITED: sdg_hub eval_utils.py]

**OSFT compliance check (D-04):** Should be added as an additional validation step inside or after `mcp_distillation_evaluation`. Check that each output example has: valid `messages` array, `tool_calls` with unique `id` fields, matching `tool_call_id` in subsequent `tool` role messages, and all required OSFT fields present.

### 2. Training Hub / OSFT Format (D-18, D-19)

**Version:** training-hub 0.10.0 on PyPI (latest). [VERIFIED: PyPI registry]

**OSFT = Orthogonal Subspace Fine-Tuning:** A continual learning technique (Nayak et al., arXiv:2504.07097) that fine-tunes models while preserving prior capabilities. Uses adaptive SVD-based decomposition. Backend: mini_trainer. [CITED: github.com/Red-Hat-AI-Innovation-Team/training_hub]

**Data format -- documented:** JSONL with `messages` array. Supported roles: `system`, `user`, `assistant`, `pretraining`. Each message has `role` and `content` fields. Optional `reasoning_content` for reasoning traces. [CITED: github.com/red-hat-data-services/red-hat-ai-examples/tree/main/examples/fine-tuning/osft]

**Data format -- tool-calling (NOT documented):** Training Hub's OSFT documentation does NOT explicitly show `tool_calls` arrays or `tool` role messages. The mini_trainer README says it "does not include data processing utilities" and defers tokenization to instructlab-training. For the data to work, the tokenizer/chat template must support the `tool_calls` extension to the messages format. [ASSUMED]

**Practical approach:** The OSFT `messages` JSONL format is likely compatible with tool-calling conversations IF the model's chat template (Gemma 4's tokenizer) knows how to handle `tool_calls` and `tool` roles. The tokenization step would use `tokenizer.apply_chat_template()` which respects these fields. The D-19 dry-run is essential to validate this assumption.

**Alternative if incompatible:** If OSFT cannot handle the tool-calling message format directly, the fallback is to pre-tokenize the data ourselves using the Gemma 4 tokenizer with its chat template, producing `input_ids` + `labels` JSONL, and using mini_trainer's pre-processed data path (`use_processed_dataset=True`). This gives full control over masking and tokenization.

### 3. vLLM + Gemma 4 Serving (D-08, D-09)

**Model:** google/gemma-4-31B-it (31B dense, Apache 2.0, July 2026 refresh) [ASSUMED -- model card details from training knowledge]

**vLLM version:** 0.31.0 (released 2026-10-05). Native Gemma 4 support including `gemma4_tool_parser`. [VERIFIED: PyPI registry]

**Serving configuration:**
```
vllm serve google/gemma-4-31B-it \
    --dtype bfloat16 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --enable-auto-tool-choice \
    --tool-call-parser gemma4 \
    --reasoning-parser gemma4 \
    --chat-template examples/tool_chat_template_gemma4.jinja \
    --port 8000
```
[CITED: docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html]

**Hardware requirements:** 
- BF16 (full precision): ~62GB VRAM. Fits on 1x H100 80GB with 8K context.
- FP8 quantization: ~31GB. Fits on 1x A100 80GB with 16K context.
- 2x A100 40GB with tensor parallelism: adds ~10-15% latency overhead.
[CITED: huggingface.co/google/gemma-4-31B-it/discussions/52, various hardware guides]

**Known issues:**
1. Concurrent `<pad>` token bug (#39392) -- shared mutable state in parser. Mitigate by limiting `--max-num-seqs`.
2. Missing `call:` marker (PR #54778) -- Gemma 4 occasionally omits `call:` prefix, parser drops the tool call. ~0.4% loss rate. Fix merged; ensure vLLM 0.31.0 includes it.
3. Custom serialization: Gemma 4 uses `<|tool_call>call:func_name{key:<|"|>value<|"|>}<tool_call|>` -- NOT JSON. The `gemma4` parser handles this.
[CITED: github.com/vllm-project/vllm/issues/39392, github.com/vllm-project/vllm/pull/54778]

**OpenAI-compatible API:** vLLM exposes `/v1/chat/completions` with tool-calling support. sdg_hub's `LLMChatBlock` can call this directly using LiteLLM's `hosted_vllm/` provider prefix.

### 4. Containerlab Device Simulator (D-12, D-14)

**Existing code:** `mcp/mcp-telecom/src/mcp_telecom/containerlab.py` provides:
- `ContainerlabManager.generate_topology(devices, links)` -- generates Containerlab YAML from a list of `DeviceInfo` objects
- `ContainerlabManager.generate_devices_yaml(lab_name, topology_data)` -- generates `devices.yaml` from deployed topology
- `ContainerlabManager.get_deploy_commands(topology_file)` -- returns `containerlab deploy/inspect/destroy` commands
- `ContainerlabManager.generate_test_scenario(scenario)` -- generates predefined scenarios: basic (3x Nokia SRL ring), mpls_core (Nokia PE + Cisco P), datacenter (Arista spine + Cisco leaf), isp_edge (multi-vendor)
- Vendor-to-kind mappings for Nokia SRL, Cisco XRd/IOSxe/NX-OS, Juniper cRPD, Arista cEOS
[VERIFIED: direct source code reading]

**Deployment on OpenShift -- Clabernetes:**
- Clabernetes (c9s) runs containerlab inside Kubernetes via docker-in-docker pods
- Install: `helm upgrade --install --create-namespace --namespace c9s clabernetes oci://ghcr.io/srl-labs/clabernetes/clabernetes`
- Convert topology: `clabverter --stdout --naming non-prefixed | kubectl apply -f -`
- Each lab node becomes a Deployment with one Pod containing a nested Docker daemon
- Inter-node links use VXLAN tunnels across Kubernetes workers
- Pods expose SSH/management ports via LoadBalancer Services
[CITED: containerlab.dev/manual/clabernetes/quickstart/]

**OpenShift-specific requirements:**
- Privileged SCC for the Clabernetes service account: `oc adm policy add-scc-to-user privileged -n c9s -z clabernetes-manager`
- CRI-O + DinD compatibility is untested and flagged as a risk (Pitfall 4)
[CITED: access.redhat.com/solutions/6375251]

**Topology recommendation (Claude's discretion):**
- Start with `basic` scenario (3x Nokia SRL ring) -- Nokia SRL images are fully open-source (`ghcr.io/nokia/srlinux:latest`), no licensing
- Expand to `mpls_core` for production -- adds Cisco XRd for multi-vendor coverage
- Skip `datacenter` and `isp_edge` unless specifically needed for coverage

**devices.yaml generation:** After Containerlab deployment, use `ContainerlabManager.generate_devices_yaml()` to produce the `devices.yaml` with Containerlab-assigned management IPs. Copy to `mcp/mcp-telecom/devices.yaml`.

### 5. Security Fixes CR-01/02/03 (D-13)

All three fixes are documented in detail in `02-REVIEW.md` with specific code locations and recommended patches. [VERIFIED: direct source code reading]

**CR-01 (command_allowlist.yaml enforcement):**
- Current state: `safety.py:validate_command()` checks blocked patterns and allowed prefixes. `command_allowlist.yaml` exists but is never loaded by any production code. `tests/test_allowlist.py` tests a reimplemented copy, not production code.
- Fix: Load `command_allowlist.yaml` at startup in `safety.py`, add allowlist prefix check to `validate_command()`. Rewrite `test_allowlist.py` to import from `safety` module.
- Lines: `safety.py:64` (`validate_command`), `server.py:505-530` (`run_command`)

**CR-02 (interface argument injection):**
- Current state: `show_interface_detail` in `tools/interfaces.py` passes `interface` directly to `get_command()` which does `template.format(**kwargs)`. No validation, no `validate_command()` call.
- Fix: Add regex validation `^[A-Za-z0-9_./:-]+$` before formatting. Route the formatted command through `validate_command()`.
- Lines: `tools/interfaces.py:23-35`

**CR-03 (arbitrary file read in compare_configs):**
- Current state: `server.py:462` passes `backup_file` to `Path(...).read_text()` with no containment.
- Fix: Resolve against `BACKUPS_DIR`, use `Path.name` to strip directory traversal, check `is_relative_to()`.
- Lines: `server.py:462-500`

### 6. NWDAF h2c Fix (D-15)

**Problem:** NextGCore's NWDAF API (port 7777) serves HTTP/2 cleartext (h2c). The NWDAF MCP server at `mcp/nwdaf/server.py` uses `httpx2.AsyncClient(base_url=get_backend_url())` which defaults to HTTP/1.1 for `http://` URLs. The client sends an HTTP/1.1 request; NextGCore expects an HTTP/2 connection preface and returns "illegal request line." [VERIFIED: direct source code reading + STATE.md]

**Solution -- httpcore2 prior-knowledge mode:**
- `httpx2[http2]` adds `httpcore2[http2]` and `h2` as dependencies
- `httpcore2.AsyncConnectionPool(http1=False, http2=True)` creates a pool that ONLY speaks HTTP/2
- For cleartext `http://` URLs, this sends the HTTP/2 connection preface directly (prior-knowledge mode)
- Pass this transport to `httpx2.AsyncClient(transport=h2_transport)`
[CITED: pydantic.dev/docs/httpx2/httpcore2/http2/]

**Compatibility concern:** Setting `http1=False` means the client cannot fall back to HTTP/1.1. If the ConfigMap switches NWDAF_BASE_URL back to a Prism backend (HTTP/1.1 only), the h2c client will fail. Solution: make the transport conditional on the backend URL or add a ConfigMap key to select the protocol.

**NWDAF path divergence (noted in server.py header):** NextGCore uses different base paths for AnalyticsInfo (`/nnwdaf-analyticsinfo/v1`) and EventsSubscription (`/nnwdaf-eventssubscription/v1`). The current single `NWDAF_BASE_URL` ConfigMap key cannot represent both. Phase 4 should add a second ConfigMap key (e.g., `NWDAF_EVENTS_BASE_URL`) or encode the full path in each tool function.

### 7. Prism Spec Enrichment (D-16)

**Current state of vendored specs:**
| Spec | Format | Lines | Example mentions | Enrichment needed |
|------|--------|-------|-----------------|-------------------|
| TMF642 Alarm v5.0.1 | OAS 3.0 YAML | 5,160 | 257 | Medium -- has good request/response examples but schema properties lack `example:` values |
| TMF628 Performance v4.0.0 | Swagger 2.0 JSON | 5,318 | 9 | HIGH -- almost no examples |
| TMF621 Trouble Ticket v5.0.1 | OAS 3.0 YAML | 7,030 | 192 | Medium -- has examples but need enrichment |
| CAMARA Location Verification | OAS 3.0 YAML | 687 | 21 | Low -- compact spec, existing examples are decent |
| CAMARA Location Retrieval | OAS 3.0 YAML | 682 | 23 | Low -- compact spec, existing examples are decent |
[VERIFIED: direct file inspection]

**TMF642 already has realistic examples:** The spec includes concrete alarm examples with telecom-specific values -- `alarmType: environmentalAlarm`, `probableCause: rectifierLowVoltage`, `specificProblem: 'ps=3,sl=1,in=8'`, real severity levels, equipment references. The problem is that Prism's DYNAMIC mock generation (for endpoints without examples) uses json-schema-faker which produces "Lorem Ipsum" values from the schema's string/number types. [VERIFIED: direct spec inspection]

**Enrichment strategy:**
1. Add `example:` values at the SCHEMA PROPERTY level in `components/schemas/` -- this is what Prism's dynamic mock generator uses
2. Focus on fields that lack `example:` values: IDs, names, descriptions, timestamps, numeric metrics, enum values
3. TMF628 is the priority -- only 9 example mentions in 5,318 lines of Swagger 2.0 JSON
4. Use TM Forum's User Guide (IG1228 for TMF642, IG1230 for TMF628, IG1229 for TMF621) for realistic values
5. For CAMARA: use GSMA OGW examples (latitude/longitude for real cities, realistic device IDs)

**What "realistic example values" means concretely:**
- TMF642: alarm IDs like `ALARM-2024-0142`, alarm types from the standard set (`communicationsAlarm`, `processingErrorAlarm`, `equipmentAlarm`, `environmentalAlarm`, `qualityOfServiceAlarm`), probable causes from ITU-T X.733 (over 100 defined values), severity levels (`critical`, `major`, `minor`, `warning`, `indeterminate`)
- TMF628: granularity values (`g_5mn`, `g_15mn`, `g_30mn`, `g_1h`, `g_24h`), KPI names (`pmActiveUEDlMean`, `pmRrcConnEstabSucc`), tracking record IDs
- TMF621: ticket priorities (`P1-Critical`, `P2-High`), status values (`acknowledged`, `inProgress`, `resolved`, `closed`), trouble ticket types
- CAMARA: real GPS coordinates (e.g., London: 51.5074/-0.1278, New York: 40.7128/-74.0060), device identifiers matching 3GPP SUPI/GPSI format

### 8. ConfigMap Consolidation (D-17)

**Current state:**
- `backends/openshift/configmap-backend-routing.yaml` -- ConfigMap in `otel25-backends` namespace
- All 6 MCP server deployments in `otel25-mcp` reference `configMap: name: backend-routing` -- a COPY of the above in `otel25-mcp` namespace (Kubernetes ConfigMaps are namespace-scoped)
- The copy carries an annotation documenting the duplication
[VERIFIED: direct file inspection of deployment YAMLs]

**Why two copies exist:** Kubernetes ConfigMap volumes are namespace-scoped. Deployments in `otel25-mcp` cannot mount a ConfigMap from `otel25-backends`. Phase 3 documented this explicitly.

**Consolidation options:**
1. **Move all MCP servers to `otel25-backends`** -- eliminates the cross-namespace problem but breaks the namespace-per-layer convention
2. **Single ConfigMap in a shared namespace** -- create an `otel25-config` namespace readable by both; requires RoleBindings
3. **External ConfigMap sync (e.g., Reflector operator)** -- automatically mirrors ConfigMaps across namespaces; adds an operator dependency
4. **Script-based sync** -- a script that patches both copies atomically; simple but manual

**Recommendation:** Option 4 (script-based sync) is the most pragmatic for a WG project:
- Create `scripts/sync-backend-routing.sh` that reads the canonical `otel25-backends/backend-routing` and patches `otel25-mcp/backend-routing`
- Document the single source of truth as `backends/openshift/configmap-backend-routing.yaml`
- The script runs as part of any backend change (adding Containerlab devices, switching NWDAF to live)
- Low complexity, no operator dependencies, consistent with existing `scripts/verify-*.sh` patterns
[ASSUMED -- this is a recommendation, not a verified pattern]

### 9. Cross-Cluster Gateway Exposure (D-06, D-07)

**Current state:** The MCP Gateway Route is already externally accessible at:
```
https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com
```
TLS edge termination is configured. JWT auth via Keycloak's `mcp` realm is enforced by the AuthPolicy. [VERIFIED: direct file inspection of gateway.yaml and auth-policy.yaml]

**What the OpenShift AI cluster needs:**
1. DNS resolution for `mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com`
2. Network connectivity to the Route's external IP
3. A Keycloak client-credentials grant to obtain JWT tokens

**Keycloak client-credentials flow:**
```bash
# Obtain JWT token from Keycloak
TOKEN=$(curl -s -X POST \
    "https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/realms/mcp/protocol/openid-connect/token" \
    -d "grant_type=client_credentials" \
    -d "client_id=sdg-pipeline" \
    -d "client_secret=<SECRET>" \
    | jq -r '.access_token')

# Call MCP Gateway with JWT
curl -H "Authorization: Bearer $TOKEN" \
    "https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp/v1/tools/list"
```

**Setup needed:**
1. Create a new Keycloak client (`sdg-pipeline`) in the `mcp` realm with `client_credentials` grant type
2. Note the client secret
3. Test connectivity from the OpenShift AI cluster
4. Configure the Langflow/LangGraph agent to use this token

**MCPVirtualServer re-reconciliation risk:** If any `MCPServerRegistration` is added (e.g., for the Containerlab MCP-Telecom backend update), RHCL's controller may overwrite `otel25-gateway/mcp-gateway-config` from its `mcp-system` copy, dropping the `virtualServers` section. Re-merge after any registration change. [VERIFIED: STATE.md blocker]

## Sources

### Primary (HIGH confidence)
- [PyPI: sdg-hub](https://pypi.org/project/sdg-hub/) -- version 0.9.4 confirmed
- [PyPI: training-hub](https://pypi.org/project/training-hub/) -- version 0.10.0 confirmed
- [PyPI: vllm](https://pypi.org/project/vllm/) -- version 0.31.0 confirmed
- [PyPI: httpx2](https://pypi.org/project/httpx2/) -- version 2.13.1 confirmed
- [PyPI: h2](https://pypi.org/project/h2/) -- version 4.4.1 confirmed
- Direct source code reading: `containerlab.py`, `safety.py`, `interfaces.py`, `server.py`, `nwdaf/server.py`, all spec files, deployment YAMLs, gateway configs
- [sdg_hub flow.yaml](https://github.com/Red-Hat-AI-Innovation-Team/sdg_hub/tree/main/examples/agentic/mcp_distillation_training) -- 18-block pipeline structure
- [sdg_hub eval_utils.py](https://github.com/Red-Hat-AI-Innovation-Team/sdg_hub/tree/main/examples/agentic/mcp_distillation_evaluation) -- trace normalization, metrics
- [02-REVIEW.md](/.planning/phases/02-mcp-tooling-foundation/02-REVIEW.md) -- CR-01/02/03 findings

### Secondary (MEDIUM confidence)
- [vLLM Gemma 4 recipe](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html) -- serving flags, hardware requirements
- [vLLM Gemma 4 tool parser docs](https://docs.vllm.ai/en/latest/api/vllm/tool_parsers/gemma4_tool_parser/) -- parser internals
- [httpcore2 HTTP/2 docs](https://pydantic.dev/docs/httpx2/httpcore2/http2/) -- prior-knowledge mode
- [Clabernetes quickstart](https://containerlab.dev/manual/clabernetes/quickstart/) -- Helm install, topology CR
- [Red Hat OSFT example](https://github.com/red-hat-data-services/red-hat-ai-examples/tree/main/examples/fine-tuning/osft) -- OSFT data format

### Tertiary (LOW confidence)
- [vLLM issue #39392](https://github.com/vllm-project/vllm/issues/39392) -- concurrent `<pad>` token bug (status unknown in 0.31.0)
- [Gemma 4 VRAM discussions](https://huggingface.co/google/gemma-4-31B-it/discussions/52) -- hardware requirements from community
- Langflow MCP support -- not verified, assumed based on sdg_hub flow default

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages verified on PyPI with exact versions
- Architecture: MEDIUM -- sdg_hub pipeline flow verified but agent framework integration (Langflow/LangGraph to MCP Gateway) is assumed
- Backend readiness (CR-01/02/03, Prism enrichment): HIGH -- code inspected directly, fixes are concrete
- OSFT format: MEDIUM -- basic messages format verified, but tool_calls extension is assumed
- h2c fix: MEDIUM -- httpcore2 prior-knowledge approach is documented but untested against NextGCore
- Pitfalls: HIGH -- based on direct codebase inspection and documented issues

**Research date:** 2026-10-05
**Valid until:** 2026-10-19 (14 days -- fast-moving due to vLLM/sdg_hub release cadence)
