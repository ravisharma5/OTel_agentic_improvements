---
phase: 4
slug: sdg-pipeline-and-dataset-production
status: active
nyquist_compliant: true
wave_0_complete: true
created: 2026-10-05
updated: 2026-10-05
---

# Phase 4 -- Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing in `mcp/mcp-telecom`) + manual notebook validation for the SDG pipeline itself |
| **Config file** | `mcp/mcp-telecom/pyproject.toml` (existing) |
| **Quick run command** | `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout 30` |
| **Full suite command** | `cd mcp/mcp-telecom && uv run pytest tests/ -v` |
| **Estimated runtime** | ~30-60 seconds (unit suite); manual notebook/dry-run steps are out-of-band |

---

## Sampling Rate

- **After every task commit:** Run `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout 30` for any MCP-Telecom changes (CR-01/02/03 fixes, device inventory)
- **After every plan wave:** Full MCP-Telecom suite (`uv run pytest tests/ -v`) + relevant manual notebook/dry-run validation for that wave's SDG pipeline work
- **Before `/gsd:verify-work`:** Full suite must be green, plus Farbod's team confirms the 10-example OSFT dry-run (D-19)
- **Max feedback latency:** 60 seconds for automated tests; manual steps (dry-run, Containerlab topology verification) are expected to take longer and are tracked separately, not part of the fast feedback loop

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-T1 | 04-01 | 1 | D-13 (CR-01) | T-04-01 | `command_allowlist.yaml` enforced in `validate_command()` with dynamic env-var path resolution | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_allowlist.py tests/test_safety.py -x` | Yes (rewrite) | pending |
| 04-01-T2 | 04-01 | 1 | D-13 (CR-02) | T-04-02 | `show_interface_detail`'s interface argument sanitized | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_interfaces.py -x` | W0 | pending |
| 04-01-T2 | 04-01 | 1 | D-13 (CR-03) | T-04-03 | `compare_configs`' backup_file contained to `backups/` via raw path resolution (NOT .name-stripped) -- traversal REJECTED not remapped | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_compare_configs.py -x` | W0 | pending |
| 04-02-T1 | 04-02 | 1 | D-15 | -- | NWDAF client speaks h2c to NextGCore; ConfigMap changes detected via content hashing (not st_mtime) | integration | Manual: curl test from pod | manual | pending |
| 04-02-T2 | 04-02 | 1 | D-17 | -- | ConfigMap sync between namespaces | automated | `bash -n scripts/sync-backend-routing.sh` | W0 | pending |
| 04-03-T1 | 04-03 | 1 | D-16 | -- | TMF628 spec enriched with realistic example values | automated | `python3 -m json.tool backends/specs/tmf628_performance_v4.0.0.swagger.json > /dev/null && python3 -c "import json; d=json.load(open('backends/specs/tmf628_performance_v4.0.0.swagger.json')); count=str(d).count('example'); print(f'example count: {count}')"` | Yes (enrich) | pending |
| 04-03-T2 | 04-03 | 1 | D-16 | -- | TMF642, TMF621, CAMARA specs enriched with realistic example values | automated | `for f in backends/specs/tmf642_alarm_v5.0.1.oas.yaml backends/specs/tmf621_troubleticket_v5.0.1.oas.yaml backends/specs/camara_location_verification.yaml backends/specs/camara_location_retrieval.yaml; do python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "$f: valid YAML"; done` | Yes (enrich) | pending |
| 04-04-T1 | 04-04 | 1 | SDG-03 | -- | Both single-turn and multi-turn JSONL formats valid; file named serialize_osft.py (underscore); original tool_call_id preserved when present | unit | `cd sdg/scripts && python -m pytest test_serialize_osft.py -x` | W0 | pending |
| 04-04-T2 | 04-04 | 1 | SDG-05, D-04 | -- | OSFT validation library with JSON argument validation (imported by run-evaluation.py per amended D-04) | unit | `cd sdg/lib && python -m pytest test_osft_validation.py -x` | W0 | pending |
| 04-05-T1 | 04-05 | 1 | SDG-01 | -- | vLLM and Langflow scripts syntactically valid, correct flags present | automated | `bash -n sdg/scripts/serve-gemma4.sh && bash -n sdg/scripts/start-agent.sh && grep -q "tool-call-parser gemma4" sdg/scripts/serve-gemma4.sh && grep -q "client_credentials" sdg/scripts/start-agent.sh` | W0 | pending |
| 04-05-T2 | 04-05 | 1 | SDG-01 | -- | Langflow MCP Gateway integration verified with session handshake (initialize + Mcp-Session-Id) | automated | `bash -n sdg/scripts/verify-langflow-mcp.sh && grep -q "Mcp-Session-Id" sdg/scripts/verify-langflow-mcp.sh && grep -q "initialize" sdg/scripts/verify-langflow-mcp.sh` | W0 | pending |
| 04-05-T3 | 04-05 | 1 | SDG-01, SDG-02 | -- | Flow configs valid YAML with env-var interpolation documented; no speculative osft_schema_filter block (per amended D-04) | automated | `python3 -c "import yaml; yaml.safe_load(open('sdg/config/flow-evaluation.yaml'))" && grep -q "expandvars" sdg/README.md` | W0 | pending |
| 04-05-T4 | 04-05 | 1 | SDG-01 | -- | Seed materialization script queries gateway tools/list with session handshake and produces tool metadata JSONL | automated | `python3 -c "import ast; ast.parse(open('sdg/scripts/materialize_seeds.py').read())" && grep -q "materialize_tool_seeds" sdg/scripts/materialize_seeds.py && grep -q "Mcp-Session-Id" sdg/scripts/materialize_seeds.py` | W0 | pending |
| 04-06-T1 | 04-06 | 2 | D-12, D-14 | -- | Containerlab topology with r1/r2/r3 nodes; devices.yaml in dict-keyed format loadable by DeviceManager.load_config(); devices.yaml.example updated to correct format | automated | `python3 -c "import yaml; d=yaml.safe_load(open('mcp/mcp-telecom/devices.yaml')); assert isinstance(d, dict) and 'r1' in d"` | W0 | pending |
| 04-06-T2 | 04-06 | 2 | D-12 | -- | Containerlab devices (r1, r2, r3) SSH-reachable | manual | Manual: SSH from MCP-Telecom pod | manual | pending |
| 04-07-T1 | 04-07 | 3 | SDG-01, D-04 | -- | Production scripts with seed materialization prerequisite, env-var interpolation, OSFT validation, proper serialize_osft import, and resume tracking | automated | `test -f sdg/scripts/run-generation.py && test -f sdg/scripts/run-evaluation.py && grep -q "validate_osft_line" sdg/scripts/run-evaluation.py && grep -q "COLUMN_MAP" sdg/scripts/run-evaluation.py && grep -q "expandvars" sdg/scripts/run-evaluation.py && grep -q "from sdg.scripts.serialize_osft import" sdg/scripts/run-evaluation.py && grep -q "materialize_tool_seeds" sdg/scripts/run-generation.py && grep -q "generation_manifest" sdg/scripts/run-generation.py` | W0 | pending |
| 04-07-T2 | 04-07 | 3 | SDG-01, D-05 | -- | Notebooks valid JSON with proper package imports and seed materialization | automated | `python3 -c "import json; json.load(open('sdg/notebooks/01-dry-run.ipynb'))"` | W0 | pending |
| 04-07-T3 | 04-07 | 3 | SDG-01, D-19 | -- | Dry-run with Farbod's team (10 examples, OSFT validated, seeds materialized) | manual | Manual: run 01-dry-run.ipynb on RHOAI | manual | pending |
| 04-07-T4 | 04-07 | 3 | SDG-04, SDG-05 | -- | Production run with resume tracking: 5K-10K filtered examples delivered | manual | Manual: run 03-production-run.ipynb | manual | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [x] `mcp/mcp-telecom/tests/test_allowlist.py` -- rewrite to test production `validate_command()` instead of the current copy-pasted reimplementation (CR-01) -- **covered by 04-01 Task 1**
- [x] `mcp/mcp-telecom/tests/test_safety.py` -- update TestValidateCommand to provision populated allowlist for safe-command test (deny-by-default behavior change) -- **covered by 04-01 Task 1**
- [x] `mcp/mcp-telecom/tests/test_interfaces.py` -- new test for `show_interface_detail` argument sanitization (CR-02) -- **covered by 04-01 Task 2**
- [x] `mcp/mcp-telecom/tests/test_compare_configs.py` -- new test for `backup_file` path containment with traversal-rejection-not-remap test case (CR-03) -- **covered by 04-01 Task 2**
- [x] `sdg/scripts/test_serialize_osft.py` -- validates OSFT JSONL serializer output including original tool_call_id preservation, both trajectory formats (SDG-03, SDG-05) -- **covered by 04-04 Task 1**
- [x] `sdg/lib/test_osft_validation.py` -- validates OSFT schema compliance library including JSON argument validation, imported by run-evaluation.py (D-04, D-05) -- **covered by 04-04 Task 2**

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| sdg_hub pipeline generates traces end-to-end against the live MCP Gateway | SDG-01 | Requires live GPU-backed teacher model, live gateway, and live/simulated backends -- not unit-testable | Run `01-dry-run.ipynb` on the OpenShift AI cluster; confirm traces are produced and traces route through the gateway |
| Langflow MCP Gateway integration with session handshake (initialize + Mcp-Session-Id) (native or adapter) | SDG-01, A4 | Requires live Langflow + MCP Gateway deployment to test protocol support | Run `sdg/scripts/verify-langflow-mcp.sh` on RHOAI cluster; confirm initialize handshake succeeds and Mcp-Session-Id is obtained; if MCP_NATIVE=false, build adapter with session handling per contingency instructions |
| Seed materialization from live gateway | SDG-01 | Requires live MCP Gateway with session handshake | Run `sdg/scripts/materialize_seeds.py` against live gateway; confirm sdg/data/seeds/tool_metadata.jsonl produced |
| Curriculum ordering distribution (single-tool to closed-loop) | SDG-02 | Statistical/qualitative property of the full generation run, not a single assertion | Inspect generated example metadata; confirm all 5 curriculum tiers are represented with reasonable distribution |
| Quality filtering reduces 8.5K-14K raw to 5K-10K filtered | SDG-04 | Depends on full-scale generation run output, not reproducible in a unit test | Count rows in raw vs. filtered output after a full production run |
| OSFT dry-run validation with Farbod's team | D-19 | Requires Farbod's team's own training pipeline to confirm format compatibility -- external dependency | Generate 10 examples, hand off to Farbod's team, confirm their mini-trainer/OSFT pipeline ingests them without error |
| NWDAF h2c live semantic verification | D-15 | Requires live NextGCore NWDAF endpoint, protocol-level behavior not mockable in pytest | `curl --http2-prior-knowledge` test from a pod against the NextGCore NWDAF endpoint, confirm valid analytics response |
| Containerlab topology device reachability (r1, r2, r3) | D-12, D-14 | Requires actual Containerlab deployment (network namespaces/privileged containers), not unit-testable | SSH/CLI round-trip to each Containerlab-provisioned device (r1, r2, r3) via MCP-Telecom's tools, confirm real (non-error) responses |
| Cross-cluster Keycloak client-credentials auth | D-07 | Requires two live clusters and a real token exchange | From the separate OpenShift AI cluster, fetch a JWT via Keycloak client-credentials grant and call the MCP Gateway Route, confirm 200 response |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s (automated tests); manual steps tracked separately
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (revision 4 -- updated for cross-AI review fixes: CR-03 raw path resolution, test_safety.py update, serialize_osft.py underscore naming, original tool_call_id preservation, MCP session handshake validation, seed materialization task, content-hash ConfigMap detection, env-var interpolation, dict-keyed devices.yaml format, r1/r2/r3 node names, resume tracking, JSON argument validation)
