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
| 04-01-T1 | 04-01 | 1 | D-13 (CR-01) | T-04-01 | `command_allowlist.yaml` enforced in `validate_command()` | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_allowlist.py -x` | Yes (rewrite) | ⬜ pending |
| 04-01-T2 | 04-01 | 1 | D-13 (CR-02) | T-04-02 | `show_interface_detail`'s interface argument sanitized | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_interfaces.py -x` | ❌ W0 | ⬜ pending |
| 04-01-T2 | 04-01 | 1 | D-13 (CR-03) | T-04-03 | `compare_configs`' backup_file contained to `backups/` | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_compare_configs.py -x` | ❌ W0 | ⬜ pending |
| 04-02-T1 | 04-02 | 1 | D-15 | -- | NWDAF client speaks h2c to NextGCore | integration | Manual: curl test from pod | ❌ manual | ⬜ pending |
| 04-02-T2 | 04-02 | 1 | D-17 | -- | ConfigMap sync between namespaces | automated | `bash -n scripts/sync-backend-routing.sh` | ❌ W0 | ⬜ pending |
| 04-04-T1 | 04-04 | 1 | SDG-03 | -- | Both single-turn and multi-turn JSONL formats valid | unit | `cd sdg/scripts && python -m pytest test_serialize_osft.py -x` | ❌ W0 | ⬜ pending |
| 04-04-T2 | 04-04 | 1 | SDG-05, D-04 | -- | OSFT validation library (imported by eval flow block) | unit | `cd sdg/lib && python -m pytest test_osft_validation.py -x` | ❌ W0 | ⬜ pending |
| 04-05-T2 | 04-05 | 1 | SDG-01 | -- | Langflow MCP Gateway integration verified (Open Q3) | automated | `bash -n sdg/scripts/verify-langflow-mcp.sh` | ❌ W0 | ⬜ pending |
| 04-05-T3 | 04-05 | 1 | SDG-01, SDG-02 | -- | Flow configs valid YAML with osft_schema_filter block (D-04) | automated | `python3 -c "import yaml; yaml.safe_load(open('sdg/config/flow-evaluation.yaml'))"` | ❌ W0 | ⬜ pending |
| 04-06-T1 | 04-06 | 2 | D-12, D-14 | -- | Containerlab topology and device inventory populated | automated | `python3 -c "import yaml; yaml.safe_load(open('mcp/mcp-telecom/devices.yaml'))"` | ❌ W0 | ⬜ pending |
| 04-06-T2 | 04-06 | 2 | D-12 | -- | Containerlab devices SSH-reachable | manual | Manual: SSH from MCP-Telecom pod | ❌ manual | ⬜ pending |
| 04-07-T1 | 04-07 | 3 | SDG-01 | -- | Production scripts exist and load sdg_hub | automated | `test -f sdg/scripts/run-generation.py && test -f sdg/scripts/run-evaluation.py` | ❌ W0 | ⬜ pending |
| 04-07-T2 | 04-07 | 3 | SDG-01, D-05 | -- | Notebooks valid JSON | automated | `python3 -c "import json; json.load(open('sdg/notebooks/01-dry-run.ipynb'))"` | ❌ W0 | ⬜ pending |
| 04-07-T3 | 04-07 | 3 | SDG-01, D-19 | -- | Dry-run with Farbod's team (10 examples, OSFT validated) | manual | Manual: run 01-dry-run.ipynb on RHOAI | ❌ manual | ⬜ pending |
| 04-07-T4 | 04-07 | 3 | SDG-04, SDG-05 | -- | Production run: 5K-10K filtered examples delivered | manual | Manual: run 03-production-run.ipynb | ❌ manual | ⬜ pending |

*Status: ⬜ pending / ✅ green / ❌ red / ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `mcp/mcp-telecom/tests/test_allowlist.py` -- rewrite to test production `validate_command()` instead of the current copy-pasted reimplementation (CR-01) -- **covered by 04-01 Task 1**
- [x] `mcp/mcp-telecom/tests/test_interfaces.py` -- new test for `show_interface_detail` argument sanitization (CR-02) -- **covered by 04-01 Task 2**
- [x] `mcp/mcp-telecom/tests/test_compare_configs.py` -- new test for `backup_file` path containment (CR-03) -- **covered by 04-01 Task 2**
- [x] `sdg/scripts/test_serialize_osft.py` -- validates OSFT JSONL serializer output, both trajectory formats (SDG-03, SDG-05) -- **covered by 04-04 Task 1**
- [x] `sdg/lib/test_osft_validation.py` -- validates OSFT schema compliance library imported by eval flow block (D-04, D-05) -- **covered by 04-04 Task 2**

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| sdg_hub pipeline generates traces end-to-end against the live MCP Gateway | SDG-01 | Requires live GPU-backed teacher model, live gateway, and live/simulated backends -- not unit-testable | Run `01-dry-run.ipynb` on the OpenShift AI cluster; confirm traces are produced and traces route through the gateway |
| Langflow MCP Gateway integration (native or adapter) | SDG-01, A4 | Requires live Langflow + MCP Gateway deployment to test protocol support | Run `sdg/scripts/verify-langflow-mcp.sh` on RHOAI cluster; if MCP_NATIVE=false, build adapter per contingency instructions |
| Curriculum ordering distribution (single-tool to closed-loop) | SDG-02 | Statistical/qualitative property of the full generation run, not a single assertion | Inspect generated example metadata; confirm all 5 curriculum tiers are represented with reasonable distribution |
| Quality filtering reduces 8.5K-14K raw to 5K-10K filtered | SDG-04 | Depends on full-scale generation run output, not reproducible in a unit test | Count rows in raw vs. filtered output after a full production run |
| OSFT dry-run validation with Farbod's team | D-19 | Requires Farbod's team's own training pipeline to confirm format compatibility -- external dependency | Generate 10 examples, hand off to Farbod's team, confirm their mini-trainer/OSFT pipeline ingests them without error |
| NWDAF h2c live semantic verification | D-15 | Requires live NextGCore NWDAF endpoint, protocol-level behavior not mockable in pytest | `curl --http2-prior-knowledge` test from a pod against the NextGCore NWDAF endpoint, confirm valid analytics response |
| Containerlab topology device reachability | D-12, D-14 | Requires actual Containerlab deployment (network namespaces/privileged containers), not unit-testable | SSH/CLI round-trip to each Containerlab-provisioned device via MCP-Telecom's tools, confirm real (non-error) responses |
| Cross-cluster Keycloak client-credentials auth | D-07 | Requires two live clusters and a real token exchange | From the separate OpenShift AI cluster, fetch a JWT via Keycloak client-credentials grant and call the MCP Gateway Route, confirm 200 response |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s (automated tests); manual steps tracked separately
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (revision pass -- all plan/task IDs populated, Wave 0 items covered)
