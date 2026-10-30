# OTel 2.5 SDG Pipeline Recipe

Synthetic Data Generation pipeline for producing telecom tool-calling training
data using Red Hat AI Innovation Team's `sdg_hub` MCP Server Distillation flow.
This recipe generates, verifies, and filters 5,000-10,000 high-quality training
examples from the Phase 3 MCP Gateway's 78 tools, for Farbod's team to run OSFT
(Objective-Specific Fine-Tuning) on OTel 2.0.

## Overview

**What this produces:** OSFT-compatible JSONL training data containing tool-calling
conversation traces across 5 curriculum tiers (single-tool to closed-loop fault
prediction workflows), in both single-turn and multi-turn trajectory formats.

**Who it is for:** Farbod's team at OpenTelco, who will use Training Hub's OSFT
algorithm to fine-tune OTel 2.0 into OTel 2.5 with these training examples.

**Architecture:** The pipeline runs on a separate OpenShift AI (RHOAI) cluster (D-06),
calling the MCP Gateway on the existing cluster via cross-cluster HTTPS + JWT auth (D-07).

```
RHOAI Cluster                      Existing Cluster
+-----------+  +-------+           +-------------------+
| sdg_hub   |->| vLLM  |           | RHCL MCP Gateway  |
| notebooks |  | Gemma4|           | 78 tools (JWT)    |
+-----------+  +-------+           +-------------------+
      |                                    ^
      v                                    |
+-----------+   HTTPS + JWT               |
| Langflow  |-----------------------------+
| Agent     |
+-----------+
```

## Prerequisites

### Software (pinned dependency versions per D-03)

```bash
pip install "sdg-hub==0.9.4"
pip install "training-hub==0.10.0"    # OSFT format reference/validation only
pip install "vllm==0.31.0"            # Served separately, not in pipeline env
pip install "jsonschema" "pyyaml"     # osft_validation.py's tool-output schema gate
```

### Infrastructure

- **OpenShift AI cluster** with GPU access (D-06, D-10):
  - 1x H100 80GB (BF16) or 1x A100 80GB (FP8) for vLLM + Gemma 4 31B
  - Alternatively: 2x A100 40GB with `--tensor-parallel-size 2`
- **Existing cluster** with MCP Gateway running (Phase 3):
  - RHCL MCP Gateway at `mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com`
  - Keycloak at `mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com`
- **Keycloak access**: client credentials for the `sdg-pipeline` client (or
  equivalent client registered in the `mcp` realm)

## Environment Variables

All flow configuration files (`sdg/config/flow-*.yaml`) use `${VAR}` syntax
for sensitive values. **These are NOT expanded by `yaml.safe_load()`** -- the
pipeline scripts handle interpolation automatically using `os.path.expandvars()`
on all string values after loading.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VLLM_API_KEY` | Yes | -- | API key for the vLLM server (can be any string if vLLM auth is disabled) |
| `LANGFLOW_API_KEY` | Yes | -- | API key for the Langflow instance |
| `CLIENT_SECRET` | Yes | -- | Keycloak client secret for MCP Gateway authentication |
| `VLLM_API_BASE` | No | `http://vllm-gemma4.rhoai-sdg.svc:8000/v1` | vLLM server endpoint |
| `LANGFLOW_URL` | No | `http://langflow.rhoai-sdg.svc:7860/api/v1/run/default` | Langflow agent endpoint |
| `GATEWAY_URL` | No | `https://mcp.apps.cluster-wfhjs.../mcp` | MCP Gateway endpoint |
| `KEYCLOAK_URL` | No | `https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.../` | Keycloak base URL |

### Setting environment variables

```bash
# Required
export VLLM_API_KEY="your-vllm-key"
export LANGFLOW_API_KEY="your-langflow-key"
export CLIENT_SECRET=$(oc get secret keycloak-client-secret-mcp-gateway \
  -n otel25-gateway -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d)

# Optional overrides
export VLLM_API_BASE="http://your-vllm-host:8000/v1"
export LANGFLOW_URL="http://your-langflow-host:7860/api/v1/run/default"
```

## Quick Start

### 1. Deploy vLLM with Gemma 4

```bash
# BF16 on single H100/A100-80GB
sdg/scripts/serve-gemma4.sh

# FP8 on single A100-40GB/80GB
sdg/scripts/serve-gemma4.sh --fp8

# BF16 on 2x A100-40GB
sdg/scripts/serve-gemma4.sh --tp 2
```

### 2. Deploy Langflow Agent

```bash
# Test JWT acquisition and gateway reachability first
sdg/scripts/start-agent.sh --dry-run

# Start Langflow
sdg/scripts/start-agent.sh
```

#### Production deployment on OpenShift (Helm)

`start-agent.sh` above runs Langflow directly via the CLI, which is enough
for local testing. The actual production instance (sandbox2667, namespace
`otel25-sdg`) runs as a Helm release instead, tuned for the real throughput
this pipeline needs (16 workers, 6-12 CPU / 12-20Gi memory, external Postgres
instead of the chart's default SQLite-on-PVC). That tuning is captured in
`sdg/openshift/langflow-values.yaml` so a `helm upgrade` can't silently
revert it back to chart defaults -- see the comments at the top of that file
for the full `helm install`/`helm upgrade` commands, including the external
Postgres (`langflow-postgres.yaml` + `create-langflow-db-secret.sh`) and
`maas-rhdp-api-key` secret this release depends on. The chart has no
`secretKeyRef` support for the Langflow superuser password or encryption
key, so those two are generated fresh and passed via `--set` at install
time -- never committed to a file.

The values file also sets `LANGFLOW_DEACTIVATE_TRACING=true`: Langflow's run
tracing writes a row per agent step, and at SDG volume it grew one
instance's database to ~23 GB with "database is locked" stalls (reported by
Farbod's team from a 10-process fleet run).

If the teacher model sits behind a LiteLLM proxy with caching enabled,
repeated generation prompts return identical cached samples. Add
`extra_body: {cache: {no-cache: true}}` to `model_config` in
`sdg/config/flow-training.yaml` for SDG runs against such an endpoint.

### 3. Verify Langflow MCP Integration (including session handshake)

```bash
sdg/scripts/verify-langflow-mcp.sh
```

This script verifies:
- MCP Gateway session handshake (initialize JSON-RPC + Mcp-Session-Id extraction)
- Gateway tools/list with session ID
- Langflow native MCP support detection
- If native support is absent, provides adapter instructions

### 4. Materialize Seed Dataset from MCP Gateway

```bash
# Queries the MCP Gateway's tools/list endpoint and produces a structured
# tool-metadata seed dataset as input for sdg_hub's training flow.
python3 sdg/scripts/materialize_seeds.py \
  --gateway-url "$GATEWAY_URL" \
  --keycloak-url "$KEYCLOAK_URL" \
  --client-id sdg-pipeline
```

This produces `sdg/data/seeds/tool_metadata.jsonl` with per-tool seed records
cross-referenced with the curriculum tiers from `sdg/config/seed-scenarios.yaml`.

### 5. Configure Authentication

Ensure all environment variables are set (see Environment Variables above).

### 6. Run Dry-Run (10 examples -- validate with Farbod's team)

```bash
# Run the dry-run notebook or:
python3 sdg/scripts/run-generation.py --dry-run
```

Validate the output format with Farbod's team before proceeding (D-19).

### 7. Run Production (8,500-14,000 examples)

```bash
python3 sdg/scripts/run-generation.py --config sdg/config/flow-training.yaml
python3 sdg/scripts/run-evaluation.py --config sdg/config/flow-evaluation.yaml
```

## Directory Structure

```
sdg/
+-- notebooks/                      # Jupyter notebooks for exploration/dry-run
|   +-- 01-dry-run.ipynb           # 10-example dry-run for format validation (D-19)
|   +-- 02-exploration.ipynb       # Interactive MCP server exploration
|   +-- 03-production-run.ipynb    # Full 8.5K-14K generation run
+-- scripts/
|   +-- serve-gemma4.sh            # vLLM launch script for Gemma 4
|   +-- start-agent.sh             # Langflow agent startup with MCP Gateway
|   +-- verify-langflow-mcp.sh     # Langflow MCP integration verification
|   +-- materialize_seeds.py       # MCP tool-schema-to-seed materialization
|   +-- run-generation.py          # Production pipeline runner (Plan 07)
|   +-- run-evaluation.py          # Three-stage verification runner (Plan 07)
|   +-- serialize_osft.py          # Trajectory to OSFT JSONL serializer (Plan 07)
+-- config/
|   +-- model-config.yaml          # vLLM + Gemma 4 serving configuration
|   +-- flow-training.yaml         # sdg_hub training flow overrides
|   +-- flow-evaluation.yaml       # sdg_hub evaluation flow overrides
|   +-- seed-scenarios.yaml        # Curriculum seed taxonomy (5 tiers)
+-- lib/
|   +-- osft_validation.py         # OSFT schema validation library (Plan 07)
+-- data/
|   +-- seeds/                     # Input seed DataFrames per curriculum stage
|   +-- raw/                       # Raw generation output
|   +-- filtered/                  # Post-verification filtered output
|   +-- delivery/                  # Final OSFT JSONL (single-turn + multi-turn)
+-- README.md                      # This file
```

## Configuration

### Flow Configs

- **`sdg/config/flow-training.yaml`**: Overrides for sdg_hub's
  `mcp_distillation_training` flow. Controls teacher model (Gemma 4 via
  LiteLLM `hosted_vllm/` prefix), agent framework (Langflow), runtime
  parameters (diversity via `multiply_tool_rows`, complexity via `sample_tools`),
  and quality thresholds.

- **`sdg/config/flow-evaluation.yaml`**: Overrides for sdg_hub's
  `mcp_distillation_evaluation` flow. Controls automated metrics (tool_recall,
  tool_precision, order_match, parameter_match), semantic judge dimensions (6
  dimensions, 1-10 scale), and quality threshold (7.0 minimum average).

### Seed Scenarios

- **`sdg/config/seed-scenarios.yaml`**: Five curriculum tiers defining
  progressively complex tool-calling scenarios:
  1. **single_tool** (complexity 1): Individual tool calls
  2. **parallel** (complexity 2): Independent simultaneous calls
  3. **sequential** (complexity 3): Dependent tool chains
  4. **multi_turn** (complexity 4): Follow-up conversations
  5. **closed_loop** (complexity 5): Observe-decide-act cycles

### Model Config

- **`sdg/config/model-config.yaml`**: Reference for vLLM deployment. Documents
  model identity, serving parameters, hardware recommendations, and LiteLLM
  provider prefix.

## Output Format

The pipeline produces OSFT-compatible JSONL with both trajectory formats (D-20):

### Single-Turn Format

```json
{"messages": [
  {"role": "system", "content": "You are a telecom NOC assistant..."},
  {"role": "user", "content": "Check for critical alarms"},
  {"role": "assistant", "content": null, "tool_calls": [...]},
  {"role": "tool", "tool_call_id": "call_abc", "content": "{...}"},
  {"role": "assistant", "content": "I found..."}
]}
```

### Multi-Turn Format

Same structure but with additional user/assistant turn pairs representing
follow-up questions and tool calls.

Both JSONL variants are delivered to Farbod's team (D-20). The training team
decides what to train on.

## Troubleshooting

### yaml.safe_load does not expand env vars

This is expected behavior. The pipeline scripts handle env-var interpolation
automatically using `os.path.expandvars()` on all string values after loading
the YAML. If you see literal `${VLLM_API_KEY}` in error messages, check that:
1. The env var is set in your shell: `echo $VLLM_API_KEY`
2. You are using the pipeline scripts (not loading YAML directly)

### vLLM tool-call parsing failures

- Ensure `--tool-call-parser gemma4` is used (not `hermes` or other parsers)
- Gemma 4 uses a custom non-JSON serialization that requires this specific parser
- If seeing empty `tool_calls` arrays, check vLLM version >= 0.31.0 (fixes PR #54778)
- If seeing `<pad>` tokens, reduce concurrency with `--max-num-seqs 64`

### Langflow cannot reach MCP Gateway

- Run `verify-langflow-mcp.sh` to diagnose
- Check cross-cluster networking (RHOAI cluster to existing cluster Route)
- Verify JWT acquisition: `start-agent.sh --dry-run`
- If Langflow lacks native MCP support, build the adapter per contingency instructions

### OSFT format validation errors

- Validate dry-run output with Farbod's team (D-19) before full production run
- Check `tool_call_id` threading between assistant `tool_calls` and `tool` role responses
- Ensure all messages have valid roles: system, user, assistant, tool

### Agent returns empty tool traces

- Verify Langflow flow is configured with the MCP Gateway tools
- Check that the MCP session handshake succeeds (Mcp-Session-Id in response headers)
- Look for sdg_hub `AgentBlock` timeout (default 300s) -- increase if needed
