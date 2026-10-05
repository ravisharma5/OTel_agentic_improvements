---
phase: 04-sdg-pipeline-and-dataset-production
plan: 05
subsystem: sdg-pipeline-scaffolding
tags: [vllm, langflow, mcp-gateway, sdg-hub, curriculum, seed-materialization]
dependency_graph:
  requires: []
  provides:
    - sdg-vllm-serving-script
    - sdg-langflow-startup-script
    - sdg-langflow-mcp-verification
    - sdg-flow-training-config
    - sdg-flow-evaluation-config
    - sdg-seed-scenarios
    - sdg-materialize-seeds
    - sdg-readme
  affects:
    - 04-06 (notebooks reference configs and scripts from this plan)
    - 04-07 (run-generation.py and run-evaluation.py consume flow configs, must implement env-var interpolation)
tech_stack:
  added: []
  patterns:
    - shell-script-with-set-euo-pipefail
    - yaml-config-with-env-var-interpolation
    - mcp-session-handshake-protocol
    - cli-plus-importable-python-module
key_files:
  created:
    - sdg/scripts/serve-gemma4.sh
    - sdg/scripts/start-agent.sh
    - sdg/scripts/verify-langflow-mcp.sh
    - sdg/scripts/materialize_seeds.py
    - sdg/config/model-config.yaml
    - sdg/config/flow-training.yaml
    - sdg/config/flow-evaluation.yaml
    - sdg/config/seed-scenarios.yaml
    - sdg/README.md
    - sdg/__init__.py
    - sdg/scripts/__init__.py
  modified: []
decisions:
  - "Reuse same Gemma 4 instance for semantic judge (D-11 discretion) -- avoids deploying second model"
  - "7 single_tool scenarios covering TMF642, TMF628, TMF621, NWDAF, CAMARA, and MCP-Telecom device tools"
  - "materialize_seeds.py supports both requests and httpx as HTTP backends for portability"
metrics:
  duration: 9 minutes
  completed: "2026-10-05T22:16:25Z"
  tasks_completed: 4
  tasks_total: 4
  files_created: 11
  files_modified: 0
---

# Phase 04 Plan 05: SDG Pipeline Infrastructure Scaffolding Summary

vLLM serving script, Langflow agent startup, MCP session-handshake verification, sdg_hub flow configs with env-var interpolation convention, 5-tier curriculum seed taxonomy, tool-schema seed materialization from MCP Gateway tools/list, and complete recipe README with pinned dependency versions for Farbod's team.

## Task Results

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | vLLM serving and Langflow agent startup scripts | 4fdfbe1 | sdg/scripts/serve-gemma4.sh, sdg/scripts/start-agent.sh, sdg/config/model-config.yaml |
| 2 | Langflow MCP Gateway verification with session handshake | 5376938 | sdg/scripts/verify-langflow-mcp.sh |
| 3 | sdg_hub flow configs, curriculum seeds, and recipe README | a3cef9d | sdg/config/flow-training.yaml, sdg/config/flow-evaluation.yaml, sdg/config/seed-scenarios.yaml, sdg/README.md |
| 4 | Materialize MCP tool schemas into sdg_hub seed dataset | a602e77 | sdg/scripts/materialize_seeds.py, sdg/__init__.py, sdg/scripts/__init__.py |

## Decisions Made

1. **Semantic judge reuses Gemma 4 instance (D-11):** The evaluation flow configures the same Gemma 4 31B model for both teacher generation and semantic judging, avoiding the need to deploy a second model on the RHOAI cluster.

2. **7 single_tool scenarios across all domains:** The single_tool tier covers TMF642 (alarms), TMF628 (performance), TMF621 (trouble tickets), NWDAF (analytics), CAMARA (location verification), and MCP-Telecom device tools (interfaces, BGP), exceeding the minimum of 5 scenarios.

3. **Dual HTTP backend support in materialize_seeds.py:** The script supports both `requests` and `httpx` as HTTP backends, with automatic fallback, for portability across different pipeline environments.

4. **env-var interpolation documented as convention:** The flow YAML files use `${VAR}` syntax with a clear header comment explaining that `yaml.safe_load()` does NOT expand these -- pipeline scripts must apply `os.path.expandvars()` after loading. This convention is documented in both the YAML files and the README.

## Deviations from Plan

None -- plan executed exactly as written.

## Key Artifacts

### Shell Scripts (3)

- **serve-gemma4.sh**: Launches vLLM with `--tool-call-parser gemma4`, `--enable-auto-tool-choice`, `--max-num-seqs 64` (Pitfall 3 mitigation). Accepts `--fp8` and `--tp N` flags. Documents hardware requirements.
- **start-agent.sh**: Acquires JWT via `client_credentials` grant from Keycloak (D-07), starts Langflow with MCP Gateway configuration. `CLIENT_SECRET` required from env (T-04-04 threat mitigation). Supports `--dry-run` mode.
- **verify-langflow-mcp.sh**: Performs full MCP session handshake (initialize JSON-RPC + Mcp-Session-Id extraction), tests tools/list with session, detects Langflow native MCP support (MCP_NATIVE flag), provides contingency adapter instructions with mandatory session handshake handling. Resolves RESEARCH.md Open Question 3 and Assumption A4.

### Python Script (1)

- **materialize_seeds.py**: Queries MCP Gateway (with session handshake), extracts tool schemas from tools/list, cross-references with seed-scenarios.yaml curriculum tiers, produces structured JSONL seed dataset. Both CLI (`argparse`) and importable (`materialize_tool_seeds` function). Output defaults to `sdg/data/seeds/tool_metadata.jsonl`.

### Config YAMLs (4)

- **model-config.yaml**: vLLM serving reference with LiteLLM provider prefix `hosted_vllm/google/gemma-4-31B-it`, hardware recommendations.
- **flow-training.yaml**: sdg_hub training flow overrides -- Gemma 4 teacher model, Langflow agent, runtime params (multiply_tool_rows x20, sample_tools x3), quality thresholds. Env-var interpolation convention documented.
- **flow-evaluation.yaml**: 4 automated metrics (tool_recall, tool_precision, order_match, parameter_match) + 6 semantic judge dimensions with 7.0 threshold. No osft_schema_filter block (D-04 amended). Inline comment explains OSFT validation runs in run-evaluation.py.
- **seed-scenarios.yaml**: 5-tier curriculum (single_tool, parallel, sequential, multi_turn, closed_loop) with 21 total scenarios across all tiers.

### Documentation (1)

- **README.md**: Complete recipe for Farbod's team with pinned versions (sdg-hub==0.9.4, training-hub==0.10.0, vllm==0.31.0 per D-03), env-var interpolation documentation, 7-step quick start, directory structure, output format examples, troubleshooting.

## Known Stubs

None -- all files contain production-ready configuration and logic. No placeholder values or TODO items that prevent the plan's goals from being achieved.

## Verification Results

All 14 verification checks passed:
1. All 3 shell scripts pass `bash -n` syntax check
2. All 4 YAML files pass `yaml.safe_load()` validation
3. Flow configs reference correct model (`hosted_vllm/google/gemma-4-31B-it`) and agent (`langflow`) endpoints
4. Evaluation flow does NOT contain `osft_schema_filter` block (D-04 compliant)
5. Seed scenarios cover all 5 curriculum tiers with 21 scenarios
6. Seed materialization script performs MCP session handshake and produces tool metadata JSONL (functional test: 21 records from 3 mock tools)
7. README covers prerequisites with pinned versions, documents env-var interpolation and seed materialization
8. Langflow MCP verification script validates MCP session handshake (initialize + Mcp-Session-Id)

## Self-Check: PASSED

All 11 created files verified present on disk. All 4 task commit hashes verified in git log.
