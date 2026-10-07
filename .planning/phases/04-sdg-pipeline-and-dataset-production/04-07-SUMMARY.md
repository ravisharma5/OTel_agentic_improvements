---
phase: 04-sdg-pipeline-and-dataset-production
plan: 07
subsystem: sdg-pipeline
status: partial (2/4 tasks complete, checkpoint at Task 3)
tags: [sdg, pipeline, notebooks, osft, generation, evaluation]
dependency_graph:
  requires: [04-02, 04-03, 04-04, 04-05, 04-06]
  provides: [run-generation, run-evaluation, pipeline-notebooks]
  affects: [sdg/scripts/, sdg/notebooks/, sdg/data/]
tech_stack:
  added: []
  patterns: [env-var-interpolation, resume-manifest, column-mapping, osft-validation]
key_files:
  created:
    - sdg/scripts/run-generation.py
    - sdg/scripts/run-evaluation.py
    - sdg/notebooks/01-dry-run.ipynb
    - sdg/notebooks/02-exploration.ipynb
    - sdg/notebooks/03-production-run.ipynb
    - sdg/data/seeds/.gitkeep
    - sdg/data/raw/.gitkeep
    - sdg/data/filtered/.gitkeep
    - sdg/data/delivery/.gitkeep
  modified: []
decisions:
  - "COLUMN_MAP bridges sdg_hub output columns to serializer input keys -- fails hard on missing required keys"
  - "Resume manifest uses atomic write-then-rename to prevent corruption on partial failures"
  - "Both scripts and notebooks share the same _load_config / expandvars / COLUMN_MAP patterns for consistency"
metrics:
  duration_seconds: 430
  completed_date: "2026-10-07"
  tasks_completed: 2
  tasks_total: 4
  files_created: 9
  files_modified: 0
---

# Phase 4 Plan 7: Production Pipeline Scripts and Notebooks Summary

Production pipeline scripts with seed materialization, env-var interpolation, OSFT validation, column mapping, resume tracking, and three Jupyter notebooks for dry-run/exploration/production-run workflows

**Status: PARTIAL -- 2/4 tasks complete, blocked at Task 3 (checkpoint:human-verify)**

Task 3 requires live infrastructure deployment (vLLM, Langflow, Keycloak client on RHOAI cluster)
and coordination with Farbod's team for D-19 dry-run validation. Task 4 depends on Task 3 completion.

## Completed Tasks

### Task 1: Production Pipeline Scripts (da92d32)

Created two production scripts:

**run-generation.py:**
- Imports `materialize_tool_seeds` from `sdg.scripts.materialize_seeds` and calls it as a prerequisite before running the sdg_hub flow
- `_load_config()` uses `os.path.expandvars()` on all string values after `yaml.safe_load()` to expand `${VLLM_API_KEY}`, `${LANGFLOW_API_KEY}`, etc.
- `--dry-run` flag limits generation to 10 examples for D-19 format validation gate
- `--resume` flag with `.generation_manifest.json` for checkpoint/resume on partial failures (atomic write-then-rename)
- Iterates over curriculum tiers from `seed-scenarios.yaml`, outputs per-tier `{tier}_raw.jsonl`
- `FlowRegistry.discover_flows()` / `Flow.from_yaml()` for sdg_hub integration

**run-evaluation.py:**
- Imports `serialize_single_turn` and `serialize_multi_turn` from `sdg.scripts.serialize_osft` (underscore, proper package import)
- Imports `validate_osft_line` and `validate_osft_file` from `sdg.lib.osft_validation` (per amended D-04)
- `_load_config()` with `os.path.expandvars()` for env-var interpolation
- Explicit `COLUMN_MAP` dict mapping sdg_hub output columns to serializer input keys
- `ValueError` raised (fails hard) if required serializer keys (`question`, `tool_trace`, `answer`, `tools`) are unmapped
- OSFT validation runs unconditionally after eval flow completes -- not behind a flag, not in a separate script
- Dual-format output: `single-turn.jsonl` and `multi-turn.jsonl` in delivery directory (D-20)
- Validates delivery files with `validate_osft_file()` as sanity check

Created `sdg/data/{seeds,raw,filtered,delivery}/` directories with `.gitkeep` files.

### Task 2: Pipeline Notebooks (c9162e6)

**01-dry-run.ipynb** (10 cells):
- 10-example format validation for D-19 gate
- Calls `materialize_tool_seeds` before generation
- Uses `_load_config` with `os.path.expandvars()` for env-var interpolation
- Applies same `COLUMN_MAP` as `run-evaluation.py`
- Imports from `sdg.scripts.serialize_osft` (underscore, proper package path)
- Runs OSFT validation via `validate_osft_line` (same pattern as `run-evaluation.py`)
- Displays 3 sample examples in pretty JSON
- Mentions intended for RHOAI workbench

**02-exploration.ipynb** (6 cells):
- Interactive MCP Gateway exploration
- JWT acquisition from Keycloak via `client_credentials` grant
- MCP session handshake (`initialize` + `Mcp-Session-Id`)
- Tool discovery via `tools/list` with domain grouping
- Sample tool invocation (`tmf642_list_alarms`)
- Schema inspection for dry-run tools

**03-production-run.ipynb** (9 cells):
- Full 8,500-14,000 example production run across all 5 curriculum tiers
- `multiply_tool_rows: 20`, `sample_tools: 3` production params
- Calls `materialize_tool_seeds` before generation
- Resume tracking with `.generation_manifest.json` (same pattern as `run-generation.py`)
- Evaluation flow filtering + column mapping + automatic OSFT validation
- Dual-format serialization via `sdg.scripts.serialize_osft`
- Final statistics: raw/filtered/validated counts, per-tier breakdown, coverage report

All notebooks import from proper package paths (`sdg.scripts.*`, `sdg.lib.*`).

## Incomplete Tasks

### Task 3: Deploy infrastructure, verify Langflow MCP integration, run dry-run (BLOCKED)

This is a `checkpoint:human-verify` task requiring:
1. vLLM with Gemma 4 31B deployed on RHOAI cluster
2. Langflow agent deployed on RHOAI cluster
3. Langflow MCP verification (resolves RESEARCH.md Open Question 3)
4. Keycloak `sdg-pipeline` client created in `mcp` realm
5. Seed materialization from live gateway
6. Cross-cluster connectivity test
7. Dry-run notebook execution on RHOAI
8. D-19 gate: Farbod's team validates OSFT format

### Task 4: Run production pipeline and deliver dataset (BLOCKED on Task 3)

Depends on Task 3 infrastructure deployment and D-19 dry-run validation.

## Deviations from Plan

None -- plan executed exactly as written for Tasks 1 and 2.

## Self-Check: PASSED

All 9 created files verified present on disk. Both task commits verified in git log:
- da92d32: Task 1 (production pipeline scripts)
- c9162e6: Task 2 (pipeline notebooks)
